import asyncio
import math
import re
import traceback
from contextlib import suppress
from typing import Any, Coroutine

from aiocouch import CouchDB, Database
from metricq import HistoryClient, Timedelta, Timestamp
from metricq.exceptions import HistoryError
from metricq.logging import get_logger

JsonDict = dict[str, Any]

logger = get_logger()
logger.setLevel("INFO")


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
        await asyncio.gather(*self.pending, return_exceptions=True)

        assert all(task.done() for task in self.pending)

        self.pending = set()


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
        return self.lock.locked()

    async def run_once(self) -> None:
        if self.lock.locked():
            raise RuntimeError("Scan already running")

        async with self.lock:
            logger.warn("Starting Cluster Health Scan")
            try:
                await self._run_scan()
            except Exception as e:
                logger.error(f"Cluster Scan failed: {e}")
                logger.error("".join(traceback.format_exception(e)))
            finally:
                logger.warn("Cluster Health Scan Finished")

    async def _run_scan(self) -> None:
        # TODO add check for (db) queue bindings
        # TODO add check for token names

        async with HistoryClient(self.token, self.url, add_uuid=True) as client:
            tasks = AsyncTaskPool(max_tasks=250)

            async for doc in self.db_metadata.docs():
                metric = doc.id
                metadata = doc.data
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
        type: str,
        scope_type: str,
        scope: str,
        date: str = None,
        severity: str = None,
        **kwargs: Any,
    ):
        report = await self.db_issues.create(
            id=f"{type}-{scope_type}-{scope}", exists_ok=True
        )

        report["severity"] = "warning" if severity is None else severity

        if "first_detection_date" not in report:
            # only set first_detection_date when creating the report, not
            # on updates
            report["first_detection_date"] = (
                str(Timestamp.now().datetime.astimezone()) if date is None else date
            )

        report["date"] = (
            str(Timestamp.now().datetime.astimezone()) if date is None else date
        )

        report["type"] = type
        report["scope_type"] = scope_type
        report["scope"] = scope

        # entries in the new kwargs should overwrite existing entries
        for key, val in kwargs.items():
            report[key] = val

        await report.save()

    async def delete_issue_report(
        self,
        type: str,
        scope_type: str,
        scope: str,
    ):
        report = await self.db_issues.create(
            id=f"{type}-{scope_type}-{scope}", exists_ok=True
        )
        if report.exists:
            await report.delete()

    async def check_metric_metadata(self, metric, metadata):
        try:
            source = metadata["source"]
        except KeyError:
            source = None

        # This check is extra from missing_metadata, because it is a bit
        # more important, but new. We want to enforce that every metric has
        # to be either historic or not historic, i.e. only live. Or in other
        # words, not setting it is not an option.
        if "historic" not in metadata or not isinstance(metadata["historic"], bool):
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                type="missing_historic",
                severity="warning",
                source=source,
            )
        else:
            await self.delete_issue_report(
                scope_type="metric",
                scope=metric,
                type="missing_historic",
            )

        missing_metadata = []

        if "rate" not in metadata or not isinstance(metadata["rate"], float):
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

        if missing_metadata:
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                type="missing_metadata",
                severity="error" if "source" in missing_metadata else "info",
                source=source,
                missing_metadata=missing_metadata,
            )
        else:
            await self.delete_issue_report(
                scope_type="metric",
                scope=metric,
                type="missing_metadata",
            )

    async def check_metric_is_dead(
        self, client: HistoryClient, metric: str, metadata: JsonDict
    ) -> None:
        # TODO tolerance is rather high, because in prod, checks seem to
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

        try:
            result = await client.history_last_value(metric, timeout=60)

            if result is None:
                # No data points stored yet. This is bad.
                await self.create_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="no_value",
                    severity="warning",
                    source=metadata.get("source"),
                )
                return

            # we have a valid result, hence, there are stored data points.
            await self.delete_issue_report(
                scope_type="metric",
                scope=metric,
                type="no_value",
            )

            age = Timestamp.now() - result.timestamp

            # Archived metrics are supposed to not receive new data points.
            # For such metrics, the archived metadata is the ISO8601 string, when
            # the metric was archived.
            if age > allowed_age and not metadata.get("archived"):
                # We haven't received a new data point in a while and the metric
                # wasn't archived => It's dead, Jimmy.
                await self.create_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="dead",
                    severity="error",
                    last_timestamp=str(result.timestamp.datetime.astimezone()),
                    source=metadata.get("source"),
                )
                # if the metric is dead, it can't be undead as well
                await self.delete_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="undead",
                )
            elif age <= allowed_age and metadata.get("archived"):
                # the metric is archived, but we recently received a new data point
                # => Zombies are here, back in my dayz, you'd reload your hatchet now.
                await self.create_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="undead",
                    severity="warning",
                    last_timestamp=str(result.timestamp.datetime.astimezone()),
                    source=metadata.get("source"),
                    archived=metadata.get("archived"),
                )
                # if the metric is undead, it can't be dead as well
                await self.delete_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="dead",
                )
            else:
                # this is the happy case, everything's fine.
                await self.delete_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="dead",
                )
                await self.delete_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="undead",
                )

            # if we got here, the metric didn't time out. so remove those reports
            await self.delete_issue_report(
                scope_type="metric",
                scope=metric,
                type="timeout",
            )

        except asyncio.TimeoutError:
            # this likely means that the bindings for this metric is borked
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                severity="warning",
                type="timeout",
                source=metadata.get("source"),
            )
        except HistoryError as e:
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                type="errored",
                severity="info",
                error=str(e),
                source=metadata.get("source"),
            )

    async def check_metric_for_infinites(
        self,
        client: HistoryClient,
        metric: str,
        metadata: JsonDict,
    ) -> None:
        start_time = Timestamp.from_iso8601("1970-01-01T00:00:00.0Z")
        end_time = Timestamp.from_now(Timedelta.from_string("7d"))

        try:
            result = await client.history_aggregate(
                metric, start_time=start_time, end_time=end_time, timeout=60
            )
            if result.count and (
                not math.isfinite(result.minimum) or not math.isfinite(result.maximum)
            ):
                await self.create_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="infinite",
                    severity="info",
                    last_timestamp=str(result.timestamp.datetime.astimezone()),
                    source=metadata.get("source"),
                )
            else:
                await self.delete_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="infinite",
                )

        except asyncio.TimeoutError:
            # we should see this in the dead metrics check as well, so don't bother here.
            pass
        except HistoryError as e:
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                type="errored",
                severity="info",
                error=str(e),
                source=metadata.get("source"),
            )

    async def check_metric_name(self, metric: str):
        if not re.match(r"([a-zA-Z][a-zA-Z0-9_]+\.)+[a-zA-Z][a-zA-Z0-9_]+", metric):
            doc = await self.db_metadata.get(metric)
            await self.create_issue_report(
                scope_type="metric",
                scope=metric,
                type="invalid_name",
                severity="info",
                source=doc.get("source"),
            )
        else:
            await self.delete_issue_report(
                scope_type="metric",
                scope=metric,
                type="invalid_name",
            )

    async def find_issues(self, currentPage, perPage, sortBy, sortDesc, **kwargs):
        skip = (currentPage - 1) * perPage
        limit = perPage

        if sortBy == "id":
            view = self.db_issues.all_docs
        elif sortBy == "severity":
            view = self.db_issues.view("sortedBy", "severity")
        elif sortBy == "scope":
            view = self.db_issues.view("sortedBy", "scope")
        elif sortBy == "issue":
            view = self.db_issues.view("sortedBy", "type")

        response = await view.get(
            include_docs=True, limit=limit, skip=skip, descending=sortDesc
        )
        return {
            "totalRows": response.total_rows,
            "rows": [doc.data for doc in response.docs()],
        }
