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

from pathlib import Path

import aiohttp_jinja2
import aiohttp_session
import jinja2
from aiohttp import web
from aiohttp.web_urldispatcher import StaticResource
from aiohttp_session.cookie_storage import EncryptedCookieStorage
import aiohttp_cors

from .api.views import routes as api_routes
from .metricq import Configurator
from .settings import Settings
from .views import index

THIS_DIR = Path(__file__).parent


async def startup(app: web.Application):
    settings: Settings = app["settings"]
    client = Configurator(
        settings.token,
        settings.amqp_server,
        settings.couchdb_url,
        settings.couchdb_user,
        settings.couchdb_password,
        event_loop=app.loop,
    )
    app["metricq_client"] = client
    await client.connect()
    return


async def cleanup(app: web.Application):
    client: Configurator = app["metricq_client"]
    await client.stop()
    return


async def create_app(loop):
    app = web.Application(loop=loop)
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

    app.router.add_get("/", index, name="index")
    app.router.add_routes(api_routes)

    # from https://github.com/aio-libs/aiohttp-cors/issues/155#issue-297282191
    for route in list(app.router.routes()):
        if not isinstance(route.resource, StaticResource):  # <<< WORKAROUND
            cors.add(route)
    # end

    setup_swagger(app)

    app.logger.setLevel("DEBUG")

    return app
