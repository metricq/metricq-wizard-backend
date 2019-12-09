from typing import Sequence, Dict, Optional, Type
from urllib.parse import urljoin

import aiohttp
import pydantic


class _InputModelAvailableMetrics(pydantic.BaseModel):
    host: str
    loginType: str
    user: Optional[str]
    password: Optional[str]
    path: str


class _SourceModel(pydantic.BaseModel):
    id: str
    searchParams: _InputModelAvailableMetrics


class _InputModelNewMetric(pydantic.BaseModel):
    metricName: str
    metricId: str
    source: _SourceModel


class Plugin:
    def input_form_get_available_metrics(self) -> Dict[str, Dict]:
        return {
            "host": {"type": "StringField"},
            "loginType": {
                "type": "SelectField",
                "options": ["none", "basic", "cookie"],
            },
            "user": {"type": "StringField"},
            "password": {"type": "PasswordField"},
            "path": {"type": "StringField"},
        }

    def input_model_get_available_metrics(self) -> Type[_InputModelAvailableMetrics]:
        return _InputModelAvailableMetrics

    async def get_available_metrics(
        self, input_model: _InputModelAvailableMetrics
    ) -> Sequence[Dict[str, Dict]]:
        url = urljoin(input_model.host, input_model.path)
        async with aiohttp.ClientSession() as session:
            response = await session.get(url)
            data = await response.json()
            return [
                {"id": possible_metric, "current_value": data[possible_metric]}
                for possible_metric in data
            ]

    def input_form_create_new_metric(self) -> Dict[str, Dict]:
        return {"metricName": {"type": "StringField"}}

    def input_model_create_new_metric(self) -> Type[_InputModelNewMetric]:
        return _InputModelNewMetric

    async def create_new_metric(
        self, metric_data: _InputModelNewMetric, old_config: Dict
    ) -> Dict:
        new_config = old_config
        found = False
        # check if host in old_config
        for host_config in new_config["hosts"]:
            if metric_data.source.searchParams.host in host_config["hosts"]:
                # TODO add support for hostlist and list of strings
                metric_prefix = host_config["names"]
                if metric_data.metricName.startswith(metric_prefix):
                    found = True
                    metric_suffix = metric_data.metricName[len(metric_prefix) :]
                    if metric_suffix in host_config["metrics"]:
                        # update metric
                        metric_config = {
                            "path": metric_data.source.searchParams.path,
                            "plugin": "json",
                            "plugin_params": {"json_path": f"$.{metric_data.metricId}"},
                        }
                        host_config["metrics"][metric_suffix].update(metric_config)
                    else:
                        metric_config = {
                            "path": metric_data.source.searchParams.path,
                            "plugin": "json",
                            "plugin_params": {"json_path": f"$.{metric_data.metricId}"},
                        }
                        host_config["metrics"][metric_suffix] = metric_config

        #  create new host entry
        if not found:
            host_config = {
                "hosts": metric_data.source.searchParams.host,
                "names": "",
                "login_type": metric_data.source.searchParams.loginType,
                "user": metric_data.source.searchParams.user,
                "password": metric_data.source.searchParams.password,
                "metrics": {
                    metric_data.metricName: {
                        "path": metric_data.source.searchParams.path,
                        "plugin": "json",
                        "plugin_params": {"json_path": f"$.{metric_data.metricId}"},
                    }
                },
            }
            new_config["hosts"].append(host_config)
        return new_config
