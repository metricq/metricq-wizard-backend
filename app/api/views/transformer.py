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
from aiohttp import web_exceptions

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef

import metricq
from aiohttp_swagger import swagger_path

from app.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/transformers")
async def get_transformer_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    config_dict = await configurator.get_configs()
    transformer_list = []
    for config_id, config in config_dict.items():
        if config_id.startswith("transformer-"):
            try:
                transformer_list.append(
                    {
                        "id": config_id,
                        "isCombinator": "combinator" in config_id.lower(),
                    }
                )
            except KeyError:
                logger.error(
                    f"Config of transformer {config_id} is incorrect! Missing key"
                )

    return Response(text=json.dumps(transformer_list), content_type="application/json")


@swagger_path("api_doc/transformer/get_combinator_metric_expression.yaml")
@routes.get("/api/transformer/{transformer_id}/{metric_id}")
async def get_combinator_metric_expression(request: Request):
    transformer_id = request.match_info["transformer_id"]
    metric_id = request.match_info["metric_id"]
    configurator: Configurator = request.app["metricq_client"]
    expression = await configurator.get_combined_metric_expression(
        transformer_id, metric_id
    )
    if expression is None:
        raise web_exceptions.HTTPNotFound

    return Response(
        text=json.dumps(
            {
                "transformerId": transformer_id,
                "metric": metric_id,
                "expression": expression,
            }
        ),
        content_type="application/json",
    )


@swagger_path("api_doc/transformer/put_combinator_metric_expression.yaml")
@routes.put("/api/transformer/{transformer_id}/{metric_id}")
async def put_combinator_metric_expression(request: Request):
    transformer_id = request.match_info["transformer_id"]
    metric_id = request.match_info["metric_id"]
    configurator: Configurator = request.app["metricq_client"]

    request_data = await request.json()

    new_expression = request_data.get("expression")

    if new_expression:
        if await configurator.create_combined_metric(
            transformer_id, metric_id, new_expression
        ):
            return Response(
                status=204,
                content_type="application/json",
            )

    raise web_exceptions.HTTPBadRequest


@swagger_path("api_doc/transformer/patch_combinator_metric_expression.yaml")
@routes.patch("/api/transformer/{transformer_id}/{metric_id}")
async def patch_combinator_metric_expression(request: Request):
    transformer_id = request.match_info["transformer_id"]
    metric_id = request.match_info["metric_id"]
    configurator: Configurator = request.app["metricq_client"]

    request_data = await request.json()

    new_expression = request_data.get("expression")

    if new_expression:
        if await configurator.update_combined_metric_expression(
            transformer_id, metric_id, new_expression
        ):
            return Response(
                status=204,
                content_type="application/json",
            )

    raise web_exceptions.HTTPBadRequest
