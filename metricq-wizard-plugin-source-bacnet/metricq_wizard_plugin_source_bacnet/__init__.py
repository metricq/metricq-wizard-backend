from typing import Dict

from app.metricq.source_plugin import PluginRPCFunctionType
from .plugin import Plugin


def get_plugin(config: Dict, rpc_function: PluginRPCFunctionType):
    return Plugin(config, rpc_function)
