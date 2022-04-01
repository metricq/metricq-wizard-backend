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

import aiohttp
import metricq
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef
from pathlib import Path

from metricq_wizard_backend.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/explorer")
async def get_metrics(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    #alle metriken
    config_dict = await configurator.get_metrics(historic=True, infix= "ariel", limit = 10)
    return Response(
        text=json.dumps(config_dict),
        content_type="application/json",
    )

@routes.get("/api/explorer/{metric}")
async def get_metric_metadata(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    metric = request.match_info["metric"]

    with open(str(Path.home())+'/Programmierung/login/rabbitmq.txt') as f:
        login = f.read().splitlines()

    answer = {}
    nodes = {}
    agents = {}
    edges = {}
    layout = {}

    x_depth = 0
    y_depth = {0:0}
    nodes[metric] = {'name': metric, 'type': 'circle'}
    layout[metric] = { 'x':x_depth, 'y':y_depth[x_depth]}

    await backward(configurator, metric, nodes, agents, edges, layout, x_depth-1, y_depth)


    exchange = {}
    async with aiohttp.ClientSession() as session:
        async with session.get('https://rabbitmq.metricq.zih.tu-dresden.de/api/exchanges/data/metricq.data/bindings/source', auth=aiohttp.BasicAuth(login[0], login[1])) as resp:
            resp = await resp.json()
            for binding in resp:
                routing_key = binding['routing_key']
                destination = binding['destination'][:-5]
                exchange.setdefault(routing_key, []).append(destination)

    if metric in exchange:
        print(exchange[metric])
        for binding in exchange[metric]:
            agents[binding] = {'name': binding, 'type': 'rect'}
            layout[binding] = {'x': (x_depth + 1) * 100, 'y': 0}
            edges[metric + 'to' + binding] = {'source': metric, 'target': binding}
            if binding.startswith('transformer'):
                binding_dict = (await configurator.get_configs([binding]))[binding]['metrics']
                answer['resp'] = binding_dict
                if binding.endswith('combinator'):
                    pass
                elif binding.endswith('aggregator'):
                    for key, value in binding_dict.items():
                        if metric == value['source']:
                            nodes[key] = {'name': key, 'type': 'circle'}
                            layout[key] = {'x': (x_depth + 2) * 100, 'y': 0}
                            edges[binding + 'to' + key] = {'source': binding, 'target': key}



    answer['nodes'] = {**nodes, **agents}
    answer['edges'] = edges
    answer['layout'] = layout

    #answer['resp'] = exchange

    return Response(
        text=json.dumps(answer),
        content_type="application/json",
    )

async def backward(configurator, metric, nodes, agents, edges, layout, x_depth, y_depth):
    metadata_dict = await configurator.fetch_metadata([metric])
    metric_metadata = metadata_dict[next(iter(metadata_dict))]
    metric_id = metric_metadata["_id"]
    metric_source = metric_metadata["source"]
    y_depth[x_depth] = 0
    if metric_source not in agents:
        agents[metric_source] = {'name': metric_source, 'type': 'rect'}
        layout[metric_source] = { 'x':x_depth*100, 'y':y_depth[x_depth]}

    edges[metric_source + 'to' + metric_id] = {'source': metric_source, 'target': metric_id}

    if metric_source.startswith("transformer"):
        if metric_source.endswith("combinator"):
            display_expression = metric_metadata["display_expression"].split("(")
            display_expression = display_expression[-1].split(")")
            display_expression = display_expression[0].split(", ")
            for metric_summand in display_expression:
                if metric_summand not in nodes:
                    nodes[metric_summand] = {'name': metric_summand, 'type': 'circle'}
                    if x_depth-1 not in y_depth:
                        y_depth[x_depth-1] = 0
                    else:
                        y_depth[x_depth - 1] += 75
                    layout[metric_summand] = {'x': (x_depth-1) * 100, 'y': y_depth[x_depth-1]}
                    await backward(configurator, metric_summand, nodes, agents, edges, layout, x_depth-2, y_depth)
                edges[metric_summand + 'to' + metric_source] = {'source': metric_summand, 'target': metric_source}

        elif metric_source.endswith("aggregator"):
            metric_primary = metric_metadata["primary"]
            if metric_primary not in nodes:
                nodes[metric_primary] = {'name': metric_primary, 'type': 'circle'}
                if x_depth - 1 not in y_depth:
                    y_depth[x_depth - 1] = 0
                else:
                    y_depth[x_depth - 1] += 75
                layout[metric_primary] = {'x': (x_depth-1) * 100, 'y': y_depth[x_depth-1]}
                await backward(configurator, metric_primary, nodes, agents, edges, layout, x_depth-2, y_depth)
            edges[metric_primary + 'to' + metric_source] = {'source': metric_primary, 'target': metric_source}

    else:
        pass