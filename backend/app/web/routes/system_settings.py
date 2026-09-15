from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.web.decorators import (
    request_security,
    require_admin,
    require_management_network,
    require_session_csrf,
    services,
)
from app.web.http import json_body


blueprint = Blueprint("system_settings", __name__, url_prefix="/api/admin/settings")


@blueprint.get("")
@require_admin
@require_management_network
def get_settings():
    client_ip = request_security().resolve(request).client_ip
    return jsonify({"values": services().system_settings.read(
        client_ip,
        actor=g.auth,
        request=request_security().metadata(request),
    )})


@blueprint.put("")
@require_admin
@require_management_network
@require_session_csrf
def update_settings():
    body = json_body()
    values = body.get("values", body)
    if not isinstance(values, dict):
        values = {}
    client_ip = request_security().resolve(request).client_ip
    return jsonify({"values": services().system_settings.update(
        actor=g.auth,
        values=values,
        client_ip=client_ip,
        request=request_security().metadata(request),
    )})
