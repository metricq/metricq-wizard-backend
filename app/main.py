from pathlib import Path

import aiohttp_jinja2
import aiohttp_session
import jinja2
from aiohttp import web
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from .settings import Settings
from .views import index

THIS_DIR = Path(__file__).parent


async def startup(app: web.Application):
    settings: Settings = app["settings"]
    return


async def cleanup(app: web.Application):
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

    app.router.add_get("/", index, name="index")
    return app
