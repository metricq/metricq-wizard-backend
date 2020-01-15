from .plugin import Plugin


def get_plugin(config):
    return Plugin(config)
