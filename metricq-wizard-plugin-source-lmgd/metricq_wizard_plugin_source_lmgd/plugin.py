import json
from typing import Dict, Sequence

from metricq import get_logger

from app.metricq.source_plugin import (
    SourcePlugin,
    AddMetricItem,
    AvailableMetricItem,
    ConfigItem,
    AvailableMetricList,
)

logger = get_logger(__name__)


class Plugin(SourcePlugin):
    def __init__(self, config):
        self._config = config

    def get_config_item_name(self) -> str:
        return "channel"

    def get_configuration_items(self) -> Sequence[ConfigItem]:
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
                    "active_power",
                    "apparent",
                    "apparent_power",
                    "reactive",
                    "reactive_power",
                    "phase",
                    "phi",
                ]
            )

        activated_metrics = {}
        for metric in channel_config["metrics"]:
            split_metric = metric.split("@", 1)
            if len(split_metric) > 1:
                activated_metrics[split_metric[0]] = f"{split_metric[1]}"
            else:
                activated_metrics[split_metric[0]] = None

        available_metric_items = []
        for metric in available_metrics:
            custom_columns = {
                "metric_name": {
                    "_": {
                        "type": "LabelField",
                        "value": f"{channel_config['name']}.{metric}",
                    }
                }
            }
            if self._config["measurement"]["mode"] == "gapless":
                custom_columns["metric_name"]["bandwidth"] = {
                    "type": "SelectField",
                    "options": [
                        {"text": " (wide)", "value": None},
                        {"text": ".narrow", "value": "narrow"},
                    ],
                    "value": activated_metrics.get(metric, None),
                }
            available_metric_items.append(
                AvailableMetricItem(
                    id=metric,
                    custom_columns=custom_columns,
                    is_active=metric in activated_metrics,
                )
            )

        return AvailableMetricList(
            columns={"metric_name": "Metric Name"}, metrics=available_metric_items
        )

    async def add_metrics_for_config_item(
        self, config_item_id: str, metrics: Sequence[AddMetricItem]
    ) -> Sequence[str]:
        ci_id = int(config_item_id)
        channel_config = self._config["channels"][ci_id]
        old_metrics = channel_config["metrics"]
        channel_config["metrics"] = []
        for metric in metrics:
            bandwidth = None
            if "metric_name" in metric.custom_columns_values:
                bandwidth = metric.custom_columns_values["metric_name"].get("bandwidth")
            if bandwidth:
                channel_config["metrics"].append(f"{metric.id}@{bandwidth}")
            else:
                channel_config["metrics"].append(metric.id)

        new_metrics = set([metric.id for metric in metrics]) - set(old_metrics)

        return [f"{channel_config['name']}.{metric}" for metric in new_metrics]

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
