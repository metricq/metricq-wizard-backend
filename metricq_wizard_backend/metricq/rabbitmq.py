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

import urllib
from collections import defaultdict
from contextlib import suppress

import aiohttp
from aiocache import SimpleMemoryCache, cached
from aiocouch import Database, Document, NotFoundError


class Bindings:
    def __init__(
        self, *, api_url: str, data_host: str, configs: Database, clients: Database
    ):
        self.api_url = api_url
        self.data_host = data_host
        self.configs = configs
        self.clients = clients

        self.metrics_by_consumer = defaultdict(list)
        self.consumers_by_metric = defaultdict(list)

    async def _client_exists(self, token: str) -> bool:
        with suppress(NotFoundError):
            # check if there is a configuration for a document called {token}
            doc = Document(database=self.clients, id=token)
            await doc._head()

            return True
        return False

    @cached(ttl=5 * 60, cache=SimpleMemoryCache)
    async def _guess_token_from_queue_name(self, queue: str) -> str:
        # first check if it's a data queue
        # somehow vtti managed to add a data queue without the
        # postfix, so I make vtti proud by replacing the assert with
        # an if statement.
        if not queue.endswith("-data"):
            # whatever this queue is, but I blame vtti for it.
            return queue

        token = queue.removesuffix("-data")

        # assume the queue name is in the format of {token}-data
        # check if there is a configuration for a document called {token}
        if await self._client_exists(token):
            return token

        # maybe the queue got a uuid attached to it
        # so it would be in the format {token}-{uuid}-data
        # that means, there would be a dash in the current token
        if "-" in token:
            # There is a dash, so let's extract the part before the dash
            # and update our token
            token = token.rsplit("-", 1)[0]

            if await self._client_exists(token):
                return token

        # I don't know what this is, but it's a queue ¯\_(ツ)_/¯
        # so we just return the original queue name w/o the -data suffix
        return queue.removesuffix("-data")

    async def _fetch(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                urllib.parse.urljoin(
                    self.api_url,
                    f"/api/exchanges/{urllib.parse.quote_plus(self.data_host)}/metricq.data/bindings/source",
                ),
                raise_for_status=True,
            ) as resp:
                for binding in await resp.json():
                    metric = binding["routing_key"]
                    consumer = await self._guess_token_from_queue_name(
                        binding["destination"]
                    )
                    self.consumers_by_metric[metric].append(consumer)
                    self.metrics_by_consumer[consumer].append(metric)


async def fetch_bindings(
    *, api_url: str, data_host: str, configs: Database, clients: Database
) -> Bindings:
    bindings = Bindings(
        api_url=api_url, data_host=data_host, configs=configs, clients=clients
    )
    await bindings._fetch()

    return bindings
