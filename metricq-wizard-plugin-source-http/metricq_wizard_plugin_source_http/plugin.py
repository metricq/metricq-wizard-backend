from typing import Sequence, Dict, Any
from urllib.parse import urljoin

import aiohttp

from metricq_wizard_backend.metricq.source_plugin import (
    SourcePlugin,
    AddMetricItem,
    AvailableMetricItem,
    ConfigItem,
)


class Plugin(SourcePlugin):
    def __init__(self, config):
        hosts = {}
        for i, host_config in enumerate(config["hosts"]):
            host_id = f"host{i}"
            host_item: Dict[str, Any] = {"from_config": True}
            host_item.update(host_config)

            del host_item["metrics"]
            paths = set()
            for metric_config in host_config["metrics"].values():
                paths.add(metric_config["path"])
            path_dict = {}
            for j, path in enumerate(paths):
                path_dict[f"path{j}"] = path
            host_item["paths"] = path_dict
            hosts[host_id] = host_item
        self._hosts = hosts
        self._config = config

    def get_configuration_items(self) -> Sequence[ConfigItem]:
        return [
            ConfigItem(
                id=f"{host_id}/{path_id}",
                name=host_config["names"],
                description=f"{host_config['hosts']}{path}",
            )
            for host_id, host_config in self._hosts.items()
            for path_id, path in host_config["paths"].items()
        ]

    async def get_metrics_for_config_item(
        self, config_item_id: str
    ) -> Sequence[AvailableMetricItem]:
        host_id, path_id = config_item_id.split("/")
        host_data = self._hosts[host_id]
        if "insecure" in host_data and host_data["insecure"]:
            host_url = f"http://{host_data['hosts']}"
        else:
            host_url = f"https://{host_data['hosts']}"

        url = urljoin(host_url, host_data["paths"][path_id])

        auth = None
        if host_data["login_type"] == "basic":
            auth = aiohttp.BasicAuth(
                login=host_data["user"], password=host_data["password"]
            )

        active_metrics = []

        for host_config in self._config["hosts"] + [None]:
            if host_config["hosts"] == host_data["hosts"]:
                break
        if host_config:
            for metric_name, metric_config in host_config["metrics"].items():
                if metric_config["path"] == host_data["paths"][path_id]:
                    active_metrics.append(
                        metric_config["plugin_params"]["json_path"][2:]
                    )

        async with aiohttp.ClientSession(auth=auth) as session:
            response = await session.get(url)
            data = await response.json()
            return [
                AvailableMetricItem(
                    id=json_identifier,
                    current_value=data[json_identifier],
                    metric_prefix=f"{host_data['names']}.",
                    metric_custom_part=json_identifier,
                    is_active=json_identifier in active_metrics,
                    has_custom_part=True,
                )
                for json_identifier in data
            ]

    async def add_metrics_for_config_item(
        self, config_item_id: str, metrics: Sequence[AddMetricItem]
    ) -> Sequence[str]:
        host_id, path_id = config_item_id.split("/")
        host_data = self._hosts[host_id]
        path = host_data["paths"][path_id]
        if host_data["from_config"]:
            for host_config in self._config["hosts"] + [None]:
                if host_config["hosts"] == host_data["hosts"]:
                    break
            if host_config:
                for metric in metrics:
                    metric_config = {
                        "path": path,
                        "plugin": "json",
                        "plugin_params": {"json_path": f"$.{metric.id}"},
                    }
                    if metric.metric_custom_part in host_config["metrics"]:
                        host_config["metrics"][metric.metric_custom_part].update(
                            metric_config
                        )
                    else:
                        host_config["metrics"][
                            metric.metric_custom_part
                        ] = metric_config
            return [f"{host_config['names']}.{metric}" for metric in metrics]
        else:
            # TODO Generate new host entry in config
            pass
        return []

    def input_form_add_config_item(self) -> Dict[str, Dict]:
        return {
            "host": {
                "type": "SelectField",
                "options": ["New..."]
                + [host_config["hosts"] for host_config in self._hosts.values()],
                "label": "Host",
            },
            "newHost": {
                "type": "StringField",
                "label": "New hostname (when New... is selected for host)",
            },
            "loginType": {
                "type": "SelectField",
                "options": ["none", "basic", "cookie"],
                "label": "Select authentication type for host",
            },
            "user": {"type": "StringField", "label": "Username (if apply)"},
            "password": {"type": "PasswordField", "label": "Password (if apply)"},
            "path": {
                "type": "StringField",
                "label": "URL path component, where metrics should be collected",
            },
        }

    async def add_config_item(self, data: Dict) -> ConfigItem:
        if data["host"] == "New...":
            hostname = data["newHost"]
        else:
            hostname = data["host"]

        for host_id, host_config in list(self._hosts.items()) + [(None, None)]:
            if host_config["hosts"] == hostname:
                break

        if host_config:
            j = len(host_config["paths"])
            host_config["paths"][f"path{j}"] = data["path"]
            path_id = f"path{j}"
        else:
            i = len(self._hosts)
            host_id = f"host{i}"
            self._hosts[host_id] = {
                "from_config": False,
                "hosts": hostname,
                "login_type": data["loginType"],
                "user": data["user"],
                "password": data["password"],
                "paths": {"path0": data["path"]},
            }
            path_id = "path0"

        return ConfigItem(
            id=f"{host_id}/{path_id}",
            name=host_config["names"],
            description=f"{host_config['hosts']}{data['path']}",
        )

    def input_form_edit_config_item(self) -> Dict[str, Dict]:
        return {
            "host": {
                "type": "SelectField",
                "options": ["New..."]
                + [host_config["hosts"] for host_config in self._hosts.values()],
            },
            "new_host": {"type": "StringField"},
            "loginType": {
                "type": "SelectField",
                "options": ["none", "basic", "cookie"],
            },
            "user": {"type": "StringField"},
            "password": {"type": "PasswordField"},
            "path": {"type": "StringField"},
        }

    async def get_config_item(self, config_item_id: str) -> Dict:
        host_id, path_id = config_item_id.split("/")
        host_data = self._hosts[host_id]
        path = host_data["paths"][path_id]

        for host_id, host_config in list(self._hosts.items()) + [(None, None)]:
            if host_config["hosts"] == host_data["hosts"]:
                break

        if host_config:
            return {
                "host": host_data["hosts"],
                "loginType": host_config["login_type"],
                "user": host_config["user"],
                "password": None,
                "path": path,
            }

        return {}

    async def update_config_item(self, config_item_id: str, data: Dict):
        host_id, path_id = config_item_id.split("/")
        host_data = self._hosts[host_id]

        if data["host"] == "New...":
            hostname = data["newHost"]
        else:
            hostname = data["host"]

        for host_id, host_config in list(self._hosts.items()) + [(None, None)]:
            if host_config["hosts"] == host_data["hosts"]:
                break

        if host_config:
            host_config["paths"][path_id] = data["path"]
            host_config.update(
                {
                    "hosts": hostname,
                    "login_type": data["loginType"],
                    "user": data["user"],
                }
            )
            password = data.get("password", None)
            if password:
                host_config["password"] = password

            # TODO also update the config, maybe warn the user that login related changes affect all config items for this path

            return ConfigItem(
                id=f"{host_id}/{path_id}",
                name=host_config["names"],
                description=f"{host_config['hosts']}{data['path']}",
            )

        return None

    async def input_form_edit_global_config(self) -> Dict[str, Dict]:
        return {
            "interval": {"type": "NumberField"},
            "http_timeout": {"type": "NumberField"},
        }

    async def get_global_config(self) -> Dict:
        return {
            "interval": self._config["interval"],
            "http_timeout": self._config["http_timeout"],
        }

    async def update_global_config(self, data: Dict) -> Dict:
        if "interval" in data:
            self._config["interval"] = data["interval"]

        if "http_timeout" in data:
            self._config["http_timeout"] = data["http_timeout"]

        return data

    async def get_config(self) -> Dict:
        return self._config
