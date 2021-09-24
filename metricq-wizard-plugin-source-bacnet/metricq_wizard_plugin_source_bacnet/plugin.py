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
import asyncio
import re
from string import Template
from typing import Dict, List, Sequence

from aiohttp.web_exceptions import HTTPBadRequest
from metricq import get_logger

from metricq_wizard_backend.metricq.source_plugin import (
    AddMetricItem,
    AvailableMetricItem,
    AvailableMetricList,
    ConfigItem,
    PluginRPCFunctionType,
    SourcePlugin,
)

logger = get_logger(__name__)


def unpack_range(range_str: str) -> List[int]:
    ret = []
    for r in range_str.split(","):
        if "-" in r:
            start, stop = r.split("-")
            for i in range(int(start), int(stop) + 1):
                ret.append(i)
        else:
            ret.append(int(r))
    return ret


class Plugin(SourcePlugin):
    # noinspection PyMissingConstructor
    def __init__(self, config: Dict, rpc_function: PluginRPCFunctionType):
        self._config = config
        self._rpc = rpc_function
        self._object_info_cache = {}

    def get_config_item_name(self) -> str:
        return "device"

    async def get_configuration_items(self) -> Sequence[ConfigItem]:
        # devices_from_source is {"ip": {"device_id": 1234, "device_name": "TRE.BLOB"}}
        try:
            devices_from_source = await self._rpc(
                function="source_bacnet.get_advertised_devices", timeout=10
            )
            del devices_from_source["from_token"]
        except asyncio.exceptions.TimeoutError:
            logger.error("Getting advertised devices from source bacnet timeouted!")
            devices_from_source = {}
        device_ips_from_config = list(self._config["devices"].keys())
        # device_infos_from_source is {"ip": {"device_id": 1234, "device_name": "TRE.BLOB"}}
        try:
            device_infos_from_source = await self._rpc(
                function="source_bacnet.get_device_name_from_ip",
                timeout=10,
                ips=device_ips_from_config,
            )
            del device_infos_from_source["from_token"]
        except asyncio.exceptions.TimeoutError:
            logger.error("Getting advertised devices from source bacnet timeouted!")
            device_infos_from_source = {
                ip: {
                    "device_id": self._config["devices"][ip].get(
                        "deviceIdentifier", "N/A"
                    ),
                    "device_name": "N/A",
                }
                for ip in device_ips_from_config
            }

        devices_from_source.update(device_infos_from_source)
        prefix = re.compile(self._config.get("devicePrefix", ".*"))
        return [
            ConfigItem(
                id=ip,
                name=info["device_name"],
                description=f"IP: {ip}, device identifier: {info['device_id']}",
            )
            for ip, info in devices_from_source.items()
            if prefix.fullmatch(info["device_name"])
        ]

    async def get_metrics_for_config_item(
        self, config_item_id: str
    ) -> AvailableMetricList:
        try:
            object_list_from_source = await self._rpc(
                function="source_bacnet.get_object_list_with_info",
                timeout=10,
                ip=config_item_id,
            )
            del object_list_from_source["from_token"]
        except asyncio.exceptions.TimeoutError:
            logger.error("Getting advertised devices from source bacnet timeouted!")
            object_list_from_source = {}

        device_object_info_cache = self._object_info_cache.get(config_item_id, {})
        device_object_info_cache.update(object_list_from_source)
        self._object_info_cache[config_item_id] = device_object_info_cache

        previous_object_configurations = {}
        if config_item_id in self._config["devices"]:
            for object_group in self._config["devices"][config_item_id]["objectGroups"]:
                if object_group["objectType"] not in previous_object_configurations:
                    previous_object_configurations[object_group["objectType"]] = {}
                for object_instance in unpack_range(object_group["objectInstance"]):
                    previous_object_configurations[object_group["objectType"]][
                        object_instance
                    ] = {
                        "active": True,
                        "interval": object_group["interval"],
                        "found": False,
                    }

        metric_id_template = Template(
            self._config["devices"]
            .get(config_item_id, {})
            .get("metricId", "$objectName")
        )
        description_template = Template(
            self._config["devices"]
            .get(config_item_id, {})
            .get("description", "$objectDescription")
        )

        available_metric_items = []
        for object_identifier in object_list_from_source:
            object_type, object_instance = object_identifier.split("-")
            object_instance = int(object_instance)

            object_info = object_list_from_source[object_identifier]

            if not object_info:
                continue

            metric_name = (
                metric_id_template.safe_substitute(
                    {
                        "objectName": object_info["objectName"],
                        # TODO "deviceName": device_name
                    }
                )
                .replace("'", ".")
                .replace("`", ".")
                .replace("´", ".")
                .replace(" ", "")
            )
            description = (
                description_template.safe_substitute(
                    {
                        "objectName": object_info["objectName"],
                        "objectDescription": object_info.get(
                            "description", "objectDescription"
                        ),
                        # TODO    "deviceName": device_name,
                        # TODO    "deviceDescription": device_info["description"],
                    }
                )
                .replace("'", ".")
                .replace("`", ".")
                .replace("´", ".")
            )
            interval = (
                previous_object_configurations.get(object_type, {})
                .get(object_instance, {})
                .get("interval", 60)
            )

            custom_columns = {
                "detected": {"_": {"type": "LabelField", "value": "yes"}},
                "metric_name": {"_": {"type": "LabelField", "value": metric_name}},
                "interval": {"_": {"type": "NumberField", "value": interval}},
                "object_type": {"_": {"type": "LabelField", "value": object_type}},
                "description": {"_": {"type": "LabelField", "value": description}},
            }

            logger.debug(
                f"{object_identifier}: {previous_object_configurations.get(object_type, {}).get(object_instance, {})}"
            )

            if previous_object_configurations.get(object_type, {}).get(object_instance):
                previous_object_configurations.get(object_type, {}).get(
                    object_instance, {}
                )["found"] = True

            available_metric_items.append(
                AvailableMetricItem(
                    id=object_identifier,
                    custom_columns=custom_columns,
                    is_active=previous_object_configurations.get(object_type, {})
                    .get(object_instance, {})
                    .get("active", False),
                )
            )

        for object_type in previous_object_configurations:
            for object_instance in previous_object_configurations[object_type]:
                if not previous_object_configurations[object_type][object_instance][
                    "found"
                ]:
                    object_identifier = f"{object_type}-{object_instance}"
                    logger.debug(f"{object_identifier} was not found on device!")

                    metric_name = (
                        metric_id_template.template.replace("'", ".")
                        .replace("`", ".")
                        .replace("´", ".")
                        .replace(" ", "")
                    )
                    description = (
                        description_template.template.replace("'", ".")
                        .replace("`", ".")
                        .replace("´", ".")
                    )
                    interval = previous_object_configurations[object_type][
                        object_instance
                    ]["interval"]

                    custom_columns = {
                        "detected": {"_": {"type": "LabelField", "value": "no"}},
                        "metric_name": {
                            "_": {"type": "LabelField", "value": metric_name}
                        },
                        "interval": {
                            "_": {"type": "NumberField", "label": "", "value": interval}
                        },
                        "object_type": {
                            "_": {"type": "LabelField", "value": object_type}
                        },
                        "description": {
                            "_": {"type": "LabelField", "value": description}
                        },
                    }
                    available_metric_items.append(
                        AvailableMetricItem(
                            id=object_identifier,
                            custom_columns=custom_columns,
                            is_active=previous_object_configurations[object_type][
                                object_instance
                            ]["active"],
                        )
                    )

        columns = {
            "detected": "Provided by BACnet",
            "metric_name": "Metric Name",
            "interval": "Interval [s]",
            "object_type": "Object Type",
            "description": "Description",
        }
        return AvailableMetricList(columns=columns, metrics=available_metric_items)

    async def add_metrics_for_config_item(
        self,
        config_item_id: str,
        metrics: Sequence[AddMetricItem],
        not_selected_metric_ids: Sequence[str],
    ) -> Sequence[str]:
        if config_item_id not in self._config["devices"]:
            self._config["devices"][config_item_id] = {
                "metricId": "$objectName",
                "objectGroups": [],
            }

        object_groups = self._config["devices"][config_item_id]["objectGroups"]
        device_object_info_cache = self._object_info_cache.get(config_item_id, {})
        metric_id_template = Template(
            self._config["devices"][config_item_id]["metricId"]
        )

        # Get old metric ids from config
        old_metrics = []
        for object_group in object_groups:
            object_type = object_group["objectType"]
            for object_instance in unpack_range(object_group["objectInstance"]):
                metric_name = (
                    metric_id_template.safe_substitute(
                        {
                            "objectName": device_object_info_cache.get(
                                "{}-{}".format(object_type, object_instance), {}
                            ).get("objectName"),
                            # TODO "deviceName": device_name
                        }
                    )
                    .replace("'", ".")
                    .replace("`", ".")
                    .replace("´", ".")
                    .replace(" ", "")
                )
                old_metrics.append(metric_name)

        # Generate new config
        new_metrics = []
        new_metrics_grouped = {}
        new_metrics_ids = []
        for metric in metrics:
            object_type, object_instance = metric.id.split("-")
            interval = int(metric.custom_columns_values["interval"]["_"])
            metric_name = metric.custom_columns_values["metric_name"]["_"]

            new_metrics.append(metric_name)
            new_metrics_ids.append(metric.id)

            object_type_group = new_metrics_grouped.get(object_type, {})
            object_instance_list = object_type_group.get(interval, [])
            object_instance_list.append(object_instance)
            object_type_group[interval] = object_instance_list
            new_metrics_grouped[object_type] = object_type_group

        for object_group in self._config["devices"][config_item_id]["objectGroups"]:
            object_type = object_group["objectType"]
            interval = object_group["interval"]

            object_type_group = new_metrics_grouped.get(object_type, {})
            object_instance_list = object_type_group.get(interval, [])

            for object_instance in unpack_range(object_group["objectInstance"]):
                object_identifier = "{}-{}".format(object_type, object_instance)
                if (
                    object_identifier not in not_selected_metric_ids
                    and object_identifier not in new_metrics_ids
                ):
                    object_instance_list.append(str(object_instance))

            object_type_group[interval] = object_instance_list
            new_metrics_grouped[object_type] = object_type_group

        new_object_groups = []
        for object_type in new_metrics_grouped:
            for interval in new_metrics_grouped[object_type]:
                if new_metrics_grouped[object_type][interval]:
                    # only add non-empty lists
                    new_object_groups.append(
                        {
                            "objectType": object_type,
                            "interval": interval,
                            "objectInstance": ",".join(
                                new_metrics_grouped[object_type][interval]
                            ),
                        }
                    )

        self._config["devices"][config_item_id]["objectGroups"] = new_object_groups

        # Get diff of metrics
        created_metrics = (
            set(new_metrics) - set(old_metrics) - set([metric_id_template.template])
        )

        return list(created_metrics)

    # region config item modification

    def input_form_add_config_item(self) -> Dict[str, Dict]:
        return {
            "deviceIp": {
                "type": "StringField",
                "label": "IP of the BACnet device (required)",
            },
            "metricId": {
                "type": "StringField",
                "label": "Template for metric IDs (required, supported placeholders: $objectName, $deviceName)",
            },
            "deviceId": {
                "type": "NumberField",
                "label": "Optional object Identifier of the BACnet device (produces warning in source if mismatch with ID of the device at IP)",
            },
            "description": {
                "type": "StringField",
                "label": "Template for metric descritptions (supported placeholders: $objectName, $objectDescription, $deviceName, $deviceDescription)",
            },
            "chunkSize": {
                "type": "NumberField",
                "label": "Optional count of requests per BACnet multi request",
            },
        }

    async def add_config_item(self, data: Dict) -> ConfigItem:
        if (
            "metricId" not in data
            or not data["metricId"]
            or "deviceIp" not in data
            or not data["deviceIp"]
        ):
            raise HTTPBadRequest(reason="deviceIp and metricId are required!")

        if data["deviceIp"] in self._config["devices"]:
            raise HTTPBadRequest(
                reason=f"device with ip {data['deviceIp']} already exists!"
            )

        new_config_item = {"metricId": data["metricId"], "objectGroups": []}

        if "deviceId" in data and data["deviceId"]:
            new_config_item["deviceIdentifier"] = data["deviceId"]

        if "description" in data and data["description"]:
            new_config_item["description"] = data["description"]

        if "chunkSize" in data and data["chunkSize"]:
            new_config_item["chunkSize"] = int(data["chunkSize"])

        self._config["devices"][data["deviceIp"]] = new_config_item

        # TODO get info
        info = {
            "device_name": "TODO",
            "device_id": new_config_item.get("deviceIdentifier", "TODO"),
        }

        return ConfigItem(
            id=data["deviceIp"],
            name=info["device_name"],
            description=f"IP: {data['deviceIp']}, device identifier: {info['device_id']}",
        )

    def input_form_edit_config_item(self) -> Dict[str, Dict]:
        return {
            "deviceIp": {"type": "LabelField"},
            "metricId": {
                "type": "StringField",
                "label": "Template for metric IDs (supported placeholders: $objectName, $deviceName)",
            },
            "deviceId": {
                "type": "NumberField",
                "label": "Object Identifier of the BACnet device (optional, produces warning in source if mismatch with ID of the device at IP)",
            },
            "description": {
                "type": "StringField",
                "label": "Template for metric descritptions (optional, supported placeholders: $objectName, $objectDescription, $deviceName, $deviceDescription)",
            },
            "chunkSize": {
                "type": "NumberField",
                "label": "Count of requests per BACnet multi request (optional)",
            },
        }

    async def get_config_item(self, config_item_id: str) -> Dict:
        return {
            "deviceIp": f"Device IP: {config_item_id}",
            "metricId": self._config["devices"]
            .get(config_item_id, {})
            .get("metricId", "$objectName"),
            "deviceId": self._config["devices"]
            .get(config_item_id, {})
            .get("deviceIdentifier"),
            "description": self._config["devices"]
            .get(config_item_id, {})
            .get("description"),
            "chunkSize": self._config["devices"]
            .get(config_item_id, {})
            .get("chunkSize"),
        }

    async def update_config_item(self, config_item_id: str, data: Dict) -> ConfigItem:
        if config_item_id not in self._config["devices"]:
            if "metricId" not in data or not data["metricId"]:
                raise HTTPBadRequest(reason="metricId is required for new devices!")

            self._config["devices"][config_item_id] = {
                "metricId": data["metricId"],
                "objectGroups": [],
            }

        if "metricId" in data and data["metricId"]:
            self._config["devices"][config_item_id]["metricId"] = data["metricId"]

        if "deviceId" in data and data["deviceId"]:
            self._config["devices"][config_item_id]["deviceIdentifier"] = data[
                "deviceId"
            ]

        if "description" in data and data["description"]:
            self._config["devices"][config_item_id]["description"] = data["description"]

        if "chunkSize" in data and data["chunkSize"]:
            self._config["devices"][config_item_id]["chunkSize"] = int(
                data["chunkSize"]
            )

        # TODO get info
        info = {
            "device_name": "TODO",
            "device_id": self._config["devices"][config_item_id].get(
                "deviceIdentifier", "TODO"
            ),
        }

        return ConfigItem(
            id=config_item_id,
            name=info["device_name"],
            description=f"IP: {config_item_id}, device identifier: {info['device_id']}",
        )

    async def delete_config_item(self, config_item_id: str):
        # TODO should this be possible?
        pass

    # endregion

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
