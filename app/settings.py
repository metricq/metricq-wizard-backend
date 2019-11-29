from urllib.parse import urlparse

from pydantic import BaseSettings


class Settings(BaseSettings):
    """
    See https://pydantic-docs.helpmanual.io/#settings for details on using and overriding this
    """

    name = "metricq-configurator-prototype-backend"
    auth_key = "u0zlRwkhWiMCaIfNuS_eIF9PXMVzw9aSYA-88jI-Y48="
    cookie_name = "metricq_configurator_prototype_backend"
