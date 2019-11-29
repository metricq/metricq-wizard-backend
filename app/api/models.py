import re

from pydantic import BaseModel, validator, root_validator

import metricq


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
