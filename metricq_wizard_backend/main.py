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

import asyncio
from pathlib import Path

import aiohttp_cors
import aiohttp_jinja2
import aiohttp_session
import jinja2
from aiohttp import web
from aiohttp.web_urldispatcher import StaticResource
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from aiohttp_swagger import setup_swagger

from . import api
from .metricq import Configurator, ClusterScanner
from .metricq.source_plugin import AddMetricItem, AvailableMetricItem, ConfigItem
from .settings import Settings

THIS_DIR = Path(__file__).parent


async def startup(app: web.Application):
    settings: Settings = app["settings"]
    client = Configurator(
        settings.token,
        settings.rabbitmq_url,
        settings.couchdb_url,
        settings.rabbitmq_api_url,
        settings.rabbitmq_data_host,
    )

    cluster_scanner = ClusterScanner(
        token=settings.token,
        url=settings.rabbitmq_url,
        couchdb=settings.couchdb_url,
        ignore_patterns=settings.metric_scanner_ignore_patterns,
    )
    app["metricq_client"] = client
    app["cluster_scanner"] = cluster_scanner
    await asyncio.gather(client.connect(), cluster_scanner.connect())
    return


async def cleanup(app: web.Application):
    client: Configurator = app["metricq_client"]
    await client.stop()

    cluster: ClusterScanner = app["cluster_scanner"]
    await cluster.stop()

    return


async def create_app():
    app = web.Application()
    settings = Settings()
    app.update(settings=settings, static_root_url="/static/")

    jinja2_loader = jinja2.FileSystemLoader(str(THIS_DIR / "templates"))
    aiohttp_jinja2.setup(app, loader=jinja2_loader)

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)

    aiohttp_session.setup(
        app, EncryptedCookieStorage(settings.auth_key, cookie_name=settings.cookie_name)
    )

    cors = aiohttp_cors.setup(
        app,
        defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True, expose_headers="*", allow_headers="*"
            )
        },
    )

    api.views.add_routes_to_app(app)

    # from https://github.com/aio-libs/aiohttp-cors/issues/155#issue-297282191
    for route in list(app.router.routes()):
        if not isinstance(route.resource, StaticResource):  # <<< WORKAROUND
            cors.add(route)
    # end

    setup_swagger(
        app,
        ui_version=3,
        swagger_template_path="api_doc/swagger_base.yaml",
        definitions={
            "AddMetricItem": AddMetricItem.schema(),
            "AvailableMetricItem": AvailableMetricItem.schema(),
            "ConfigItem": ConfigItem.schema(),
        },
    )

    app.logger.setLevel("DEBUG")

    return app
