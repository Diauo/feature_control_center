from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.application.auth import AuthContext
from app.application.errors import ApplicationError
from app.web.decorators import (
    request_security,
    require_management_network,
    require_menu,
    require_session_csrf,
    services,
)
from app.web.http import json_body, pagination_args, pagination_payload


blueprint = Blueprint("admin", __name__, url_prefix="/api/admin")


@blueprint.get("/users")
@require_menu("users")
@require_management_network
def list_users():
    page, page_size = pagination_args()
    items, total = services().identity.list_users(
        g.auth, page=page, page_size=page_size, role=request.args.get("role", "").strip().lower()
    )
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.post("/users")
@require_menu("users")
@require_management_network
@require_session_csrf
def create_user():
    body = json_body()
    created = services().identity.create_user(
        actor=g.auth,
        username=str(body.get("username", "")),
        display_name=str(body.get("displayName", "")),
        role=str(body.get("role", "operator")),
        menu_keys=body["menuKeys"] if "menuKeys" in body else None,
        customer_ids=_string_list(body.get("customerIds", [])),
        request=request_security().metadata(request),
    )
    return jsonify({"user": created.user, "temporaryPassword": created.temporary_password}), 201


@blueprint.patch("/users/<user_id>")
@require_menu("users")
@require_management_network
@require_session_csrf
def update_user(user_id: str):
    body = json_body()
    display_name = str(body["displayName"]) if "displayName" in body else None
    role = str(body["role"]) if "role" in body else None
    active_value = body.get("isActive")
    is_active = active_value if isinstance(active_value, bool) else None
    customer_ids = _string_list(body["customerIds"]) if "customerIds" in body else None
    user = services().identity.update_user(
        actor=g.auth,
        user_id=user_id,
        display_name=display_name,
        role=role,
        is_active=is_active,
        customer_ids=customer_ids,
        menu_keys=body["menuKeys"] if "menuKeys" in body else None,
        request=request_security().metadata(request),
    )
    return jsonify({"user": user})


@blueprint.put("/users/<user_id>/customers")
@require_menu("users")
@require_management_network
@require_session_csrf
def set_user_customers(user_id: str):
    body = json_body()
    user = services().identity.set_user_customers(
        actor=g.auth,
        user_id=user_id,
        customer_ids=_string_list(body.get("customerIds", [])),
        request=request_security().metadata(request),
    )
    return jsonify({"user": user})


@blueprint.post("/users/<user_id>/reset-password")
@require_menu("users")
@require_management_network
@require_session_csrf
def reset_password(user_id: str):
    temporary_password = services().identity.reset_password(
        actor=g.auth,
        user_id=user_id,
        request=request_security().metadata(request),
    )
    return jsonify({"temporaryPassword": temporary_password})


@blueprint.post("/users/<user_id>/revoke-sessions")
@require_menu("users")
@require_management_network
@require_session_csrf
def revoke_sessions(user_id: str):
    actor: AuthContext = g.auth
    services().auth.require_recent_auth(actor)
    count = services().auth.revoke_all_for_user(
        actor=actor,
        user_id=user_id,
        reason="admin_revoked",
        request=request_security().metadata(request),
    )
    return jsonify({"revokedSessions": count})


@blueprint.delete("/users/<user_id>")
@require_menu("users")
@require_management_network
@require_session_csrf
def delete_user(user_id: str):
    return jsonify(services().identity.delete_user(
        actor=g.auth,
        user_id=user_id,
        request=request_security().metadata(request),
    ))


@blueprint.get("/customers")
@require_menu("customers")
@require_management_network
def list_customers():
    page, page_size = pagination_args()
    items, total = services().identity.list_customers(g.auth, page=page, page_size=page_size)
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.post("/customers")
@require_menu("customers")
@require_management_network
@require_session_csrf
def create_customer():
    body = json_body()
    customer = services().identity.create_customer(
        actor=g.auth,
        name=str(body.get("name", "")),
        description=str(body.get("description", "")),
        request=request_security().metadata(request),
    )
    return jsonify({"customer": customer}), 201


@blueprint.patch("/customers/<customer_id>")
@require_menu("customers")
@require_management_network
@require_session_csrf
def update_customer(customer_id: str):
    body = json_body()
    name = str(body["name"]) if "name" in body else None
    description = str(body["description"]) if "description" in body else None
    active_value = body.get("isActive")
    is_active = active_value if isinstance(active_value, bool) else None
    customer = services().identity.update_customer(
        actor=g.auth,
        customer_id=customer_id,
        name=name,
        description=description,
        is_active=is_active,
        request=request_security().metadata(request),
    )
    return jsonify({"customer": customer})


@blueprint.get("/audit-logs")
@require_menu("audit")
@require_management_network
def list_audit_logs():
    page, page_size = pagination_args()
    def optional_timestamp(name: str) -> int | None:
        raw = request.args.get(name, "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            raise ApplicationError("INVALID_AUDIT_FILTER", "审计时间筛选条件无效", status=400)

    items, total = services().identity.list_audit_logs(
        g.auth,
        page=page,
        page_size=page_size,
        category=request.args.get("category", "ALL").upper(),
        action=request.args.get("action", "").strip(),
        outcome=request.args.get("outcome", "").strip(),
        client_ip=request.args.get("clientIp", "").strip(),
        occurred_from=optional_timestamp("from"),
        occurred_to=optional_timestamp("to"),
    )
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ApplicationError("INVALID_CUSTOMER_IDS", "客户列表格式无效", status=400)
    return value
