import json
from typing import Dict, Sequence

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

# bandwidth does not matter here
# bandwidth is only support for gapless mode, where only voltage, current and power is supported!
metric_id_to_name = {
    "voltage_min": "voltage.min",
    "voltage_max": "voltage.max",
    "voltage_crest": "voltage_crest",
    "current_min": "current.min",
    "current_max": "current.max",
    "current_crest": "current_crest",
    "apparent_power": "apparent_power",
    "reactive_power": "reactive_power",
}


class Plugin(SourcePlugin):
    # noinspection PyMissingConstructor
    def __init__(self, config: Dict, rpc_function: PluginRPCFunctionType):
        self._config = config
        self._rpc_function = rpc_function

        logger.debug("Got rpc_function: {}", rpc_function)

    def get_config_item_name(self) -> str:
        return "channel"

    async def get_configuration_items(self) -> Sequence[ConfigItem]:
        return [
            ConfigItem(id=ci_id, name=channel["name"], description=json.dumps(channel))
            for ci_id, channel in enumerate(self._config["channels"])
        ]

    async def get_metrics_for_config_item(
        self, config_item_id: str
    ) -> AvailableMetricList:
        ci_id = int(config_item_id)
        channel_config = self._config["channels"][ci_id]
        available_metrics = ["voltage", "current", "power"]
        if self._config["measurement"]["mode"] == "cycle":
            available_metrics.extend(
                [
                    "voltage_min",
                    "voltage_max",
                    "voltage_crest",
                    "current_min",
                    "current_max",
                    "current_crest",
                    "apparent_power",
                    "reactive_power",
                    "phi",
                ]
            )
        elif self._config["measurement"]["mode"] == "gapless":
            available_metrics.extend(
                [f"{metric}@narrow" for metric in available_metrics]
            )

        available_metric_items = []
        for metric in available_metrics:
            custom_columns = {
                "metric_name": {
                    "_": {
                        "type": "LabelField",
                        "value": f"{channel_config['name']}.{metric_id_to_name.get(metric, metric).replace('@', '.')}",
                    }
                }
            }
            if self._config["measurement"]["mode"] == "gapless":
                metric_parts = metric.split("@")
                if len(metric_parts) > 1:
                    bandwidth = metric_parts[1]
                else:
                    bandwidth = "wide"
                custom_columns["bandwidth"] = {
                    "_": {"type": "LabelField", "value": bandwidth}
                }
            available_metric_items.append(
                AvailableMetricItem(
                    id=metric,
                    custom_columns=custom_columns,
                    is_active=metric in channel_config["metrics"],
                )
            )

        columns = {"metric_name": "Metric Name"}
        if self._config["measurement"]["mode"] == "gapless":
            columns["bandwidth"] = "Bandwidth"

        return AvailableMetricList(columns=columns, metrics=available_metric_items)

    async def add_metrics_for_config_item(
        self,
        config_item_id: str,
        metrics: Sequence[AddMetricItem],
        not_selected_metric_ids: Sequence[str],
    ) -> Sequence[str]:
        ci_id = int(config_item_id)
        channel_config = self._config["channels"][ci_id]
        old_metrics = channel_config["metrics"]
        channel_config["metrics"] = []
        for metric in metrics:
            channel_config["metrics"].append(metric.id)

        new_metrics = set([metric.id for metric in metrics]) - set(old_metrics)

        return [
            f"{channel_config['name']}.{metric_id_to_name.get(metric, metric).replace('@', '.')}"
            for metric in new_metrics
        ]

    def input_form_add_config_item(self) -> Dict[str, Dict]:
        return {
            "name": {"type": "StringField"},
            "coupling": {
                "type": "SelectField",
                "options": [
                    {"text": "AC", "value": "AC"},
                    {"text": "ACDC", "value": "ACDC"},
                ],
            },
            "voltage_range": {"type": "NumberField"},
            "current_range": {"type": "NumberField"},
        }

    async def add_config_item(self, data: Dict) -> ConfigItem:
        if self._config["measurement"]["device"]["num_channels"] > len(
            self._config["channels"]
        ):
            channel = {
                "name": data["name"],
                "coupling": data["coupling"],
                "voltage_range": data["voltage_range"],
                "current_range": data["current_range"],
                "metrics": [],
            }
            self._config["channels"].append(channel)
            return ConfigItem(
                id=len(self._config["channels"] - 1),
                name=channel["name"],
                description=json.dumps(channel),
            )
        return None

    async def delete_config_item(self, config_item_id: str):
        ci_id = int(config_item_id)
        del self._config["channels"][ci_id]

    def input_form_edit_config_item(self) -> Dict[str, Dict]:
        return {
            "name": {"type": "StringField"},
            "coupling": {
                "type": "SelectField",
                "options": [
                    {"text": "AC", "value": "AC"},
                    {"text": "ACDC", "value": "ACDC"},
                ],
            },
            "voltage_range": {"type": "NumberField"},
            "current_range": {"type": "NumberField"},
        }

    async def get_config_item(self, config_item_id: str) -> Dict:
        ci_id = int(config_item_id)
        channel_config = self._config["channels"][ci_id]
        return channel_config

    async def update_config_item(self, config_item_id: str, data: Dict) -> ConfigItem:
        ci_id = int(config_item_id)
        channel_config = self._config["channels"][ci_id]
        for key in ["name", "coupling", "voltage_range", "current_range"]:
            if key in data:
                channel_config[key] = data[key]
        return ConfigItem(
            id=ci_id,
            name=channel_config["name"],
            description=json.dumps(channel_config),
        )

    async def input_form_edit_global_config(self) -> Dict[str, Dict]:
        return {
            "chunk_size": {"type": "NumberField"},
            "filter": {"type": "StringField"},
            "sampling_rate": {"type": "NumberField"},
            "serial": {"type": "StringField"},
            "connection": {
                "type": "SelectField",
                "options": [
                    {"text": "serial", "value": "serial"},
                    {"text": "socket", "value": "socket"},
                ],
            },
            "port": {"type": "StringField"},
            "ip": {"type": "StringField"},
            "num_channels": {"type": "NumberField"},
            "mode": {
                "type": "SelectField",
                "options": [
                    {"text": "cycle", "value": "cycle"},
                    {"text": "gapless", "value": "gapless"},
                ],
            },
        }

    async def get_global_config(self) -> Dict:
        return {
            "chunk_size": self._config["chunk_size"],
            "filter": self._config["measurement"]["filter"],
            "sampling_rate": self._config["measurement"]["sampling_rate"],
            "serial": self._config["measurement"]["device"]["serial"],
            "connection": self._config["measurement"]["device"]["connection"],
            "port": self._config["measurement"]["device"].get("port", ""),
            "ip": self._config["measurement"]["device"].get("ip", ""),
            "num_channels": self._config["measurement"]["device"]["num_channels"],
            "mode": self._config["measurement"]["mode"],
        }

    async def update_global_config(self, data: Dict) -> Dict:
        if "chunk_size" in data:
            self._config["chunk_size"] = int(data["chunk_size"])
        if "mode" in data and data["mode"] in ["cycle", "gapless"]:
            self._config["measurement"]["mode"] = data["mode"]
        if "filter" in data:
            self._config["measurement"]["filter"] = data["filter"]
        if "sampling_rate" in data:
            self._config["measurement"]["sampling_rate"] = int(data["sampling_rate"])
        if "serial" in data:
            self._config["measurement"]["device"]["serial"] = data["serial"]
        if "connection" in data and data["connection"] in ["serial", "socket"]:
            self._config["measurement"]["device"]["connection"] = data["connection"]
        if "port" in data:
            self._config["measurement"]["device"]["port"] = data["port"]
        if "ip" in data:
            self._config["measurement"]["device"]["ip"] = data["ip"]
        if "num_channels" in data:
            self._config["measurement"]["device"]["num_channels"] = int(
                data["num_channels"]
            )

        channel_diff = self._config["measurement"]["device"]["num_channels"] - len(
            self._config["channels"]
        )
        if channel_diff > 0:
            empty_begin = len(self._config["channels"]) + 1
            for i in range(channel_diff):
                self._config["channels"].append(
                    {
                        "name": f"emtpy{empty_begin + i}",
                        "coupling": "AC",
                        "voltage_range": 250,
                        "current_range": 16,
                        "metrics": [],
                    }
                )

        return data

    async def get_config(self) -> Dict:
        return self._config
