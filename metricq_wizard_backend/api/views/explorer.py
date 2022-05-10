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
from metricq_wizard_backend.metricq import Configurator
from metricq_wizard_backend.settings import Settings

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/explorer/{metric}")
async def get_metric_metadata(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    metric = request.match_info["metric"]

    settings: Settings = request.app["settings"]

    answer = {}
    nodes = {}
    agents = {}
    edges = {}
    layout = {}

    x_depth = 0
    y_depth = {0: 0}

    nodes[metric] = {'name': metric, 'type': 'circle'}
    create_node(nodes, metric, '#417534')
    layout[metric] = {'x': x_depth, 'y': y_depth[x_depth]}

    await backward(configurator, metric, nodes, agents, edges, layout, x_depth - 1, y_depth)

    exchange = {}
    async with aiohttp.ClientSession() as session:
        async with session.get(
                'https://rabbitmq.metricq.zih.tu-dresden.de/api/exchanges/data/metricq.data/bindings/source',
                auth=aiohttp.BasicAuth(settings.rabbitmq_user, settings.rabbitmq_password)) as resp:
            resp = await resp.json()
            for binding in resp:
                routing_key = binding['routing_key']
                destination = binding['destination'][:-5]
                exchange.setdefault(routing_key, []).append(destination)

    await forward(configurator, metric, nodes, agents, edges, layout, x_depth + 1, y_depth, exchange)

    answer['nodes'] = {**nodes, **agents}
    answer['edges'] = edges
    answer['layout'] = layout

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
        create_agent(agents, metric_source)
        layout[metric_source] = {'x': x_depth * 100, 'y': y_depth[x_depth]}

    edges[metric_source + 'to' + metric_id] = {'source': metric_source, 'target': metric_id}

    if metric_source.startswith("transformer"):
        if metric_source.endswith("combinator"):
            json_ends = []
            metric_source_dict = (await configurator.get_configs([metric_source]))[metric_source]['metrics'][metric]
            await searchJson(json_ends, metric_source_dict['expression'])
            for metric_summand in json_ends:
                try:
                    if metric_summand not in nodes:
                        create_node(nodes, metric_summand)
                        if x_depth - 1 not in y_depth:
                            y_depth[x_depth - 1] = 0
                        else:
                            y_depth[x_depth - 1] += 75
                        layout[metric_summand] = {'x': (x_depth - 1) * 100, 'y': y_depth[x_depth - 1]}
                        await backward(configurator, metric_summand, nodes, agents, edges, layout, x_depth - 2, y_depth)
                    edges[metric_summand + 'to' + metric_source] = {'source': metric_summand, 'target': metric_source}
                except Exception:
                    if metric_summand in nodes:
                        del nodes[metric_summand]
        elif metric_source.endswith("aggregator"):
            metric_primary = metric_metadata["primary"]
            if metric_primary not in nodes:
                create_node(nodes, metric_primary)
                if x_depth - 1 not in y_depth:
                    y_depth[x_depth - 1] = 0
                else:
                    y_depth[x_depth - 1] += 75
                layout[metric_primary] = {'x': (x_depth - 1) * 100, 'y': y_depth[x_depth - 1]}
                await backward(configurator, metric_primary, nodes, agents, edges, layout, x_depth - 2, y_depth)
            edges[metric_primary + 'to' + metric_source] = {'source': metric_primary, 'target': metric_source}


async def forward(configurator, metric, nodes, agents, edges, layout, x_depth, y_depth, exchange):
    if metric in exchange:
        for binding in exchange[metric]:
            if binding not in agents:
                if x_depth not in y_depth:
                    y_depth[x_depth] = 0
                else:
                    y_depth[x_depth] += 75
                create_agent(agents, binding)
                layout[binding] = {'x': x_depth * 100, 'y': y_depth[x_depth]}
            edges[metric + 'to' + binding] = {'source': metric, 'target': binding}
            if binding.startswith('transformer'):
                binding_dict = (await configurator.get_configs([binding]))[binding]['metrics']
                if binding.endswith('combinator'):
                    for key, value in binding_dict.items():
                        json_ends = []
                        await searchJson(json_ends, value['expression'])
                        for end in json_ends:
                            if metric == end:
                                if key not in nodes:
                                    if x_depth + 1 not in y_depth:
                                        y_depth[x_depth + 1] = 0
                                    else:
                                        y_depth[x_depth + 1] += 75
                                    create_node(nodes, key)
                                    layout[key] = {'x': (x_depth + 1) * 100, 'y': y_depth[x_depth + 1]}
                                edges[binding + 'to' + key] = {'source': binding, 'target': key}
                                await forward(configurator, key, nodes, agents, edges, layout, x_depth + 2, y_depth,
                                              exchange)
                elif binding.endswith('aggregator'):
                    for key, value in binding_dict.items():
                        if metric == value['source']:
                            if key not in nodes:
                                if x_depth + 1 not in y_depth:
                                    y_depth[x_depth + 1] = 0
                                else:
                                    y_depth[x_depth + 1] += 75
                                create_node(nodes, key)
                                layout[key] = {'x': (x_depth + 1) * 100, 'y': y_depth[x_depth + 1]}
                            edges[binding + 'to' + key] = {'source': binding, 'target': key}
                            await forward(configurator, key, nodes, agents, edges, layout, x_depth + 2, y_depth,
                                          exchange)


async def searchJson(json_ends, expression):
    if not isinstance(expression, dict) and not isinstance(expression, list):
        json_ends.append(expression)
    else:
        if isinstance(expression, dict):
            for key, value in expression.items():
                await searchJson(json_ends, value)
        elif isinstance(expression, list):
            for item in expression:
                await searchJson(json_ends, item)


def create_node(nodes, new_metric, color='#4aba4a'):
    nodes[new_metric] = {'name': new_metric, 'type': 'circle', 'color': color, 'direction': 'north'}


def create_agent(agents, new_agent):
    if new_agent.endswith('combinator'):
        color = '#55b1e3'
    elif new_agent.endswith('aggregator'):
        color = '#5b90bf'
    else:
        color = '#3abec8'
    agents[new_agent] = {'name': new_agent, 'type': 'rect', 'color': color, 'direction': 'south'}
