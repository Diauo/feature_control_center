from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.web.decorators import request_security, require_admin, require_management_network, services
from app.web.http import pagination_args, pagination_payload


blueprint = Blueprint("system_operations", __name__, url_prefix="/api/admin/system")


@blueprint.get("/status")
@require_admin
@require_management_network
def status():
    return jsonify(services().system_operations.status())


@blueprint.get("/timezones")
@require_admin
@require_management_network
def timezones():
    return jsonify(services().system_operations.timezone_catalogue())


@blueprint.get("/release-history")
@require_admin
@require_management_network
def release_history():
    page, page_size = pagination_args()
    history = services().system_operations.release_history()
    start = (page - 1) * page_size
    return jsonify({"items": history[start:start + page_size], "pagination": pagination_payload(page, page_size, len(history))})


@blueprint.get("/logs")
@require_admin
@require_management_network
def logs():
    try:
        limit = int(request.args.get("limit", "200"))
    except ValueError:
        limit = 200
    return jsonify(
        services().system_operations.list_logs(
            service=request.args.get("service", "all"),
            date=request.args.get("date", ""),
            level=request.args.get("level", ""),
            limit=limit,
            cursor=request.args.get("cursor", ""),
        )
    )


@blueprint.get("/logs/download")
@require_admin
@require_management_network
def download_log():
    downloaded = services().system_operations.download_log(
        actor=g.auth,
        service=request.args.get("service", ""),
        date=request.args.get("date", ""),
        request=request_security().metadata(request),
    )
    response = Response(downloaded.content, mimetype="application/x-ndjson")
    response.headers["Content-Disposition"] = f'attachment; filename="{downloaded.filename}"'
    response.headers["X-Content-SHA256"] = downloaded.sha256
    response.headers["Cache-Control"] = "no-store"
    return response
