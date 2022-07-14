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
from aiohttp.web import json_response
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

    return json_response(await network.search())


class Network:
    def __init__(self, original_metric, configurator):
        self.configurator = configurator
        self.nodes = {}
        self.edges = {}
        self.layout = {}
        self.y_depth = defaultdict(int)
        self.add_metric(original_metric, "#417534")
        self.add_layout(original_metric, 0)
        self.original_metric = original_metric

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

    def insert_metric(self, metric: str, token: str, x_depth: int):
        if metric not in self.nodes:
            self.add_metric(metric)
            self.add_layout(metric, x_depth)
        self.add_edge(token, metric)

    async def search(self):
        await self.search_backwards(self.original_metric, 0)
        await self.search_forwards(self.original_metric, 0)

        return {"nodes": self.nodes, "edges": self.edges, "layout": self.layout}

    async def search_backwards(self, metric, x_depth):
        metadata_dict = await self.configurator.fetch_metadata([metric])
        metadata = metadata_dict[next(iter(metadata_dict))]
        metric_id = metadata["_id"]
        source_token = metadata["source"]
        if source_token not in self.nodes:
            self.add_agent(source_token)
            self.add_layout(source_token, x_depth - 1)

        self.add_edge(source_token, metric_id)

        if source_token.startswith("transformer"):
            if source_token.endswith("combinator"):
                await self.search_combinator_backwards(metric, source_token, x_depth)
            elif source_token.endswith("aggregator"):
                await self.search_aggregator_backwards(
                    metadata["primary"], source_token, x_depth
                )

    async def search_combinator_backwards(self, metric: str, token: str, x_depth: int):
        config = (await self.configurator.get_configs([token]))[token]["metrics"][
            metric
        ]

        for input in self.parse_combinator_expression(config["expression"]):
            try:
                if input not in self.nodes:
                    self.add_metric(input)
                    await self.search_backwards(input, x_depth - 2)
                    self.add_layout(input, x_depth - 2)
                self.add_edge(input, token)
            except Exception:
                if input in self.nodes:
                    del self.nodes[input]

    async def search_aggregator_backwards(self, metric: str, token: str, x_depth: int):
        if metric not in self.nodes:
            self.add_metric(metric)
            self.add_layout(metric, x_depth - 2)
            await self.search_backwards(metric, x_depth - 2)
        self.add_edge(metric, token)

    async def search_forwards(self, metric, x_depth):
        for token in await self.configurator.fetch_consumers(metric):
            if token not in self.nodes:
                self.add_agent(token)
                self.add_layout(token, x_depth + 1)
            self.add_edge(metric, token)

            if token.startswith("transformer"):
                if token.endswith("combinator"):
                    await self.search_combinator_forwards(metric, token, x_depth)
                elif token.endswith("aggregator"):
                    await self.search_aggregator_forwards(metric, token, x_depth)

    async def search_aggregator_forwards(self, metric: str, token: str, x_depth: int):
        metrics = (await self.configurator.get_configs([token]))[token]["metrics"]

        for aggregated_metric, config in metrics.items():
            if metric == config["source"]:
                self.insert_metric(aggregated_metric, token, x_depth + 2)
                await self.search_forwards(aggregated_metric, x_depth + 2)

    async def search_combinator_forwards(self, metric: str, token: str, x_depth: int):
        metrics = (await self.configurator.get_configs([token]))[token]["metrics"]

        for combined_metric, config in metrics.items():
            if metric in self.parse_combinator_expression(config["expression"]):
                self.insert_metric(combined_metric, token, x_depth + 2)
                await self.search_forwards(combined_metric, x_depth + 2)

    def parse_combinator_expression(self, expression, inputs=[]):
        if not isinstance(expression, dict) and not isinstance(expression, list):
            inputs.append(expression)
        else:
            if isinstance(expression, dict):
                for value in expression.values():
                    self.parse_combinator_expression(value, inputs)
            elif isinstance(expression, list):
                for item in expression:
                    self.parse_combinator_expression(item, inputs)
        return inputs
