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
from aiohttp.web_exceptions import HTTPBadRequest
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp_swagger import swagger_path

from ..metricq import Configurator
from .models import MetricDatabaseConfiguration
from ..metricq.source_plugin import AddMetricItem

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


@routes.post("/api/metrics")
async def post_metric_list(request: Request):
    client: Configurator = request.app["metricq_client"]
    request_data = await request.json()
    if "requested_metrics" in request_data:
        requested_metrics = request_data.get("requested_metrics", [])

        metric_dict = await client.get_metrics(format="object")
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
        for metric_id in metric_dict:
            metric = metric_dict[metric_id]
            metric["id"] = metric_id
            metric_list.append(metric)
    elif "source" in request_data:
        requested_source = request_data["source"]
        metric_dict = await client.get_metrics(source=requested_source, format="object")
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
async def post_metric_list(request: Request):
    logger.debug(f"Reconfiguring {request.match_info['database_id']}")
    return Response(text="Hello, {}".format(request.match_info["database_id"]))


@swagger_path("api_doc/get_source_list.yaml")
@routes.get("/api/sources")
async def get_source_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()
    source_list = []
    for config_id, config in config_dict.items():
        if config_id.startswith("source-"):
            try:
                source_list.append({"id": config_id, "configurable": "type" in config})
            except KeyError:
                logger.error(f"Config of source {config_id} is incorrect! Missing key")

    return Response(text=json.dumps(source_list), content_type="application/json")


@swagger_path("api_doc/get_source_config_items.yaml")
@routes.get("/api/source/{source_id}/config_items")
async def get_source_config_items(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    return Response(
        text=json.dumps(
            [
                config_item.dict()
                for config_item in source_plugin.get_configuration_items()
            ]
        ),
        content_type="application/json",
    )


@swagger_path("api_doc/add_source_config_item.yaml")
@routes.post("/api/source/{source_id}/config_items")
async def add_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    request_data = await request.json()

    config_item = await source_plugin.add_config_item(request_data)

    return Response(text=config_item.json(), content_type="application/json")


@swagger_path("api_doc/get_source_metrics_for_config_item.yaml")
@routes.get("/api/source/{source_id}/config_item/{config_item_id}/metrics")
async def get_source_metrics_for_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    metric_list = await source_plugin.get_metrics_for_config_item(config_item_id)

    return Response(
        text=json.dumps([metric.dict() for metric in metric_list]),
        content_type="application/json",
    )


@swagger_path("api_doc/add_source_metrics_for_config_item.yaml")
@routes.post("/api/source/{source_id}/config_item/{config_item_id}/metrics")
async def add_source_metrics_for_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    request_data = await request.json()
    if "metrics" not in request_data:
        raise HTTPBadRequest

    new_metrics = await source_plugin.add_metrics_for_config_item(
        config_item_id, [AddMetricItem(**metric) for metric in request_data["metrics"]]
    )

    return Response(
        text=json.dumps({"metrics": new_metrics}), content_type="application/json"
    )


@routes.get("/api/source/{source_id}/config_items/input_form")
async def get_source_add_config_item_input_form(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    return Response(
        text=json.dumps(source_plugin.input_form_add_config_item()),
        content_type="application/json",
    )


@routes.get("/api/source/{source_id}/config_item/{config_item_id}/input_form")
async def get_source_edit_config_item_input_form(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    return Response(
        text=json.dumps(source_plugin.input_form_edit_config_item()),
        content_type="application/json",
    )


@swagger_path("api_doc/get_source_config_item.yaml")
@routes.get("/api/source/{source_id}/config_item/{config_item_id}")
async def get_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    config_item_config = await source_plugin.get_config_item(config_item_id)

    return Response(
        text=json.dumps(config_item_config), content_type="application/json"
    )


@swagger_path("api_doc/update_source_config_item.yaml")
@routes.post("/api/source/{source_id}/config_item/{config_item_id}")
async def update_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    request_data = await request.json()

    config_item = await source_plugin.update_config_item(config_item_id, request_data)

    return Response(text=config_item.json(), content_type="application/json")


@swagger_path("api_doc/delete_source_config_item.yaml")
@routes.delete("/api/source/{source_id}/config_item/{config_item_id}")
async def delete_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    await source_plugin.delete_config_item(config_item_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )


@routes.get("/api/source/{source_id}/input_form")
async def get_source_edit_global_config_input_form(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    return Response(
        text=json.dumps(await source_plugin.input_form_edit_global_config()),
        content_type="application/json",
    )


@swagger_path("api_doc/get_source_config.yaml")
@routes.get("/api/source/{source_id}")
async def get_source_global_config(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    source_global_config = await source_plugin.get_global_config()

    return Response(
        text=json.dumps(source_global_config), content_type="application/json"
    )


@swagger_path("api_doc/update_source_config.yaml")
@routes.post("/api/source/{source_id}")
async def update_source_global_config(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(source_id=source_id)

    request_data = await request.json()

    source_global_config = await source_plugin.update_global_config(request_data)

    return Response(
        text=json.dumps(source_global_config), content_type="application/json"
    )


@swagger_path("api_doc/save_source_config.yaml")
@routes.post("/api/source/{source_id}/save")
async def save_source_config(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    await configurator.save_source_config(source_id=source_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )


@swagger_path("api_doc/reconfigure_source.yaml")
@routes.post("/api/source/{source_id}/reconfigure")
async def reconfigure_source(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    if not request.app["settings"].dry_run:
        await configurator.reconfigure_client(client_id=source_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )


@swagger_path("api_doc/save_config_and_reconfigure_source.yaml")
@routes.post("/api/source/{source_id}/save_reconfigure")
async def save_config_and_reconfigure_source(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    await configurator.save_source_config(source_id=source_id)
    if not request.app["settings"].dry_run:
        await configurator.reconfigure_client(client_id=source_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )


@swagger_path("api_doc/get_client_list.yaml")
@routes.get("/api/clients")
async def get_client_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()

    return Response(
        text=json.dumps([{"id": config_id} for config_id in config_dict]),
        content_type="application/json",
    )


@swagger_path("api_doc/reconfigure_client.yaml")
@routes.post("/api/client/{client_id}/reconfigure")
async def reconfigure_client(request: Request):
    client_id = request.match_info["client_id"]
    configurator: Configurator = request.app["metricq_client"]
    if not request.app["settings"].dry_run:
        await configurator.reconfigure_client(client_id=client_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )
