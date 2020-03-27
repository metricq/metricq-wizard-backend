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

from aiohttp.web_exceptions import HTTPBadRequest

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

    # region global config

    async def input_form_edit_global_config(self) -> Dict[str, Dict]:
        return {
            "bacnetReaderAddress": {
                "type": "StringField",
                "label": "IP address of the BACnet source in CIDR notation",
            },
            "bacnetReaderObjectIdentifier": {
                "type": "NumberField",
                "label": "Object identifier for the source as a BACnet device",
            },
            "discoverObjectTypeFilter": {
                "type": "StringField",
                "label": "Comma separated list of BACnet object types, which will be discovered for a device and show up in the devices metric list",
            },
            "vendorSpecificDescriptionSubstitutions": {
                "type": "JSONField",
                "label": "Replacements for matching parts of BACnet descriptions (partial replacement)",
            },
            "vendorSpecificNameSubstitutions": {
                "type": "JSONField",
                "label": "Replacements for matching parts of BACnet names (partial replacement)",
            },
            "vendorSpecificMapping": {
                "type": "JSONField",
                "label": "Replacements for matching BACnet names and descriptions (whole value only)",
            },
        }

    async def get_global_config(self) -> Dict:
        return {
            "bacnetReaderAddress": self._config["bacnetReaderAddress"],
            "bacnetReaderObjectIdentifier": self._config[
                "bacnetReaderObjectIdentifier"
            ],
            "discoverObjectTypeFilter": ",".join(
                self._config.get("discoverObjectTypeFilter", [])
            ),
            "vendorSpecificDescriptionSubstitutions": self._config.get(
                "vendorSpecificDescriptionSubstitutions", ""
            ),
            "vendorSpecificNameSubstitutions": self._config.get(
                "vendorSpecificNameSubstitutions", ""
            ),
            "vendorSpecificMapping": self._config.get("vendorSpecificMapping", ""),
        }

    async def update_global_config(self, data: Dict) -> Dict:
        if "bacnetReaderAddress" in data:
            self._config["bacnetReaderAddress"] = data["bacnetReaderAddress"]
        if "bacnetReaderObjectIdentifier" in data:
            self._config["bacnetReaderObjectIdentifier"] = int(
                data["bacnetReaderObjectIdentifier"]
            )
        if "discoverObjectTypeFilter" in data:
            self._config["discoverObjectTypeFilter"] = (
                data["discoverObjectTypeFilter"].replace(" ", "").split(",")
            )
        if "vendorSpecificDescriptionSubstitutions" in data:
            if isinstance(data["vendorSpecificDescriptionSubstitutions"], dict):
                self._config["vendorSpecificDescriptionSubstitutions"] = data[
                    "vendorSpecificDescriptionSubstitutions"
                ]
            else:
                raise HTTPBadRequest(
                    reason="vendorSpecificDescriptionSubstitutions not a dict!"
                )

        if "vendorSpecificNameSubstitutions" in data:
            if isinstance(data["vendorSpecificNameSubstitutions"], dict):
                self._config["vendorSpecificNameSubstitutions"] = data[
                    "vendorSpecificNameSubstitutions"
                ]
            else:
                raise HTTPBadRequest(
                    reason="vendorSpecificNameSubstitutions not a dict!"
                )
        if "vendorSpecificMapping" in data:
            if isinstance(data["vendorSpecificMapping"], dict):
                self._config["vendorSpecificMapping"] = data["vendorSpecificMapping"]
            else:
                raise HTTPBadRequest(reason="vendorSpecificMapping not a dict!")

        return data

    # endregion

    async def get_config(self) -> Dict:
        return self._config
