from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.web.decorators import require_preauth_csrf, request_security, services
from app.web.http import ensure_session_transport, json_body, session_response


blueprint = Blueprint("setup", __name__, url_prefix="/api/setup")


@blueprint.get("/status")
def status():
    service = services()
    return jsonify(
        {
            "needsInitialization": service.bootstrap.is_required(),
            "systemName": service.settings.system_name(),
        }
    )


@blueprint.get("/timezones")
def timezones():
    return jsonify(services().system_operations.timezone_catalogue())


@blueprint.post("/initialize")
@require_preauth_csrf
def initialize():
    ensure_session_transport()
    body = json_body()
    issued = services().bootstrap.initialize(
        bootstrap_code=str(body.get("bootstrapCode", "")),
        system_name=str(body.get("systemName", "")),
        admin_username=str(body.get("adminUsername", "")),
        admin_display_name=str(body.get("adminDisplayName", "")),
        password=str(body.get("password", "")),
        customer_name=str(body.get("customerName", "")),
        system_timezone=str(body.get("systemTimezone", "Asia/Hong_Kong")),
        request=request_security().metadata(request),
    )
    return session_response(
        issued,
        {
            "initialized": True,
            "user": {
                "id": issued.context.user_id,
                "username": issued.context.username,
                "displayName": issued.context.display_name,
                "role": issued.context.role.value,
                "mustChangePassword": issued.context.must_change_password,
            },
        },
        status=201,
    )
