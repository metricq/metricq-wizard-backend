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

import metricq
from aiohttp.web import RouteTableDef
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from ..metricq import Configurator
from .models import MetricDatabaseConfiguration

routes = RouteTableDef()

logger = metricq.get_logger()
logger.setLevel("DEBUG")


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


@routes.post("/api/metrics/database")
async def post_metric_list(request: Request):
    client: Configurator = request.app["metricq_client"]

    data = await request.json()
    metric_database_configuration = MetricDatabaseConfiguration(**data)

    await client.update_metric_database_config(metric_database_configuration)

    return Response(
        text=metric_database_configuration.json(by_alias=True),
        content_type="application/json",
    )


@routes.get("/api/databases")
async def get_db_list(request: Request):
    client: Configurator = request.app["metricq_client"]
    config_dict = await client.get_configs()
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
async def post_metric_list(request: Request):
    logger.debug(f"Reconfiguring {request.match_info['database_id']}")
    return Response(text="Hello, {}".format(request.match_info["database_id"]))
