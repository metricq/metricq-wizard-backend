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
from collections import defaultdict

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_routedef import RouteTableDef

from metricq_wizard_backend.metricq import Configurator

logger = metricq.get_logger()
logger.setLevel("DEBUG")

routes = RouteTableDef()


@routes.get("/api/explorer/{metric}")
async def get_metric_metadata(request: Request):
    configurator: Configurator = request.app["metricq_client"]
    metric = request.match_info["metric"]

    network = Network(metric, configurator)

    await network.backward(metric, 0)
    await network.forward(metric, 0)

    return Response(
        text=json.dumps(network.return_result()),
        content_type="application/json",
    )


class Network:
    def __init__(self, original_metric, configurator):
        self.configurator = configurator
        self.nodes = {}
        self.edges = {}
        self.layout = {}
        self.y_depth = defaultdict(int)
        self.add_metric(original_metric, "#417534")
        self.add_layout(original_metric, 0)

    def add_metric(self, new_metric, color="#4aba4a"):
        self.nodes[new_metric] = {
            "name": new_metric,
            "type": "circle",
            "color": color,
            "direction": "north",
        }

    def add_agent(self, new_agent):
        if new_agent.endswith("combinator"):
            color = "#55b1e3"
        elif new_agent.endswith("aggregator"):
            color = "#5b90bf"
        else:
            color = "#3abec8"
        self.nodes[new_agent] = {
            "name": new_agent,
            "type": "rect",
            "color": color,
            "direction": "south",
        }

    def add_edge(self, source, target):
        self.edges[source + "to" + target] = {"source": source, "target": target}

    def add_layout(self, target, x_depth):
        self.layout[target] = {"x": x_depth * 75, "y": self.y_depth[x_depth] * 75}
        self.y_depth[x_depth] += 1

    def return_result(self):
        return {"nodes": self.nodes, "edges": self.edges, "layout": self.layout}

    async def backward(self, metric, x_depth):
        metadata_dict = await self.configurator.fetch_metadata([metric])
        metric_metadata = metadata_dict[next(iter(metadata_dict))]
        metric_id = metric_metadata["_id"]
        metric_source = metric_metadata["source"]
        if metric_source not in self.nodes:
            self.add_agent(metric_source)
            self.add_layout(metric_source, x_depth - 1)

        self.add_edge(metric_source, metric_id)

        if metric_source.startswith("transformer"):
            if metric_source.endswith("combinator"):
                metric_source_dict = (
                    await self.configurator.get_configs([metric_source])
                )[metric_source]["metrics"][metric]
                json_ends = await self.search_json([], metric_source_dict["expression"])

                for metric_summand in json_ends:
                    try:
                        if metric_summand not in self.nodes:
                            self.add_metric(metric_summand)
                            await self.backward(metric_summand, x_depth - 2)
                            self.add_layout(metric_summand, x_depth - 2)
                        self.add_edge(metric_summand, metric_source)
                    except Exception:
                        if metric_summand in self.nodes:
                            del self.nodes[metric_summand]
            elif metric_source.endswith("aggregator"):
                metric_primary = metric_metadata["primary"]
                if metric_primary not in self.nodes:
                    self.add_metric(metric_primary)
                    self.add_layout(metric_primary, x_depth - 2)
                    await self.backward(metric_primary, x_depth - 2)
                self.add_edge(metric_primary, metric_source)

    async def forward(self, metric, x_depth):
        exchange = await self.configurator.fetch_bindings()
        if metric in exchange:
            bindings = exchange[metric]
            for binding in bindings:
                if binding not in self.nodes:
                    self.add_agent(binding)
                    self.add_layout(binding, x_depth + 1)
                self.add_edge(metric, binding)
                if binding.startswith("transformer"):
                    binding_dict = (await self.configurator.get_configs([binding]))[
                        binding
                    ]["metrics"]
                    if binding.endswith("combinator"):
                        for key, value in binding_dict.items():
                            json_ends = await self.search_json([], value["expression"])
                            for end in json_ends:
                                if metric == end:
                                    if key not in self.nodes:
                                        self.add_metric(key)
                                        self.add_layout(key, x_depth + 2)
                                    self.add_edge(binding, key)
                                    await self.forward(key, x_depth + 2)
                    elif binding.endswith("aggregator"):
                        for key, value in binding_dict.items():
                            if metric == value["source"]:
                                if key not in self.nodes:
                                    self.add_metric(key)
                                    self.add_layout(key, x_depth + 2)
                                self.add_edge(binding, key)
                                await self.forward(key, x_depth + 2)

    async def search_json(self, json_ends, expression):
        if not isinstance(expression, dict) and not isinstance(expression, list):
            json_ends.append(expression)
        else:
            if isinstance(expression, dict):
                for key, value in expression.items():
                    await self.search_json(json_ends, value)
            elif isinstance(expression, list):
                for item in expression:
                    await self.search_json(json_ends, item)
        return json_ends
