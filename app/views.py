from aiohttp.hdrs import METH_POST
from aiohttp.web_exceptions import HTTPFound
from aiohttp.web_response import Response
from aiohttp_jinja2 import template
from aiohttp_session import get_session
from pydantic import BaseModel, ValidationError, constr


@template("index.jinja")
async def index(request):
    """
    This is the view handler for the "/" url.

    :param request: the request object see http://aiohttp.readthedocs.io/en/stable/web_reference.html#request
    :return: context for the template.
    ---
    """
    # Note: we return a dict not a response because of the @template decorator
    return {
        "title": request.app["settings"].name,
        "intro": "Success! you've setup a basic aiohttp app.",
    }
