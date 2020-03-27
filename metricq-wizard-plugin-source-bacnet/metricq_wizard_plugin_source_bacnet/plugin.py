# metricq-wizard-plugin-bacnet
# Copyright (C) 2019 ZIH, Technische Universitaet Dresden, Federal Republic of Germany
#
# All rights reserved.
#
# This file is part of metricq-wizard-plugin-bacnet.
#
# metricq-wizard-plugin-bacnet is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# metricq-wizard-plugin-bacnet is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with metricq-wizard-plugin-bacnet.  If not, see <http://www.gnu.org/licenses/>.
from typing import Sequence, Dict

from app.metricq.source_plugin import (
    SourcePlugin,
    AddMetricItem,
    ConfigItem,
    AvailableMetricList,
    PluginRPCFunctionType,
)


class Plugin(SourcePlugin):
    # noinspection PyMissingConstructor
    def __init__(self, config: Dict, rpc_function: PluginRPCFunctionType):
        self._config = config
        self._rpc = rpc_function

    def get_config_item_name(self) -> str:
        return "device"

    def get_configuration_items(self) -> Sequence[ConfigItem]:
        pass

    async def get_metrics_for_config_item(
        self, config_item_id: str
    ) -> AvailableMetricList:
        pass

    async def add_metrics_for_config_item(
        self, config_item_id: str, metrics: Sequence[AddMetricItem]
    ) -> Sequence[str]:
        pass

    def input_form_add_config_item(self) -> Dict[str, Dict]:
        pass

    async def add_config_item(self, data: Dict) -> ConfigItem:
        pass

    def input_form_edit_config_item(self) -> Dict[str, Dict]:
        pass

    async def get_config_item(self, config_item_id: str) -> Dict:
        pass

    async def update_config_item(self, config_item_id: str, data: Dict) -> ConfigItem:
        pass

    async def delete_config_item(self, config_item_id: str):
        pass

    # TODO add vendor specific mapping to global config
    async def input_form_edit_global_config(self) -> Dict[str, Dict]:
        return {
            "bacnetReaderAddress": {"type": "StringField"},
            "bacnetReaderObjectIdentifier": {"type": "NumberField"},
            "devicePrefix": {"type": "StringField"},
        }

    async def get_global_config(self) -> Dict:
        return {
            "bacnetReaderAddress": self._config["bacnetReaderAddress"],
            "bacnetReaderObjectIdentifier": self._config[
                "bacnetReaderObjectIdentifier"
            ],
            "devicePrefix": self._config.get("devicePrefix", ""),
        }

    async def update_global_config(self, data: Dict) -> Dict:
        if "bacnetReaderAddress" in data:
            self._config["bacnetReaderAddress"] = data["bacnetReaderAddress"]
        if "bacnetReaderObjectIdentifier" in data:
            self._config["bacnetReaderObjectIdentifier"] = int(
                data["bacnetReaderObjectIdentifier"]
            )
        if "devicePrefix" in data:
            self._config["devicePrefix"] = data["devicePrefix"]

        return data

    async def get_config(self) -> Dict:
        return self._config
