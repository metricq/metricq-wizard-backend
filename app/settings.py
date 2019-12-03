from urllib.parse import urlparse

from pydantic import BaseSettings


class Settings(BaseSettings):
    """
    See https://pydantic-docs.helpmanual.io/#settings for details on using and overriding this
    """

    name = "metricq-wizard-backend"
    auth_key = "u0zlRwkhWiMCaIfNuS_eIF9PXMVzw9aSYA-88jI-Y48="
    cookie_name = "metricq_wizard_backend"
    token = name
    amqp_server = "amqp://guest:guest@localhost/"
    couchdb_url = "http://localhost:5984"
    couchdb_user = "admin"
    couchdb_password = "admin"
