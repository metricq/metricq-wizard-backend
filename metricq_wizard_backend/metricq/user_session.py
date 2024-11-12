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
from typing import Dict, Optional, Sequence

from metricq import get_logger, Timestamp

from metricq_wizard_backend.metricq.source_plugin import (
    SourcePlugin,
    EntryPointType,
    PluginRPCFunctionType,
)

logger = get_logger()


class UserSession:
    def __init__(
        self,
        session_key: str,
    ):
        self.session_key: str = session_key
        self._source_plugins: Dict[str, SourcePlugin] = {}
        self._source_config_revision: Dict[str, str] = {}
        self._source_plugin_creation_time: Dict[str, Timestamp] = {}
        self._source_plugin_initial_configured_metrics: Dict[str, Sequence[str]] = {}
        self.creation_time = Timestamp.now()

    def create_source_plugin(
        self,
        source_id: str,
        source_config: Dict,
        rpc_function: PluginRPCFunctionType,
    ) -> Optional[SourcePlugin]:
        source_type = source_config["type"].replace("-", "_")

        if source_id not in self._source_plugins:
            full_module_name = f"metricq_wizard_plugin_{source_type}"
            if importlib.util.find_spec(full_module_name):
                plugin_module = importlib.import_module(full_module_name)
                entry_point: EntryPointType = plugin_module.get_plugin
                self._source_plugins[source_id] = entry_point(
                    source_config, rpc_function
                )
                self._source_config_revision[source_id] = source_config.get("_rev")
                self._source_plugin_creation_time[source_id] = Timestamp.now()
                self._source_plugin_initial_configured_metrics[source_id] = (
                    self._source_plugins[source_id].get_configured_metrics()
                )
                logger.debug(
                    f"Currently configured metrics: {self._source_plugin_initial_configured_metrics[source_id]}"
                )
            else:
                logger.error(
                    f"Plugin {full_module_name} for source {source_id} not found."
                )

        if source_id in self._source_plugins:
            return self._source_plugins[source_id]

        logger.error(f"Plugin instance for source {source_id} not found.")
        return None

    def get_source_plugin(self, source_id: str) -> Optional[SourcePlugin]:
        return self._source_plugins.get(source_id)

    def unload_source_plugin(self, source_id):
        if source_id in self._source_plugins:
            del self._source_plugins[source_id]
            del self._source_config_revision[source_id]
            del self._source_plugin_creation_time[source_id]

    def can_save_source_config(self, source_id: str, current_rev: str) -> bool:
        return self._source_config_revision.get(source_id, current_rev) == current_rev

    def get_source_plugin_creation_time(self, source_id) -> Optional[Timestamp]:
        return self._source_plugin_creation_time.get(source_id)

    def get_added_metrics(self, source_id) -> Sequence[str]:
        plugin = self._source_plugins.get(source_id)
        if plugin is None:
            return []

        old_metrics = set(self._source_plugin_initial_configured_metrics[source_id])
        current_metrics = set(plugin.get_configured_metrics())

        logger.debug(f"old metrics: {old_metrics}")
        logger.debug(f"current metrics: {current_metrics}")
        logger.debug(f"diff: {current_metrics - old_metrics}")

        return list(current_metrics - old_metrics)
