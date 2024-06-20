import asyncio
import math
import re
import traceback
from contextlib import suppress
from typing import Any, Coroutine, Literal, cast

from aiocouch import CouchDB, Database, View
from metricq import HistoryClient, Timedelta, Timestamp
from metricq.exceptions import HistoryError
from metricq.logging import get_logger

JsonDict = dict[str, Any]

logger = get_logger()
logger.setLevel("INFO")

SeverityType = Literal["error"] | Literal["warning"] | Literal["info"]
ScopeType = Literal["metric"]
IssueType = (
    Literal["dead"]
    | Literal["undead"]
    | Literal["no_value"]
    | Literal["infinite"]
    | Literal["invalid_name"]
    | Literal["errored"]
    | Literal["timeout"]
    | Literal["missing_historic"]
    | Literal["missing_metadata"]
)


class AsyncTaskPool:
    def __init__(self, max_tasks: int, timeout: float = 0.1):
        self.max_tasks = max_tasks
        self.timeout = timeout
        self.pending: set[asyncio.Task] = set()

    async def append(self, coro: Coroutine) -> None:
        assert len(self.pending) <= self.max_tasks

        # Once there are enough pending tasks, we will wait for the timeout.
        # Ideally, we make a good chunk of progress
        while len(self.pending) == self.max_tasks:
            done, pending = await asyncio.wait(
                self.pending,
                timeout=self.timeout,
                return_when=asyncio.ALL_COMPLETED,
            )

            assert self.pending == done | pending
            self.pending = pending

            # fetch all results of the done tasks.
            for task in done:
                try:
                    task.result()
                except Exception as e:
                    # this should never be CancelledError or InvalidStateError
                    # besides strange cancelling on shutdown.
                    # Other exceptions we will just log and forget about. We
                    # have other fish to fry.
                    logger.error("Failed to complete health check task: ", e)
                    traceback.print_exception(e)

        self.pending.add(asyncio.create_task(coro))

    async def completed(self) -> None:
        if len(self.pending) == 0:
            return

        # We don't stop on exceptions. We want all tasks to complete, be it
        # successful or not.
        results = await asyncio.gather(*self.pending, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("Failed to complete health check task: ", result)
                traceback.print_exception(result)

        assert all(task.done() for task in self.pending)

        self.pending = set()


def issue_report_id(issue_type: IssueType, scope_type: ScopeType, scope: str) -> str:
    return f"{issue_type}-{scope_type}-{scope}"


class ClusterScanner:
    def __init__(self, token: str, url: str, couchdb: str):
        self.token = token
        self.url = url
        self.couch: CouchDB = CouchDB(couchdb)

        self.db_issues: Database | None = None
        self.db_metadata: Database | None = None

        self.lock: asyncio.Lock | None = None

    async def connect(self):
        self.lock = asyncio.Lock()

        self.db_metadata = await self.couch.create("metadata", exists_ok=True)

        self.db_issues = await self.couch.create("issues", exists_ok=True)

        index = await self.db_issues.design_doc("sortedBy", exists_ok=True)
        await index.create_view(
            view="scope",
            map_function="function (doc) {\n  emit(doc.scope_type + doc.scope, null);\n}",
            exists_ok=True,
        )
        await index.create_view(
            view="severity",
            map_function='function (doc) {\n  if (doc.severity == "error") {\n    emit(1, null);\n } else if (doc.severity == "warning") {\n emit(2, null);\n } else {\n emit(3, null);\n }\n }',
            exists_ok=True,
        )
        await index.create_view(
            view="type",
            map_function="function (doc) {\n emit(doc.type, null);\n }",
            exists_ok=True,
        )

    async def stop(self) -> None:
        await self.couch.close()

    @property
    def running(self) -> bool:
        assert self.lock is not None
        return self.lock.locked()

    async def run_once(self) -> None:
        assert self.lock is not None
        if self.lock.locked():
            raise RuntimeError("Scan already running")

        async with self.lock:
            logger.warn("Starting Cluster Health Scan")
            try:
                await self._run_scan()
            except Exception:
                logger.exception("Cluster Scan failed")
            finally:
                logger.warn("Cluster Health Scan Finished")

    async def _run_scan(self) -> None:
        assert self.db_metadata is not None

        async with HistoryClient(self.token, self.url, add_uuid=True) as client:
            tasks = AsyncTaskPool(max_tasks=250)

            async for doc in self.db_metadata.docs():
                metric = doc.id
                metadata = doc.data

                # this assert is purely for mypy. doc.data can only return None
                # if the doc does not exist. It clearly exists, as we only
                # get existing documents from the docs iterator.
                assert metadata is not None

                await tasks.append(self.check_metric_metadata(metric, metadata))

                if metadata.get("historic", False):
                    # Only check the db status for historic metrics
                    await tasks.append(
                        self.check_metric_is_dead(client, metric, metadata)
                    )
                    await tasks.append(
                        self.check_metric_for_infinites(client, metric, metadata)
                    )

                # there is no tooling for renaming metrics, so bad
                # names is nothing we should warn about yet.
                # await tasks.append(self.check_metric_name(metric))

            await tasks.completed()

    async def create_issue_report(
        self,
        issue_type: IssueType,
        scope_type: ScopeType,
        scope: str,
        severity: SeverityType | None = None,
        **kwargs: Any,
    ):
        assert self.db_issues is not None
        report = await self.db_issues.create(
            id=issue_report_id(issue_type, scope_type, scope),
            exists_ok=True,
        )

        report["severity"] = "warning" if severity is None else severity

        if "first_detection_date" not in report:
            # only set first_detection_date when creating the report, not
            # on updates
            report["first_detection_date"] = Timestamp.now().datetime.isoformat()

        report["date"] = Timestamp.now().datetime.isoformat()

        report["type"] = issue_type
        report["scope_type"] = scope_type
        report["scope"] = scope

        # entries in the new kwargs should overwrite existing entries
        for key, val in kwargs.items():
            report[key] = val

        await report.save()

    async def delete_issue_report(
        self,
        issue_type: IssueType,
        scope_type: ScopeType,
        scope: str,
    ):
        # This function would better be named like this:
        # make_sure_no_matching_error_report_exists() but that's too long for my
        # taste. So yes, unlike delete_issue_reports() and delete_issue_report_by()
        # this function should not error if we try to delete something that
        # does not exists.
        assert self.db_issues is not None

        report = await self.db_issues.create(
            id=issue_report_id(issue_type, scope_type, scope),
            exists_ok=True,
        )

        if report.exists:
            await report.delete()

    async def delete_issue_report_by(self, id: str):
        assert self.db_issues is not None
        report = await self.db_issues.get(id)
        await report.delete()

    async def delete_issue_reports(self, scope_type: ScopeType, scope: str):
        assert self.db_issues is not None

        async for report in self.db_issues.find(
            {
                "scope": scope,
                "scope_type": scope_type,
            }
        ):
            await report.delete()

    async def handle_issue_report(
        self,
        create_condition: bool,
        issue_type: IssueType,
        scope_type: ScopeType,
        scope: str,
        severity: SeverityType | None = None,
        **kwargs: Any,
    ):
        if create_condition:
            await self.create_issue_report(
                issue_type, scope_type, scope, severity, **kwargs
            )
        else:
            await self.delete_issue_report(issue_type, scope_type, scope)

    async def check_metric_metadata(self, metric: str, metadata: JsonDict):
        source = metadata.get("source")

        # This check is extra from missing_metadata, because it is a bit
        # more important, but new. We want to enforce that every metric has
        # to be either historic or not historic, i.e. only live. Or in other
        # words, not setting it is not an option.
        await self.handle_issue_report(
            "historic" not in metadata or not isinstance(metadata["historic"], bool),
            scope_type="metric",
            scope=metric,
            issue_type="missing_historic",
            severity="warning",
            source=source,
        )

        missing_metadata = []

        if (
            "rate" not in metadata
            or not isinstance(metadata["rate"], float)
            or metadata["rate"] <= 0
        ):
            missing_metadata.append("rate")

        if (
            "description" not in metadata
            or not isinstance(metadata["description"], str)
            or not metadata["description"]
        ):
            missing_metadata.append("description")

        if (
            "unit" not in metadata
            or not isinstance(metadata["unit"], str)
            or not metadata["unit"]
        ):
            missing_metadata.append("unit")

        if (
            "source" not in metadata
            or not isinstance(metadata["source"], str)
            or not metadata["source"]
        ):
            missing_metadata.append("source")

        await self.handle_issue_report(
            len(missing_metadata) > 0,
            scope_type="metric",
            scope=metric,
            issue_type="missing_metadata",
            severity="error" if "source" in missing_metadata else "info",
            source=source,
            missing_metadata=missing_metadata,
        )

    def _guess_allowed_age(self, metadata: JsonDict) -> Timedelta:
        # We set the allowed_age rather high, because in prod, checks seem to
        # take a while, which messes up the timings :(
        allowed_age = Timedelta.from_string("1min")
        try:
            rate = metadata["rate"]
            if not isinstance(rate, (int, float)):
                logger.error(
                    "Invalid rate: {} ({}) [{}]",
                    rate,
                    type(rate),
                    metadata,
                )
            else:
                allowed_age += Timedelta.from_s(1 / rate)
        except KeyError:
            # Fall back to compute tolerance from interval
            with suppress(KeyError):
                interval = metadata["interval"]
                if isinstance(interval, str):
                    allowed_age += Timedelta.from_string(interval)
                elif isinstance(interval, (int, float)):
                    allowed_age += Timedelta.from_s(interval)
                else:
                    logger.error(
                        "Invalid interval: {} ({}) [{}]",
                        interval,
                        type(interval),
                        metadata,
                    )

        return allowed_age

    async def check_metric_is_dead(
        self, client: HistoryClient, metric: str, metadata: JsonDict
    ) -> None:
        result = None
        has_timed_out = False
        has_errored = False
        error_msg: str | None = None

        request_time: Timestamp | None = None
        request_start_time = Timestamp.now()

        try:
            result = await client.history_last_value(metric, timeout=60)

            # In a perfect world, this time would be taken *before* the request
            # However, we live in the real world where the actual request might
            # get preempted before it get's send. Hence we ran into a lot of
            # false positives, driven by the high load during these checks.
            # However, let's assume that the time after the actual request
            # finishes until the return is small.
            request_time = Timestamp.now()
        except TimeoutError:
            has_timed_out = True
        except HistoryError as e:
            has_errored = True
            error_msg = str(e)

        # I'm not sure how this could happen, but here we are.
        await self.handle_issue_report(
            result is None and request_time is not None,
            scope_type="metric",
            scope=metric,
            issue_type="no_value",
            severity="warning",
            source=metadata.get("source"),
        )

        # a timeout likely means that the bindings for this metric is borked
        await self.handle_issue_report(
            has_timed_out,
            scope_type="metric",
            scope=metric,
            severity="warning",
            issue_type="timeout",
            source=metadata.get("source"),
        )

        # an HistoryError is something in the Database, this sounds bad.
        await self.handle_issue_report(
            has_errored,
            scope_type="metric",
            scope=metric,
            issue_type="errored",
            severity="error",
            error=str(error_msg),
            source=metadata.get("source"),
        )

        # if anything went wrong until here, we first push the issue reports,
        # but now it's time to go.
        if request_time is None or result is None or has_timed_out or has_errored:
            return

        age = request_time - result.timestamp

        # Archived metrics are supposed to not receive new data points.
        # For such metrics, the archived metadata is the ISO8601 string, when
        # the metric was archived.

        # We add the time our request took to the allowed_age, since we can't
        # tell where the request might have gotten stuck. We may not catch
        # metrics, which failed just shy before the check or whose that have
        # a slightly different rate than expected, but I guess we can live with
        # that. The alternative is a lot of false positives.
        allowed_age = self._guess_allowed_age(metadata) + (
            request_start_time - request_time
        )

        # We haven't received a new data point in a while and the metric
        # wasn't archived => It's dead, Jim.
        await self.handle_issue_report(
            age > allowed_age and not metadata.get("archived"),
            scope_type="metric",
            scope=metric,
            issue_type="dead",
            severity="error",
            last_timestamp=str(result.timestamp.datetime.isoformat()),
            source=metadata.get("source"),
        )

        # the metric is archived, but we received a new data point since
        # => Zombies are here, back in my dayz, you'd reload your hatchet now.
        if "archived" in metadata:
            archived_at = Timestamp.from_iso8601(metadata["archived"])
        else:
            archived_at = Timestamp.now()

        await self.handle_issue_report(
            bool(metadata.get("archived")) and archived_at < result.timestamp,
            scope_type="metric",
            scope=metric,
            issue_type="undead",
            severity="warning",
            last_timestamp=str(result.timestamp.datetime.isoformat()),
            source=metadata.get("source"),
            archived=metadata.get("archived"),
        )

    async def check_metric_for_infinites(
        self,
        client: HistoryClient,
        metric: str,
        metadata: JsonDict,
    ) -> None:
        start_time = Timestamp(0)
        end_time = Timestamp.from_now(Timedelta.from_string("7d"))

        has_errored = False
        error_msg = None

        try:
            result = await client.history_aggregate(
                metric,
                start_time=start_time,
                end_time=end_time,
                timeout=60,
            )

        except asyncio.TimeoutError:
            # we should see this in the dead metrics check as well, so don't bother here.
            pass
        except HistoryError as e:
            # we may get a different error from the database though
            has_errored = True
            error_msg = str(e)

        await self.handle_issue_report(
            has_errored,
            scope_type="metric",
            scope=metric,
            issue_type="errored",
            severity="info",
            error=str(error_msg),
            source=metadata.get("source"),
        )

        if has_errored:
            return

        await self.handle_issue_report(
            not math.isfinite(result.minimum) or not math.isfinite(result.maximum),
            scope_type="metric",
            scope=metric,
            issue_type="infinite",
            severity="info",
            last_timestamp=str(result.timestamp.datetime.isoformat()),
            source=metadata.get("source"),
        )

    async def check_metric_name(self, metric: str):
        assert self.db_metadata is not None

        if not re.match(r"([a-zA-Z][a-zA-Z0-9_]+\.)+[a-zA-Z][a-zA-Z0-9_]+", metric):
            doc = await self.db_metadata.get(metric)
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                issue_type="invalid_name",
                severity="info",
                source=doc.get("source"),
            )
        else:
            await self.delete_issue_report(
                scope_type="metric",
                scope=metric,
                issue_type="invalid_name",
            )

    async def find_issues(
        self, page: int, per_page: int, sorting_key: str, descending: bool
    ) -> JsonDict:
        assert self.db_issues is not None

        skip = (page - 1) * per_page
        limit = per_page

        if sorting_key == "id":
            view = cast(View, self.db_issues.all_docs)
        elif sorting_key == "severity":
            view = self.db_issues.view("sortedBy", "severity")
        elif sorting_key == "scope":
            view = self.db_issues.view("sortedBy", "scope")
        elif sorting_key == "issue":
            view = self.db_issues.view("sortedBy", "type")

        response = await view.get(
            include_docs=True, limit=limit, skip=skip, descending=descending
        )

        return {
            "totalRows": response.total_rows,
            "rows": [doc.json for doc in response.docs()],
        }

    async def get_metric_issues(self, metric) -> list[JsonDict]:
        assert self.db_issues is not None

        issues = []
        async for doc in self.db_issues.find({"scope_type": "metric", "scope": metric}):
            assert doc.data is not None
            # again, this is only mypy. can't find a document that does not
            # exist, hence doc.data can't be None
            issues.append(doc.data)

        return issues
