# metricq-wizard
# Copyright (C) 2024 ZIH, CIDS, Technische Universitaet Dresden,
#                    Federal Republic of Germany
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

from aiocouch import NotFoundError
from aiohttp.web_request import Request
from aiohttp.web_response import json_response
from aiohttp.web_routedef import RouteTableDef

from metricq_wizard_backend.metricq import ClusterScanner

routes = RouteTableDef()


@routes.post("/api/cluster/issues")
async def get_client_list_filtered(request: Request):
    scanner: ClusterScanner = request.app["cluster_scanner"]

    ctx = await request.json()

    return json_response(
        data=await scanner.find_issues(
            page=ctx["currentPage"],
            per_page=ctx["perPage"],
            sorting_key=ctx["sortBy"],
            descending=ctx["sortDesc"],
        )
    )


@routes.delete("/api/cluster/issues/{issue}")
async def delete_issue(request: Request):
    scanner: ClusterScanner = request.app["cluster_scanner"]
    issue = request.match_info["issue"]

    try:
        await scanner.delete_issue_report_by(issue)
        return json_response(data={"status": "ok"})
    except NotFoundError:
        return json_response(data={"error": "report does not exist"}, status=400)


@routes.post("/api/cluster/health_scan")
async def post_health_scan(request: Request):
    # this will initiate another cluster health scan run
    scanner: ClusterScanner = request.app["cluster_scanner"]

    # this is a preliminary check. The real check will be done in the scan task
    # itself. There might be some situations, when this endpoint doesn't return
    # the proper response, but those cases do not really change a thing:
    # 1. A scan just now finished. No need to rerun than anyway.
    # 2. Someone else just now started a scan. Same result.
    if scanner.running:
        return json_response(data={"status": "already running"}, status=429)
    else:
        asyncio.create_task(scanner.run_once())
        return json_response(data={"status": "created"}, status=202)


@routes.get("/api/cluster/health_scan")
async def get_health_scan(request: Request):
    scanner: ClusterScanner = request.app["cluster_scanner"]

    status = "finished"

    if scanner.running:
        status = "running"

    return json_response(data={"status": status})
