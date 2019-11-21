from urllib.parse import urlparse

from pydantic import BaseSettings


class Settings(BaseSettings):
    """
    See https://pydantic-docs.helpmanual.io/#settings for details on using and overriding this
    """
    name = 'metricq-configurator-prototype-backend'
    pg_dsn = 'postgres://postgres@localhost:5432/demo_app'
    auth_key = 'u0zlRwkhWiMCaIfNuS_eIF9PXMVzw9aSYA-88jI-Y48='
    cookie_name = 'metricq_configurator_prototype_backend'

    @property
    def _pg_dsn_parsed(self):
        return urlparse(self.pg_dsn)

    @property
    def pg_name(self):
        return self._pg_dsn_parsed.path.lstrip('/')
