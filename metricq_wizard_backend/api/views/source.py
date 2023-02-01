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
from aiohttp.web_exceptions import HTTPBadRequest
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef
from aiohttp_swagger import swagger_path

from metricq_wizard_backend.metricq import Configurator
from metricq_wizard_backend.metricq.source_plugin import AddMetricItem

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@swagger_path("api_doc/get_source_list.yaml")
@routes.get("/api/sources")
async def get_source_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    configs = await configurator.get_configs("^source-.*")
    source_list = []
    for token, config in configs.items():
        source_list.append(
            {
                "id": token,
                "configurable": "type" in config,
                "type": config.get("type"),
            }
        )

    return Response(text=json.dumps(source_list), content_type="application/json")


@swagger_path("api_doc/get_source_config_items.yaml")
@routes.get("/api/source/{source_id}/config_items")
async def get_source_config_items(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    return Response(
        text=json.dumps(
            {
                "configItemName": source_plugin.get_config_item_name(),
                "configItems": [
                    config_item.dict()
                    for config_item in await source_plugin.get_configuration_items()
                ],
            }
        ),
        content_type="application/json",
    )


@swagger_path("api_doc/add_source_config_item.yaml")
@routes.post("/api/source/{source_id}/config_items")
async def add_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    request_data = await request.json()

    config_item = await source_plugin.add_config_item(request_data)

    return Response(text=config_item.json(), content_type="application/json")


@swagger_path("api_doc/get_source_metrics_for_config_item.yaml")
@routes.get("/api/source/{source_id}/config_item/{config_item_id}/metrics")
async def get_source_metrics_for_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    metric_list = await source_plugin.get_metrics_for_config_item(config_item_id)

    return Response(
        text=metric_list.json(by_alias=True), content_type="application/json"
    )


@swagger_path("api_doc/add_source_metrics_for_config_item.yaml")
@routes.post("/api/source/{source_id}/config_item/{config_item_id}/metrics")
async def add_source_metrics_for_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    request_data = await request.json()
    if "metrics" not in request_data:
        raise HTTPBadRequest

    not_selected_metric_ids = request_data.get("notSelectedMetricIds", [])

    new_metrics = await source_plugin.add_metrics_for_config_item(
        config_item_id,
        [AddMetricItem(**metric) for metric in request_data["metrics"]],
        not_selected_metric_ids,
    )

    return Response(
        text=json.dumps({"metrics": new_metrics}), content_type="application/json"
    )


@routes.get("/api/source/{source_id}/config_items/input_form")
async def get_source_add_config_item_input_form(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    return Response(
        text=json.dumps(source_plugin.input_form_add_config_item()),
        content_type="application/json",
    )


@routes.get("/api/source/{source_id}/config_item/{config_item_id}/input_form")
async def get_source_edit_config_item_input_form(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    return Response(
        text=json.dumps(source_plugin.input_form_edit_config_item()),
        content_type="application/json",
    )


@swagger_path("api_doc/get_source_config_item.yaml")
@routes.get("/api/source/{source_id}/config_item/{config_item_id}")
async def get_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    config_item_config = await source_plugin.get_config_item(config_item_id)

    return Response(
        text=json.dumps(config_item_config), content_type="application/json"
    )


@swagger_path("api_doc/update_source_config_item.yaml")
@routes.post("/api/source/{source_id}/config_item/{config_item_id}")
async def update_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    request_data = await request.json()

    config_item = await source_plugin.update_config_item(config_item_id, request_data)

    return Response(text=config_item.json(), content_type="application/json")


@swagger_path("api_doc/delete_source_config_item.yaml")
@routes.delete("/api/source/{source_id}/config_item/{config_item_id}")
async def delete_source_config_item(request: Request):
    source_id = request.match_info["source_id"]
    config_item_id = request.match_info["config_item_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    await source_plugin.delete_config_item(config_item_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )


@routes.get("/api/source/{source_id}/input_form")
async def get_source_edit_global_config_input_form(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    return Response(
        text=json.dumps(await source_plugin.input_form_edit_global_config()),
        content_type="application/json",
    )


@swagger_path("api_doc/get_source_config.yaml")
@routes.get("/api/source/{source_id}")
async def get_source_global_config(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    source_global_config = await source_plugin.get_global_config()

    return Response(
        text=json.dumps(source_global_config), content_type="application/json"
    )


@swagger_path("api_doc/update_source_config.yaml")
@routes.post("/api/source/{source_id}")
async def update_source_global_config(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    source_plugin = await configurator.get_source_plugin(
        source_id=source_id, session_key=session_key
    )

    request_data = await request.json()

    source_global_config = await source_plugin.update_global_config(request_data)

    return Response(
        text=json.dumps(source_global_config), content_type="application/json"
    )


@swagger_path("api_doc/save_source_config.yaml")
@routes.post("/api/source/{source_id}/save")
async def save_source_config(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    metrics = await configurator.save_source_config(
        source_id=source_id, session_key=session_key, unload_plugin=True
    )

    return Response(
        text=json.dumps({"status": "success", "metrics": metrics}),
        content_type="application/json",
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
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]
    metrics = await configurator.save_source_config(
        source_id=source_id, session_key=session_key, unload_plugin=True
    )
    if not request.app["settings"].dry_run:
        await configurator.reconfigure_client(client_id=source_id)

    return Response(
        text=json.dumps({"status": "success", "metrics": metrics}),
        content_type="application/json",
    )


@swagger_path("api_doc/get_source_raw_config.yaml")
@routes.get("/api/source/{source_id}/raw_config")
async def get_source_raw_config(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]
    config = await configurator.read_config(source_id)

    keys_to_filter = list(
        filter(lambda k: k.startswith("_") and not k == "_rev", config.keys())
    )

    for key in keys_to_filter:
        del config[key]

    return Response(
        text=json.dumps({"config": config}), content_type="application/json"
    )


@swagger_path("api_doc/save_source_raw_config.yaml")
@routes.post("/api/source/{source_id}/raw_config")
async def save_source_raw_config(request: Request):
    source_id = request.match_info["source_id"]
    configurator: Configurator = request.app["metricq_client"]

    request_data = await request.json()

    keys_to_filter = list(
        filter(lambda k: k.startswith("_") and not k == "_rev", request_data.keys())
    )

    for key in keys_to_filter:
        del request_data[key]

    await configurator.set_config(source_id, request_data)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )


# @swagger_path("api_doc/save_source_raw_config.yaml")
@routes.get("/api/source/{source_id}/session")
async def get_session_state(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]

    session = configurator.get_session(session_key)
    response = {
        "valid": await configurator.get_session_state(session_key, source_id),
        "creation_time": session.creation_time.datetime.isoformat(),
    }
    plugin_creation_time = session.get_source_plugin_creation_time(source_id)
    if plugin_creation_time is not None:
        response["plugin_creation_time"] = plugin_creation_time.datetime.isoformat()

    return Response(text=json.dumps(response), content_type="application/json")


# @swagger_path("api_doc/save_source_raw_config.yaml")
@routes.post("/api/source/{source_id}/session/reset")
async def post_reset_session(request: Request):
    source_id = request.match_info["source_id"]
    session_key = request.query.get("session")
    if session_key is None:
        raise HTTPBadRequest(reason="Missing session key")

    configurator: Configurator = request.app["metricq_client"]

    session = configurator.get_session(session_key)

    session.unload_source_plugin(source_id)

    return Response(
        text=json.dumps({"status": "success"}), content_type="application/json"
    )
