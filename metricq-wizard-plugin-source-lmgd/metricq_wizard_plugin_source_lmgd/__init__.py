from metricq_wizard_backend.metricq.source_plugin import PluginRPCFunctionType

from .plugin import Plugin


def get_plugin(config, rpc_function: PluginRPCFunctionType):
    return Plugin(config, rpc_function=rpc_function)
