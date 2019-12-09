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
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()
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


@routes.get("/api/sources")
async def get_source_list(request: Request):
    """

    :param request:
    :return:
    ---
    description: Get list of configured sources
    tags:
    - Sources
    produces:
    - application/json
    """
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()
    source_list = []
    for config_id, config in config_dict.items():
        if config_id.startswith("source-"):
            try:
                source_list.append({"id": config_id})
            except KeyError:
                logger.error(f"Config of source {config_id} is incorrect! Missing key")

    return Response(text=json.dumps(source_list), content_type="application/json")


@routes.get("/api/source/{source_id}/get_available_metrics/input_form")
async def get_available_metrics_input_form(request: Request):
    """

    :param request:
    :return:
    ---
    description: Get list of configured sources
    tags:
    - Sources
    parameters:
    - in: path
      name: source_id
      required: true
      description: Numeric ID of the user to get
    produces:
    - application/json
    """
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    return Response(
        text=json.dumps(source_plugin.input_form_get_available_metrics()),
        content_type="application/json",
    )


@routes.post("/api/source/{source_id}/get_available_metrics")
async def get_available_metrics(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    data = await request.json()
    source_metric_list_configuration = source_plugin.input_model_get_available_metrics()(
        **data
    )

    metric_list = await source_plugin.get_available_metrics(
        source_metric_list_configuration
    )

    return Response(text=json.dumps(metric_list), content_type="application/json")


@routes.get("/api/source/{source_id}/create_new_metric/input_form")
async def create_new_metric_input_form(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    return Response(
        text=json.dumps(source_plugin.input_form_create_new_metric()),
        content_type="application/json",
    )


@routes.post("/api/source/{source_id}/create_new_metric")
async def create_new_metric(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    data = await request.json()
    source_metric_configuration = source_plugin.input_model_create_new_metric()(**data)

    config = await configurator.get_configs(selector=source_id)
    if not config or source_id not in config:
        # TODO return 404
        pass

    new_config = await source_plugin.create_new_metric(
        source_metric_configuration, config[source_id]
    )

    logger.debug(new_config)

    await configurator.set_config(source_id, new_config)

    return Response(
        text=source_metric_configuration.json(by_alias=True),
        content_type="application/json",
    )
