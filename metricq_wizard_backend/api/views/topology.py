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


@swagger_path("api_doc/discover_topology.yaml")
@routes.post("/api/topology/discover")
async def update_topology(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    await configurator.discover()

    return json_response(data={"ok": "Processing update asynchronously."}, status=202)


@swagger_path("api_doc/discover.yaml")
@routes.get("/api/topology")
async def get_topology(request: Request):
    configurator: Configurator = request.app["metricq_client"]

    topology = await configurator.fetch_topology()

    return json_response(data=topology)
