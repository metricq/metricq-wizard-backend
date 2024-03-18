from .client import routes as client_routes
from .explorer import routes as explorer_routes
from .metric import routes as metric_routes
from .source import routes as source_routes
from .topology import routes as topology_routes
from .transformer import routes as transformer_routes
from .cluster import routes as cluster_routes


def add_routes_to_app(app):
    app.router.add_routes(client_routes)
    app.router.add_routes(explorer_routes)
    app.router.add_routes(metric_routes)
    app.router.add_routes(source_routes)
    app.router.add_routes(transformer_routes)
    app.router.add_routes(topology_routes)
    app.router.add_routes(cluster_routes)
