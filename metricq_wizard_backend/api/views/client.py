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
from aiohttp.web_request import Request
from aiohttp.web_response import Response, json_response
from aiohttp.web_routedef import RouteTableDef
from aiohttp_swagger import swagger_path

from metricq_wizard_backend.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


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


@swagger_path("api_doc/backup_list_client.yaml")
@routes.get("/api/client/{client_id}/backups")
async def get_client_backup_list(request: Request):
    client_id = request.match_info["client_id"]
    configurator: Configurator = request.app["metricq_client"]

    backup_list = await configurator.fetch_config_backups(token=client_id)

    print(backup_list)

    return Response(
        text=json.dumps(backup_list),
        content_type="application/json",
    )


@swagger_path("api_doc/backup_list_client.yaml")
@routes.get("/api/client/{client_id}/backup/{backup_id}")
async def get_client_backup(request: Request):
    client_id = request.match_info["client_id"]
    backup_id = request.match_info["backup_id"]

    configurator: Configurator = request.app["metricq_client"]

    backup = await configurator.fetch_config_backup(
        token=client_id, backup_id=backup_id
    )

    return Response(
        text=json.dumps(backup),
        content_type="application/json",
    )
