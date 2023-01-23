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

import metricq

from aiohttp.web_request import Request
from aiohttp.web import json_response
from aiohttp.web_routedef import RouteTableDef

from metricq_wizard_backend.metricq import Configurator
from metricq_wizard_backend.metricq.network import Network

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/explorer/{metric}")
async def get_metric_metadata(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    metric = request.match_info["metric"]

    network = Network(metric, configurator)

    return json_response(await network.search())
