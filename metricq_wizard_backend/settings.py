from cryptography.fernet import Fernet
from pydantic import AnyHttpUrl, BaseSettings, stricturl


class Settings(BaseSettings):
    """
    See https://pydantic-docs.helpmanual.io/#settings for details on using and overriding this
    """

    name = "metricq-wizard-backend"

    # generate the auth key with cryptography.fernet.Fernet.generate_key() and set it via env
    auth_key: str = Fernet.generate_key()
    cookie_name = "metricq_wizard_backend"
    token = name
    rabbitmq_url: stricturl(
        tld_required=False, allowed_schemes={"amqp", "amqps"}  # noqa: F821
    ) = "amqp://admin:admin@localhost/"
    couchdb_url: AnyHttpUrl = "http://localhost:5984"
    rabbitmq_api_url: AnyHttpUrl = "http://admin:admin@localhost:15672"
    rabbitmq_data_host: str = "/"
    dry_run = False

    class Config:
        env_file = ".env"
