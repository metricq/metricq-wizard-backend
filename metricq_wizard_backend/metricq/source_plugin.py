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
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Sequence

import pydantic

PluginRPCFunctionType = Callable[[str, Optional[Any], Optional[int], Any], Any]


class AddMetricItem(pydantic.BaseModel):
    id: str
    custom_columns_values: Dict

    class Config:
        allow_population_by_alias = True

        @classmethod
        def alias_generator(cls, string: str) -> str:
            return re.sub(r"_([a-z])", lambda m: m.group(1).upper(), string)


class AvailableMetricItem(pydantic.BaseModel):
    id: str
    is_active: bool = False
    custom_columns: Dict

    class Config:
        allow_population_by_alias = True

        @classmethod
        def alias_generator(cls, string: str) -> str:
            return re.sub(r"_([a-z])", lambda m: m.group(1).upper(), string)


class AvailableMetricList(pydantic.BaseModel):
    columns: Dict[str, str]
    metrics: Sequence[AvailableMetricItem]


class ConfigItem(pydantic.BaseModel):
    id: str
    name: str
    description: str = ""


class SourcePlugin(ABC):
    @abstractmethod
    def __init__(self, config: Dict, rpc_function: PluginRPCFunctionType):
        raise NotImplementedError

    @abstractmethod
    def get_config_item_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_configuration_items(self) -> Sequence[ConfigItem]:
        raise NotImplementedError

    @abstractmethod
    async def get_metrics_for_config_item(
        self, config_item_id: str
    ) -> AvailableMetricList:
        raise NotImplementedError

    @abstractmethod
    async def add_metrics_for_config_item(
        self,
        config_item_id: str,
        metrics: Sequence[AddMetricItem],
        not_selected_metric_ids: Sequence[str],
    ) -> Sequence[str]:
        raise NotImplementedError

    @abstractmethod
    def input_form_add_config_item(self) -> Dict[str, Dict]:
        raise NotImplementedError

    @abstractmethod
    async def add_config_item(self, data: Dict) -> ConfigItem:
        raise NotImplementedError

    @abstractmethod
    def input_form_edit_config_item(self) -> Dict[str, Dict]:
        raise NotImplementedError

    @abstractmethod
    async def get_config_item(self, config_item_id: str) -> Dict:
        raise NotImplementedError

    @abstractmethod
    async def update_config_item(self, config_item_id: str, data: Dict) -> ConfigItem:
        raise NotImplementedError

    @abstractmethod
    async def delete_config_item(self, config_item_id: str):
        raise NotImplementedError

    @abstractmethod
    async def input_form_edit_global_config(self) -> Dict[str, Dict]:
        raise NotImplementedError

    @abstractmethod
    async def get_global_config(self) -> Dict:
        raise NotImplementedError

    @abstractmethod
    async def update_global_config(self, data: Dict) -> Dict:
        raise NotImplementedError

    @abstractmethod
    async def get_config(self) -> Dict:
        raise NotImplementedError


EntryPointType = Callable[[Dict, PluginRPCFunctionType], SourcePlugin]
