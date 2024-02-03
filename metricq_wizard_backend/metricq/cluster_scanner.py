import asyncio
import math
import re
from typing import Any

from aiocouch import CouchDB, Database
from metricq import HistoryClient, Timedelta, Timestamp
from metricq.exceptions import HistoryError
from metricq.logging import get_logger

JsonDict = dict[str, Any]

logger = get_logger()
logger.setLevel("INFO")


class ClusterScanner:
    def __init__(self, token: str, url: str, couch: CouchDB):
        self.token = token
        self.url = url
        self.couch = couch

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

    async def scan_cluster(self) -> None:
        if self.lock.locked():
            raise RuntimeError("Scan already running")

        async with self.lock():
            logger.warn("Starting Cluster Health Scan")

            # TODO add check for queue bindings

            async with HistoryClient(self.token, self.url, add_uuid=True) as client:

                async with asyncio.TaskGroup() as tasks:
                    async for metric, metadata in self.db_metadata.docs():
                        tasks.create_task(self.check_metric_metadata(metric, metadata),)
                        tasks.create_task(
                            self.check_metric_is_dead(client, metric, metadata)
                        )
                        tasks.create_task(
                            self.check_metric_for_infinites(client, metric, metadata)
                        )
                        # there is no tooling for renaming metrics, so bad
                        # names is nothing we should warn about yet.
                        # tasks.create_task( self.check_metric_name(metric))

                await asyncio.gather(*tasks)

            logger.warn("Cluster Health Scan Finished")

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
                severity="warn",
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

    async def check_metrics_for_dead(
        self, client: HistoryClient, metrics: dict[str, JsonDict]
    ) -> None:
        async def check_metric(metric: str, allowed_age: Timedelta) -> None:
            try:
                result = await client.history_last_value(metric, timeout=60)

                if result is None:
                    # No data points stored yet. This is bad.
                    await self.create_issue_report(
                        scope_type="metric",
                        scope=metric,
                        type="no_value",
                        severity="warning",
                        source=metrics[metric].get("source"),
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
                if age > allowed_age and not metrics[metric].get("archived"):
                    # We haven't received a new data point in a while and the metric
                    # wasn't archived => It's dead, Jimmy.
                    await self.create_issue_report(
                        scope_type="metric",
                        scope=metric,
                        type="dead",
                        severity="error",
                        last_timestamp=str(result.timestamp.datetime.astimezone()),
                        source=metrics[metric].get("source"),
                    )
                    # if the metric is dead, it can't be undead as well
                    await self.delete_issue_report(
                        scope_type="metric",
                        scope=metric,
                        type="undead",
                    )
                elif age <= allowed_age and metrics[metric].get("archived") is not None:
                    # the metric is archived, but we recently received a new data point
                    # => Zombies are here, back in my dayz, you'd reload your hatchet now.
                    await self.create_issue_report(
                        scope_type="metric",
                        scope=metric,
                        type="undead",
                        severity="warning",
                        last_timestamp=str(result.timestamp.datetime.astimezone()),
                        source=metrics[metric].get("source"),
                        archived=metrics[metric].get("archived"),
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
                    source=metrics[metric].get("source"),
                )
            except HistoryError as e:
                await self.create_issue_report(
                    scope_type="metric",
                    scope=metric,
                    type="errored",
                    severity="info",
                    error=str(e),
                    source=metrics[metric].get("source"),
                )

        def compute_allowed_age(metadata: JsonDict) -> Timedelta:
            # TODO tolerance is rather high, because in prod, checks seem to
            # take a while, which messes up the timings :(
            tolerance = Timedelta.from_string("1min")
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
                    tolerance += Timedelta.from_s(1 / rate)
            except KeyError:
                # Fall back to compute tolerance from interval
                try:
                    interval = metadata["interval"]
                    if isinstance(interval, str):
                        tolerance += Timedelta.from_string(interval)
                    elif isinstance(interval, (int, float)):
                        tolerance += Timedelta.from_s(interval)
                    else:
                        logger.error(
                            "Invalid interval: {} ({}) [{}]",
                            interval,
                            type(interval),
                            metadata,
                        )
                except KeyError:
                    pass
            return tolerance

        requests = [
            check_metric(metric, compute_allowed_age(metadata))
            for metric, metadata in metrics.items()
        ]

        for request in asyncio.as_completed(requests):
            await request

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

    async def check_metric_names(self):
        """
        Checks all metric names in the database against the regex.
        """
        async for metric in self.db_metadata.all_docs.ids():
            if metric.startswith("_design/"):
                # these are special, don't touch them
                continue

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
