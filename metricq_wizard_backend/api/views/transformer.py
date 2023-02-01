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
from aiohttp import web_exceptions
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef
from aiohttp_swagger import swagger_path

from metricq_wizard_backend.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/transformers")
async def get_transformer_list(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    tokens = await configurator.get_client_tokens()
    transformers = []
    for token in tokens:
        if token.startswith("transformer-"):
            transformers.append(
                {
                    "id": token,
                    "isCombinator": "combinator" in token.lower(),
                }
            )

    return Response(text=json.dumps(transformers), content_type="application/json")


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
                "expression": expression["expression"],
                "configHash": expression["config_hash"],
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
    config_hash = request_data.get("configHash")

    if new_expression and config_hash:
        if await configurator.update_combined_metric_expression(
            transformer_id, metric_id, new_expression, config_hash
        ):
            return Response(
                status=204,
                content_type="application/json",
            )

    raise web_exceptions.HTTPBadRequest
