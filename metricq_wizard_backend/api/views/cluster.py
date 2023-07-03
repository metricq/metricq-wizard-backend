# metricq-wizard
# Copyright (C) 2023 ZIH, Technische Universitaet Dresden, Federal Republic of Germany
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

import asyncio

import metricq
from aiohttp.web_request import Request
from aiohttp.web_response import json_response
from aiohttp.web_routedef import RouteTableDef
from aiohttp_swagger import swagger_path

from metricq_wizard_backend.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/cluster/issues")
async def get_client_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]

    return json_response(data=await configurator.get_cluster_issues())


@routes.post("/api/cluster/health_scan")
async def get_client_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]

    asyncio.create_task(configurator.scan_cluster())

    return json_response(data={"status": "created"}, status=202)
