import json
from typing import Dict, Sequence

from app.metricq.source_plugin import (
    SourcePlugin,
    AddMetricItem,
    AvailableMetricItem,
    ConfigItem,
)


class Plugin(SourcePlugin):
    def __init__(self, config):
        self._config = config

    def get_configuration_items(self) -> Sequence[ConfigItem]:
        return [
            ConfigItem(id=ci_id, name=channel["name"], description=json.dumps(channel))
            for ci_id, channel in enumerate(self._config["channels"])
        ]

    async def get_metrics_for_config_item(
        self, config_item_id: str
    ) -> Sequence[AvailableMetricItem]:
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

        return [
            AvailableMetricItem(
                id=metric,
                metric_prefix=f"{channel_config['name']}.{metric}",
                metric_custom_part="",
                # is_active: bool = False
            )
            for metric in available_metrics
        ]

    async def add_metrics_for_config_item(
        self, config_item_id: str, metrics: Sequence[AddMetricItem]
    ):
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

    async def input_form_edit_global_config(self) -> Dict[str, Dict]:
        pass

    async def get_global_config(self) -> Dict:
        pass

    async def update_global_config(self, data: Dict) -> Dict:
        pass

    async def get_config(self) -> Dict:
        pass
