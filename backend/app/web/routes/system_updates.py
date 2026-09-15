from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.application.errors import ConflictError
from app.web.http import pagination_args
from app.web.decorators import (
    request_security,
    require_admin,
    require_management_network,
    require_session_csrf,
    services,
)


blueprint = Blueprint("system_updates", __name__, url_prefix="/api/admin/system/updates")


@blueprint.get("")
@require_admin
@require_management_network
def overview():
    page, page_size = pagination_args()
    return jsonify(services().system_updates.overview(page=page, page_size=page_size))


@blueprint.post("/packages")
@require_admin
@require_management_network
@require_session_csrf
def upload_package():
    upload = request.files.get("package")
    if upload is None or not upload.filename:
        raise ConflictError("UPDATE_PACKAGE_REQUIRED", "请选择更新包", status=400)
    result = services().system_updates.upload(
        actor=g.auth,
        filename=upload.filename,
        stream=upload.stream,
        request=request_security().metadata(request),
    )
    return jsonify({"item": result}), 201


@blueprint.post("/<update_id>/apply")
@require_admin
@require_management_network
@require_session_csrf
def apply_update(update_id: str):
    result = services().system_updates.request_apply(
        actor=g.auth,
        update_id=update_id,
        request=request_security().metadata(request),
    )
    return jsonify({"item": result}), 202


@blueprint.post("/<update_id>/retry")
@require_admin
@require_management_network
@require_session_csrf
def retry_update(update_id: str):
    result = services().system_updates.retry_failed(
        actor=g.auth,
        update_id=update_id,
        request=request_security().metadata(request),
    )
    return jsonify({"item": result}), 201


@blueprint.post("/rollback")
@require_admin
@require_management_network
@require_session_csrf
def rollback():
    result = services().system_updates.request_rollback(
        actor=g.auth,
        request=request_security().metadata(request),
    )
    return jsonify({"item": result}), 202
