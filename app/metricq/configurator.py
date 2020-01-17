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

import importlib
import json
import logging
import os
from asyncio import Lock
from typing import Union, Sequence, Dict

from aiohttp import ClientResponseError
from metricq import ManagementAgent
from metricq.logging import get_logger

from app.api.models import MetricDatabaseConfiguration
from app.metricq.source_plugin import SourcePlugin

logger = get_logger()

logger.setLevel("INFO")
# Use this if we ever use threads
# logger.handlers[0].formatter = logging.Formatter(fmt='%(asctime)s %(threadName)-16s %(levelname)-8s %(message)s')
# logger.handlers[0].formatter = logging.Formatter(
#     fmt="%(asctime)s [%(levelname)-8s] [%(name)-20s] %(message)s"
# )


class Configurator(ManagementAgent):
    def __init__(
        self,
        token,
        management_url,
        couchdb_url,
        couchdb_user,
        couchdb_password,
        event_loop,
    ):
        super().__init__(
            token,
            management_url,
            "",
            couchdb_url,
            couchdb_user,
            couchdb_password,
            event_loop=event_loop,
        )
        self._loaded_plugins: Dict[str, SourcePlugin] = {}
        self._config_locks = {}

    async def fetch_metadata(self, metric_ids):
        return {
            doc.id: doc.data
            async for doc in self.couchdb_db_metadata.docs(metric_ids, create=True)
        }

    async def stop(self):
        logger.debug("closing data channel and connection in manager")
        await super().stop()

    async def read_config(self, token):
        try:
            return (await self.couchdb_db_config[token]).data
        except KeyError:
            # TODO use aiofile
            with open(os.path.join(self.config_path, token + ".json"), "r") as f:
                return json.load(f)

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

        configs = {doc["_id"]: doc async for doc in aiter}

        return configs

    async def set_config(self, token: str, new_config: dict):
        arguments = {"token": token, "config": new_config}
        logger.debug(arguments)

        config = await self.couchdb_db_config[token]
        if config:
            self._update_config(config, new_config)
            await config.save()

        return

    async def update_metric_database_config(
        self, metric_database_configuration: MetricDatabaseConfiguration
    ):
        metadata = await self.get_metrics(
            format="object", selector=metric_database_configuration.id
        )

        if metadata and metric_database_configuration.id in metadata:
            metric_metadata = metadata[metric_database_configuration.id]
            if metric_metadata.get("historic", False):
                logger.warn("Metric already in a database. Ignoring!")
            else:
                async with self._get_config_lock(
                    metric_database_configuration.database_id
                ):
                    config = await self.get_configs(
                        selector=metric_database_configuration.database_id
                    )
                    if config and metric_database_configuration.database_id in config:
                        db_config = config[metric_database_configuration.database_id]
                        if metric_database_configuration.id in db_config["metrics"]:
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
                            db_config["metrics"][
                                metric_database_configuration.id
                            ] = metric_config

                            await db_config.save()
                    else:
                        logger.warn("Config for database not found!")
        else:
            logger.warn("Metric not found. Ignoring!")

    def _get_config_lock(self, token):
        config_lock = self._config_locks.get(token, None)
        if not config_lock:
            config_lock = Lock()
            self._config_locks[token] = config_lock
        return config_lock

    def _update_config(self, doc, config):
        for key, value in config.items():
            if not key.startswith("_"):
                doc[key] = value

    async def get_source_plugin(self, source_id) -> SourcePlugin:
        config = await self.couchdb_db_config[source_id]
        source_type = config.get("type", None)
        if source_type is None:
            logger.error(f"No type for source {source_id} provided.")
            return None

        if source_id not in self._loaded_plugins:
            full_module_name = f"metricq_wizard_plugin_{source_type}"
            if importlib.util.find_spec(full_module_name):
                plugin_module = importlib.import_module(full_module_name)
                self._loaded_plugins[source_id] = plugin_module.get_plugin(config)
            else:
                logger.error(
                    f"Plugin {full_module_name} for source {source_id} not found."
                )
                return None

        if source_id in self._loaded_plugins:
            return self._loaded_plugins[source_id]

        logger.error("Plugin instance for source {source_id} not found.")
        return None

    async def save_source_config(self, source_id):
        async with self._get_config_lock(source_id):
            source_plugin = await self.get_source_plugin(source_id)
            config = await self.couchdb_db_config[source_id]
            self._update_config(config, await source_plugin.get_config())
            await config.save()

    async def reconfigure_source(self, source_id):
        async with self._get_config_lock(source_id):
            config = await self.couchdb_db_config[source_id]
            await self.rpc(
                function="config",
                exchange=self._management_channel.default_exchange,
                routing_key=f"{source_id}-rpc",
                response_callback=self._on_source_configure_response,
                **config,
            )

    async def _on_source_configure_response(self, response):
        logger.debug("Source reconfigure completed!")
