# metricq-wizard
# Copyright (C) 2019 ZIH, Technische Universitaet Dresden, Federal Republic of Germany
#
# All rights reserved.
#
# This file is part of metricq-wizard.
#
# metricq-wizard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# metricq-wizard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with metricq-wizard.  If not, see <http://www.gnu.org/licenses/>.
import json
import math

import metricq
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef

from metricq_wizard_backend.api.models import MetricDatabaseConfigurations
from metricq_wizard_backend.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/metrics")
async def get_metric_list(request: Request):
    client: Configurator = request.app["metricq_client"]
    infix = request.query.get("infix", None)
    metric_dict = await client.get_metrics(infix=infix, format="object")
    metric_list = []
    for metric_id in metric_dict:
        metric = metric_dict[metric_id]
        metric["id"] = metric_id
        metric_list.append(metric)

    return Response(text=json.dumps(metric_list), content_type="application/json")


@routes.post("/api/metrics")
async def post_metric_list(request: Request):
    client: Configurator = request.app["metricq_client"]
    request_data = await request.json()
    if "requested_metrics" in request_data:
        requested_metrics = request_data.get("requested_metrics", [])

        metric_dict = await client.get_metrics(
            format="object", selector=requested_metrics
        )
        metric_list = []
        for metric_id in requested_metrics:
            if metric_id in metric_dict:
                metric = metric_dict[metric_id]
                metric["id"] = metric_id
                metric_list.append(metric)
            else:
                metric = {"id": metric_id}
                metric_list.append(metric)
    elif "database" in request_data:
        requested_database = request_data["database"]

        # TODO filter db

        metric_dict = await client.get_metrics(historic=True, format="object")
        metric_list = []
        for metric_id, metric in metric_dict.items():
            metric["id"] = metric_id
            metric_list.append(metric)
    elif "source" in request_data:
        requested_source = request_data["source"]
        metric_dict = await client.get_metrics(source=requested_source, format="object")
        metric_list = []
        for metric_id, metric in metric_dict.items():
            metric["id"] = metric_id
            metric_list.append(metric)

    return Response(text=json.dumps(metric_list), content_type="application/json")


def _get_interval_max_ms(interval_min_ms: int, interval_factor: int) -> int:
    ms_a_day = 24 * 60 * 60e3
    n = int(math.log(ms_a_day / interval_min_ms, interval_factor))
    if n < 0:
        n = 0
    if interval_min_ms * (interval_factor ** n) >= ms_a_day:
        return interval_min_ms * (interval_factor ** n)
    return interval_min_ms * (interval_factor ** (n + 1))


@routes.post("/api/metrics/database/defaults")
async def post_metric_database_default_config(request: Request):
    client: Configurator = request.app["metricq_client"]
    request_data = await request.json()

    selected_metrics = request_data.get("selectedMetrics", [])

    metric_list = []

    if selected_metrics:
        metric_dict = await client.get_metrics(
            format="object", selector=selected_metrics
        )
        logger.debug(metric_dict)
        for metric_id, metric_config in metric_dict.items():
            if "historic" not in metric_config or not metric_config["historic"]:
                try:
                    metric_list.append(
                        {
                            "id": metric_id,
                            "intervalMin": f"{int(40e3 / float(metric_config['rate'])) or 1:d}ms",
                            "intervalMax": f"{_get_interval_max_ms(int(40e3 / float(metric_config['rate'])) or 1, 10):d}ms",
                            "intervalFactor": 10,
                        }
                    )
                except ValueError:
                    logger.warning(
                        f"Metric {metric_id} has invalid rate: {metric_config['rate']}"
                    )

    return Response(text=json.dumps(metric_list), content_type="application/json")


@routes.post("/api/metrics/database")
async def post_metric_database(request: Request):
    client: Configurator = request.app["metricq_client"]
    request_data = await request.json()

    database_configs = MetricDatabaseConfigurations(**request_data)
    await client.update_metric_database_config(database_configs.database_configurations)

    return Response(
        text=database_configs.json(by_alias=True),
        content_type="application/json",
    )


@routes.get("/api/databases")
async def get_db_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()
    db_list = []
    for config_id in config_dict.keys():
        if config_id.startswith("db-"):
            try:
                db_list.append({"id": config_id})
            except KeyError:
                logger.error(
                    f"Config of database {config_id} is incorrect! Missing key"
                )
            except AttributeError:
                logger.error(
                    f"Config of database {config_id} is incorrect! 'metrics' is list not dict"
                )

    return Response(text=json.dumps(db_list), content_type="application/json")


@routes.post("/api/databases/historic_metrics")
async def post_db_list_with_historic_metrics(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()
    data = await request.json()
    db_list = []
    for config_id, config in config_dict.items():
        if config_id.startswith("db-"):
            try:
                db_list.append(
                    {
                        "id": config_id,
                        "metrics": [
                            {
                                "id": metric_id,
                                "databaseId": config_id,
                                "intervalMin": f"{metric_config['interval_min'] / 1e6:.0f}ms",
                                "intervalMax": f"{metric_config['interval_max'] / 1e6:.0f}ms",
                                "intervalFactor": metric_config["interval_factor"],
                            }
                            for metric_id, metric_config in config["metrics"].items()
                            if metric_id in data["selectedMetrics"]
                        ],
                    }
                )
            except KeyError:
                logger.error(
                    f"Config of database {config_id} is incorrect! Missing key"
                )
            except AttributeError:
                logger.error(
                    f"Config of database {config_id} is incorrect! 'metrics' is list not dict"
                )

    return Response(text=json.dumps(db_list), content_type="application/json")


@routes.post("/api/database/{database_id}/reconfigure")
async def reconfigure_database(request: Request):
    database_id = request.match_info["database_id"]
    configurator: Configurator = request.app["metricq_client"]
    if not request.app["settings"].dry_run:
        await configurator.reconfigure_client(client_id=database_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )
