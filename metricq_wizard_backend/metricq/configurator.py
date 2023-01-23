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
import datetime
import hashlib
import json
import urllib
from asyncio import Lock, gather
from itertools import islice
from typing import Any, Dict, List, Optional, Sequence, Union
from collections import defaultdict

import aiohttp
from aiocouch import CouchDB, Document, NotFoundError, database
from metricq import Agent, Client
from metricq.logging import get_logger
from aiocache import SimpleMemoryCache, cached

from metricq_wizard_backend.api.models import MetricDatabaseConfiguration
from metricq_wizard_backend.metricq.session_manager import UserSessionManager
from metricq_wizard_backend.metricq.session_manager import UserSession
from metricq_wizard_backend.metricq.source_plugin import SourcePlugin
from metricq_wizard_backend.version import version as __version__  # noqa: F401

logger = get_logger()

logger.setLevel("INFO")

JsonDict = dict[str, Any]

# Use this if we ever use threads
# logger.handlers[0].formatter = logging.Formatter(fmt='%(asctime)s %(threadName)-16s %(levelname)-8s %(message)s')
# logger.handlers[0].formatter = logging.Formatter(
#     fmt="%(asctime)s [%(levelname)-8s] [%(name)-20s] %(message)s"
# )


class Configurator(Client):
    def __init__(
        self,
        token,
        management_url,
        couchdb_url,
        rabbitmq_api_url,
        rabbitmq_data_host,
    ):
        super().__init__(
            token,
            management_url,
        )

        self.couchdb_client: CouchDB = CouchDB(couchdb_url)

        self.rabbitmq_api_url = rabbitmq_api_url
        self.rabbitmq_data_host = rabbitmq_data_host

        self.couchdb_db_config: database.Database = None
        self.couchdb_db_metadata: database.Database = None
        self.couchdb_db_clients: database.Database = None

        self.user_session_manager = UserSessionManager()

        self._config_locks = {}

    async def connect(self):
        # First, connect to couchdb
        self.couchdb_db_config = await self.couchdb_client.create(
            "config", exists_ok=True
        )
        self.couchdb_db_metadata = await self.couchdb_client.create(
            "metadata", exists_ok=True
        )

        self.couchdb_db_clients = await self.couchdb_client.create(
            "clients", exists_ok=True
        )

        self.couchdb_db_config_backups = await self.couchdb_client.create(
            "config_backup", exists_ok=True
        )

        index = await self.couchdb_db_config_backups.design_doc("index", exists_ok=True)
        await index.create_view(
            view="token",
            map_function='function (doc) {\n  emit(doc["x-metricq-id"], doc._id);\n}',
            exists_ok=True,
        )

        # After that, we do the MetricQ connection stuff
        await super().connect()

    @cached(ttl=5 * 60, cache=SimpleMemoryCache)
    async def fetch_bindings(self):
        metrics_by_consumer = defaultdict(list)
        consumers_by_metric = defaultdict(list)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.rabbitmq_api_url
                + f"/api/exchanges/{urllib.parse.quote_plus(self.rabbitmq_data_host)}/metricq.data/bindings/source"
            ) as resp:
                for binding in await resp.json():
                    metric = binding["routing_key"]
                    consumer = await self.guess_token_from_queue_name(
                        binding["destination"]
                    )
                    consumers_by_metric[metric].append(consumer)
                    metrics_by_consumer[consumer].append(metric)
        return (
            consumers_by_metric,
            metrics_by_consumer,
        )

    @cached(ttl=60 * 60, cache=SimpleMemoryCache)
    async def guess_token_from_queue_name(self, queue: str) -> str:
        # first check if it's a data queue
        assert queue.endswith("-data")
        token = queue.removesuffix("-data")

        try:
            # check if there is a configuration for a document called {token}
            doc = Document(database=self.couchdb_db_config, id=token)
            await doc._head()

            return token
        except NotFoundError:
            # maybe the queue got a uuid attached to it
            # so it would be {token}-{uuid}-data

            # The following call is idempotent if there's no dash in token
            token = token.rsplit("-", 1)[0]

            try:
                # check if there is a configuration for a document called {token}
                doc = Document(database=self.couchdb_db_clients, id=token)
                await doc._head()

                return token
            except NotFoundError:

                # I'don't know what this is, but it's a queue ¯\_(ツ)_/¯
                return token

    @cached(ttl=5 * 60, cache=SimpleMemoryCache)
    async def fetch_produced_metrics(self, token):
        view = self.couchdb_db_metadata.view("index", "source")

        return [metric async for metric in view.ids(prefix=token)]

    async def fetch_consumed_metrics(self, token):
        (_, metrics_by_consumer) = await self.fetch_bindings()

        return metrics_by_consumer.get(token, [])

    async def fetch_consumers(self, metric: str):
        (consumers_by_metric, _) = await self.fetch_bindings()

        return consumers_by_metric.get(metric, [])

    async def fetch_metadata(self, metric_ids):
        return {
            doc.id: doc.data
            async for doc in self.couchdb_db_metadata.docs(metric_ids, create=True)
        }

    async def fetch_dependency_wheel(self):
        connections = defaultdict(int)

        for client in (await self.get_configs()).keys():
            metrics = await self.fetch_produced_metrics(client)

            for metric in metrics:
                consumers = await self.fetch_consumers(metric)

                for consumer in consumers:
                    connections[(client, consumer)] += 1

        return [[key[0], key[1], count] for key, count in connections.items()]

    async def read_config(self, token):
        return (await self.couchdb_db_config[token]).data

    async def get_configs(
        self, selector: Union[str, Sequence[str], None] = None
    ) -> dict:
        """
        :param selector: regex for partial matching the metric name or sequence of possible metric names
        :return: a {token: config} dict
        """
        selector_dict = dict()
        if selector is not None:
            if isinstance(selector, str):
                selector_dict["_id"] = {"$regex": selector}
            elif isinstance(selector, list):
                if len(selector) < 1:
                    raise ValueError("Empty selector list")
                if len(selector) == 1:
                    # That may possibly be faster.
                    selector_dict["_id"] = selector[0]
                else:
                    selector_dict["_id"] = {"$in": selector}
            else:
                raise TypeError(
                    "Invalid selector type: {}, supported: str, list", type(selector)
                )

        if selector_dict:
            aiter = self.couchdb_db_config.find(selector_dict)
        else:
            aiter = self.couchdb_db_config.all_docs.docs()

        configs = {
            doc["_id"]: doc async for doc in aiter if not doc["_id"].startswith("_")
        }

        return configs

    async def set_config(self, token: str, new_config: dict):
        arguments = {"token": token, "config": new_config}
        logger.debug(arguments)

        async with self._get_config_lock(token):

            config = await self.couchdb_db_config[token]

            if config.exists:
                try:
                    backup = await self.couchdb_db_config_backups.create(
                        f"backup-{token}-{datetime.datetime.now().isoformat()}"
                    )
                    backup_data = dict(config.data)
                    backup_data["x-metricq-id"] = token
                    if "_rev" in backup_data:
                        del backup_data["_rev"]
                    backup.update(backup_data)
                    await backup.save()
                except Exception as e:
                    logger.warn(
                        f"Failed to save configuration backup for `{config.id}` in CouchDB: {e}"
                    )

            for config_key in list(config.keys()):
                if config_key not in new_config:
                    del config[config_key]

            config.update(new_config)

            await config.save()

        return

    async def update_metric_database_config(
        self, metric_database_configurations: List[MetricDatabaseConfiguration]
    ):

        configurations_by_database = {}
        for config in metric_database_configurations:
            config_list = configurations_by_database.get(config.database_id, [])
            config_list.append(config)
            configurations_by_database[config.database_id] = config_list

        for database_id in configurations_by_database.keys():
            async with self._get_config_lock(database_id):
                config = await self.couchdb_db_config[database_id]

                if config:
                    for metric_database_configuration in configurations_by_database[
                        database_id
                    ]:
                        metadata = await self.couchdb_db_metadata[
                            metric_database_configuration.id
                        ]

                        if metadata:
                            if metadata.get("historic", False):
                                logger.warn("Metric already in a database. Ignoring!")
                            else:
                                if (
                                    metric_database_configuration.id
                                    in config["metrics"]
                                ):
                                    logger.warn(
                                        f"Metric already configured for database {metric_database_configuration.database_id}. Ignoring!"
                                    )
                                else:
                                    metric_config = {
                                        "mode": "RW",
                                        "interval_min": metric_database_configuration.interval_min.ns,
                                        "interval_max": metric_database_configuration.interval_max.ns,
                                        "interval_factor": metric_database_configuration.interval_factor,
                                    }
                                    config["metrics"][
                                        metric_database_configuration.id
                                    ] = metric_config
                        else:
                            logger.warn("Metric not found. Ignoring!")

                    await config.save()
                else:
                    logger.warn("Config for database not found!")

    def _get_config_lock(self, token):
        config_lock = self._config_locks.get(token, None)
        if not config_lock:
            config_lock = Lock()
            self._config_locks[token] = config_lock
        return config_lock

    async def get_source_plugin(
        self, source_id, session_key: str
    ) -> Optional[SourcePlugin]:
        config = await self.couchdb_db_config[source_id]
        if "type" not in config:
            logger.error(f"No type for source {source_id} provided.")
            return None

        session = self.user_session_manager.get_user_session(session_key)
        source_plugin = session.get_source_plugin(source_id)

        if source_plugin is None:
            source_plugin = session.create_source_plugin(
                source_id,
                source_config=config,
                rpc_function=self._rpc_for_plugins(client_token=source_id),
            )

        return source_plugin

    def unload_source_plugin(self, source_id, session_key):
        session = self.user_session_manager.get_user_session(session_key)
        session.unload_source_plugin(source_id)

    def get_session(self, session_key: str) -> UserSession:
        session = self.user_session_manager.get_user_session(session_key)

        return session

    async def get_session_state(self, session_key: str, source_id: str) -> bool:
        config = await self.couchdb_db_config[source_id]
        if "type" not in config:
            logger.error(f"No type for source {source_id} provided.")
            return None

        session = self.user_session_manager.get_user_session(session_key)

        return session.can_save_source_config(source_id, config.get("_rev"))

    async def save_source_config(
        self, source_id, session_key: str, unload_plugin=False
    ) -> Sequence[str]:
        source_plugin = await self.get_source_plugin(source_id, session_key)
        if source_plugin:
            await self.set_config(source_id, await source_plugin.get_config())

            session = self.get_session(session_key)
            metrics = session.get_added_metrics(source_id)

            if unload_plugin:
                self.unload_source_plugin(source_id, session_key)

            return metrics

        return []

    async def create_client(self, client_id):
        async with self._get_config_lock(client_id):
            config = await self.couchdb_db_config.create(client_id)
            await config.save()

    async def reconfigure_client(self, client_id):
        async with self._get_config_lock(client_id):
            config = await self.couchdb_db_config[client_id]
            await super(Client, self).rpc(
                function="config",
                exchange=self._management_channel.default_exchange,
                routing_key=f"{client_id}-rpc",
                response_callback=self._on_client_configure_response,
                **config,
            )

    async def _on_client_configure_response(self, **kwargs):
        logger.debug(f"Client reconfigure completed! kwargs are: {kwargs}")

    def _rpc_for_plugins(self, client_token: str):
        async def rpc_function(
            function: str,
            response_callback: Any = None,
            timeout: int = 60,
            **kwargs: Any,
        ):
            await self._management_connection_watchdog.established()
            logger.debug(f"Routing key for rpc is {client_token}-rpc")
            return await super(Client, self).rpc(
                exchange=self._management_channel.default_exchange,
                routing_key=f"{client_token}-rpc",
                response_callback=response_callback,
                timeout=timeout,
                function=function,
                **kwargs,
            )

        return rpc_function

    async def get_metrics(
        self,
        selector: Union[str, Sequence[str], None] = None,
        format: Optional[str] = "array",
        historic: Optional[bool] = None,
        timeout: Optional[float] = None,
        prefix: Optional[str] = None,
        infix: Optional[str] = None,
        limit: Optional[int] = None,
        source: Optional[str] = None,
    ) -> Union[Sequence[str], Sequence[dict]]:
        if format not in ("array", "object"):
            raise AttributeError("unknown format requested: {}".format(format))

        if infix is not None and prefix is not None:
            raise AttributeError('cannot get_metrics with both "prefix" and "infix"')

        if source is not None and historic is not None:
            raise AttributeError('cannot get_metrics with both "historic" and "source"')

        selector_dict = dict()
        if selector is not None:
            if isinstance(selector, str):
                selector_dict["_id"] = {"$regex": selector}
            elif isinstance(selector, list):
                if len(selector) < 1:
                    raise ValueError("Empty selector list")
                if len(selector) == 1:
                    # That may possibly be faster.
                    selector_dict["_id"] = selector[0]
                else:
                    selector_dict["_id"] = {"$in": selector}
            else:
                raise TypeError(
                    "Invalid selector type: {}, supported: str, list", type(selector)
                )
        if historic is not None:
            if not isinstance(historic, bool):
                raise AttributeError(
                    'invalid type for "historic" argument: should be bool, is {}'.format(
                        type(historic)
                    )
                )

        # TODO can this be unified without compromising performance?
        # Does this even perform well?
        # ALSO: Async :-[
        if selector_dict:
            if historic is not None:
                selector_dict["historic"] = historic
            if prefix is not None or infix is not None:
                raise AttributeError(
                    'cannot get_metrics with both "selector" and "prefix" or "infix".'
                )
            aiter = self.couchdb_db_metadata.find(selector_dict, limit=limit)
            if format == "array":
                metrics = [doc["_id"] async for doc in aiter]
            elif format == "object":
                metrics = {doc["_id"]: doc.data async for doc in aiter}

        else:  # No selector dict, all *fix / historic filtering
            request_limit = limit
            request_params = {}
            if infix is None:
                request_prefix = prefix
                if historic is not None:
                    endpoint = self.couchdb_db_metadata.view("index", "historic")
                elif source is not None:
                    endpoint = self.couchdb_db_metadata.view("index", "source")
                    request_prefix = None
                    request_params["key"] = f'"{source}"'
                else:
                    endpoint = self.couchdb_db_metadata.all_docs
            else:
                request_prefix = infix
                # These views produce stupid duplicates thus we must filter ourselves and request more
                # to get enough results. We assume for no more than 6 infix segments on average
                if limit is not None:
                    request_limit = 6 * limit
                if historic is not None:
                    endpoint = self.couchdb_db_metadata.view("components", "historic")
                else:
                    raise NotImplementedError(
                        "non-historic infix lookup not yet supported"
                    )
            if format == "array":
                metrics = [
                    key
                    async for key in endpoint.ids(
                        prefix=request_prefix, limit=request_limit
                    )
                ]
                if request_limit != limit:
                    # Object of type islice is not JSON serializable m(
                    metrics = list(islice(sorted(set(metrics)), limit))
            elif format == "object":
                metrics = {
                    doc["_id"]: doc.data
                    async for doc in endpoint.docs(
                        prefix=request_prefix, limit=request_limit, **request_params
                    )
                }
                if request_limit != limit:
                    metrics = dict(islice(sorted(metrics.items()), limit))

        return metrics

    async def get_combined_metric_expression(
        self, transformer_id: str, metric: str
    ) -> Optional[Dict]:
        config = await self.read_config(transformer_id)
        for transformer_metric in config.get("metrics", {}):
            if transformer_metric == metric:
                config_hash = hashlib.sha256(
                    json.dumps(config["metrics"][transformer_metric]).encode("utf-8")
                ).hexdigest()
                logger.info("JSON hash is {}", config_hash)
                return {
                    "config_hash": config_hash,
                    "expression": config["metrics"][transformer_metric].get(
                        "expression"
                    ),
                }
        return None

    async def create_combined_metric(
        self, transformer_id: str, metric: str, expression: Dict
    ) -> bool:
        async with self._get_config_lock(transformer_id):
            config = await self.couchdb_db_config[transformer_id]

            if "metrics" not in config:
                config["metrics"] = {}

            if metric not in config["metrics"]:
                config["metrics"][metric] = {"expression": expression}
                await config.save()
                return True

        return False

    async def update_combined_metric_expression(
        self, transformer_id: str, metric: str, expression: Dict, config_hash: str
    ) -> bool:
        async with self._get_config_lock(transformer_id):
            config = await self.couchdb_db_config[transformer_id]

            if "metrics" not in config:
                config["metrics"] = {}

            if metric in config["metrics"]:
                old_config_hash = hashlib.sha256(
                    json.dumps(config["metrics"][metric]).encode("utf-8")
                ).hexdigest()
                if config_hash == old_config_hash:
                    config["metrics"][metric]["expression"] = expression
                    await config.save()
                    return True

        return False

    async def get_host(self, client: str) -> str:
        try:
            response = await Agent.rpc(
                self,
                function="discover",
                routing_key=f"{client}-rpc",
                exchange=self._management_channel.default_exchange,
                timeout=10,
            )
            return response
        except TimeoutError as e:
            raise RuntimeError(
                f"Failed to get hostname for '{client}'. RPC timed out."
            ) from e

    async def discover(self) -> None:
        async def callback(from_token: str, **response):
            client = await self.couchdb_db_clients.create(from_token, exists_ok=True)
            client.update(response)
            client["discoverTime"] = datetime.datetime.now(
                tz=datetime.timezone.utc
            ).isoformat()
            await client.save()

        await Agent.rpc(
            self,
            function="discover",
            exchange=self._management_broadcast_exchange,
            routing_key="discover",
            timeout=30,
            response_callback=callback,
            cleanup_on_response=False,
        )

    async def fetch_config_backups(self, token: str) -> List[str]:
        return [
            backup.id
            async for backup in self.couchdb_db_config_backups.view(
                "index", "token"
            ).docs(prefix=token)
        ]

    async def fetch_config_backup(self, token: str, backup_id: str) -> JsonDict:
        assert backup_id.startswith(f"backup-{token}-")

        backup = await self.couchdb_db_config_backups.get(backup_id)
        backup_data = dict(backup.data)
        del backup_data["_id"]
        del backup_data["_rev"]
        del backup_data["x-metricq-id"]

        return backup_data

    async def fetch_topology(self) -> JsonDict:
        hosts = defaultdict(dict)

        async for client_data in self.couchdb_db_clients.all_docs.docs():
            try:
                hosts[client_data["hostname"]].setdefault(
                    "hostname", client_data["hostname"]
                )
                hosts[client_data["hostname"]].setdefault("clients", [])
                hosts[client_data["hostname"]]["clients"].append(client_data.data)
            except KeyError:
                hosts["unknown"].setdefault("hostname", client_data["hostname"])
                hosts["unknown"].setdefault("clients", [])
                hosts["unknown"]["clients"].append(client_data.data)

        return list(hosts.values())

    async def fetch_active_clients(self) -> List[JsonDict]:
        clients = []
        async for client in self.couchdb_db_clients.all_docs.docs():
            data = dict(client.data)
            data["id"] = data["_id"]
            del data["_id"]
            del data["_rev"]
            clients.append(data)

        return clients
