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

from abc import ABC, abstractmethod
from typing import Sequence, Dict, Type

import pydantic


class SourcePlugin(ABC):
    @abstractmethod
    def input_form_get_available_metrics(self) -> Dict[str, Dict]:
        raise NotImplementedError

    @abstractmethod
    def input_model_get_available_metrics(self) -> Type[pydantic.BaseModel]:
        raise NotImplementedError

    @abstractmethod
    async def get_available_metrics(
        self, input_model: pydantic.BaseModel
    ) -> Sequence[Dict[str, Dict]]:
        raise NotImplementedError

    @abstractmethod
    def input_form_create_new_metric(self) -> Dict[str, Dict]:
        raise NotImplementedError

    @abstractmethod
    def input_model_create_new_metric(self) -> Type[pydantic.BaseModel]:
        raise NotImplementedError

    @abstractmethod
    async def create_new_metric(
        self, metric_data: pydantic.BaseModel, old_config: Dict
    ) -> Dict:
        raise NotImplementedError
