from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from app.application.auth import AuthContext
from app.domain.identity import ordered_menu_keys
from app.web.decorators import (
    optional_auth,
    request_security,
    require_auth,
    require_preauth_csrf,
    require_session_csrf,
    services,
)
from app.web.http import clear_session_cookies, ensure_session_transport, json_body, session_response


blueprint = Blueprint("auth", __name__, url_prefix="/api")


@blueprint.get("/auth/csrf")
def csrf():
    context = optional_auth()
    if context is not None:
        return jsonify({"csrfToken": context.csrf_token, "authenticated": True})
    token = services().preauth_csrf.issue(services().clock.now())
    return jsonify({"csrfToken": token.value, "expiresAt": token.expires_at, "authenticated": False})


@blueprint.post("/auth/login")
@require_preauth_csrf
def login():
    ensure_session_transport()
    body = json_body()
    issued = services().auth.login(
        username=str(body.get("username", "")),
        password=str(body.get("password", "")),
        request=request_security().metadata(request),
    )
    return session_response(
        issued,
        {
            "user": {
                "id": issued.context.user_id,
                "username": issued.context.username,
                "displayName": issued.context.display_name,
                "role": issued.context.role.value,
                "mustChangePassword": issued.context.must_change_password,
                "menuKeys": ordered_menu_keys(issued.context.menus),
            }
        },
    )


@blueprint.post("/auth/logout")
@require_auth(allow_password_change=True)
@require_session_csrf
def logout():
    context: AuthContext = g.auth
    services().auth.logout(context, request_security().metadata(request))
    response = jsonify({"loggedOut": True})
    clear_session_cookies(response)
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
    return response


@blueprint.post("/auth/reauthenticate")
@require_auth()
@require_session_csrf
def reauthenticate():
    body = json_body()
    context: AuthContext = g.auth
    updated = services().auth.reauthenticate(
        context,
        str(body.get("password", "")),
        request_security().metadata(request),
    )
    return jsonify({"reauthenticated": True, "reauthenticatedAt": updated.reauthenticated_at})


@blueprint.post("/auth/password")
@require_auth(allow_password_change=True)
@require_session_csrf
def change_password():
    body = json_body()
    context: AuthContext = g.auth
    issued = services().auth.change_password(
        context,
        str(body.get("currentPassword", "")),
        str(body.get("newPassword", "")),
        request_security().metadata(request),
    )
    return session_response(issued, {"passwordChanged": True})


@blueprint.get("/me")
@require_auth(allow_password_change=True)
def me():
    context: AuthContext = g.auth
    customers = services().identity.list_authorized_customers(context)
    return jsonify(
        {
            "user": {
                "id": context.user_id,
                "username": context.username,
                "displayName": context.display_name,
                "role": context.role.value,
                "mustChangePassword": context.must_change_password,
                "menuKeys": ordered_menu_keys(context.menus),
            },
            "customers": customers,
            "csrfToken": context.csrf_token,
        }
    )
