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
from typing import List

import metricq
from pydantic import BaseModel, root_validator


class Timedelta(metricq.Timedelta):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return cls.from_string(v)


class MetricDatabaseConfiguration(BaseModel):
    id: str
    database_id: str
    interval_min: Timedelta
    interval_max: Timedelta
    interval_factor: int

    @root_validator
    def check_interval_min_divisible_by_factor(cls, values):
        interval_min = values.get("interval_min")
        interval_factor = values.get("interval_factor")

        if interval_min.ns % interval_factor != 0:
            raise ValueError(
                f"interval_min of {interval_min} not divisible by {interval_factor}"
            )
        return values

    @root_validator
    def check_interval_min_is_positive(cls, values):
        interval_min = values.get("interval_min")
        if interval_min.ns <= 0:
            raise ValueError("interval_min not positive")
        return values

    @root_validator
    def check_interval_max_lager_then_interval_min(cls, values):
        interval_min = values.get("interval_min")
        interval_max = values.get("interval_max")

        if interval_max < interval_min:
            raise ValueError(
                f"interval_max ({interval_max})not larger than interval_min ({interval_min})"
            )
        return values

    class Config:
        json_encoders = {metricq.Timedelta: lambda td: f"{td.ms:.0f}ms"}

        @classmethod
        def alias_generator(cls, string: str) -> str:
            return re.sub(r"_([a-z])", lambda m: m.group(1).upper(), string)


class MetricDatabaseConfigurations(BaseModel):
    database_configurations: List[MetricDatabaseConfiguration]

    class Config:
        json_encoders = {metricq.Timedelta: lambda td: f"{td.ms:.0f}ms"}

        @classmethod
        def alias_generator(cls, string: str) -> str:
            return re.sub(r"_([a-z])", lambda m: m.group(1).upper(), string)
