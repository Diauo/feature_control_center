from __future__ import annotations

import json

from conftest import initialize, preauth_csrf
from app.infrastructure.models import SystemSettingModel
from app.web.request_security import RequestSecurityResolver


def test_forwarded_headers_are_ignored_until_direct_proxy_is_trusted(app):
    resolver: RequestSecurityResolver = app.extensions["fcc_request_security"]
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.20.30.40"},
        headers={"X-Forwarded-For": "203.0.113.8", "X-Forwarded-Proto": "https"},
    ):
        from flask import request

        state = resolver.resolve(request)
        assert state.client_ip == "10.20.30.40"
        assert state.secure is False

    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        setting = db.get(SystemSettingModel, "security.trusted_proxy_cidrs")
        setting.value_json = json.dumps(["10.20.30.0/24"])

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "10.20.30.40"},
        headers={
            "X-Forwarded-For": "203.0.113.8, 10.20.30.30",
            "X-Forwarded-Proto": "https",
        },
    ):
        from flask import request

        state = resolver.resolve(request)
        assert state.client_ip == "203.0.113.8"
        assert state.secure is True


def test_public_mode_refuses_http_login_before_creating_a_session(app, client, tmp_path):
    initialize(client, tmp_path / "data")
    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        setting = db.get(SystemSettingModel, "security.deployment_mode")
        setting.value_json = json.dumps("PUBLIC_HTTPS")
    assert client.get("/api/me").status_code == 401

    insecure_client = app.test_client()
    response = insecure_client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": preauth_csrf(insecure_client)},
        json={"username": "admin", "password": "Correct horse battery 7!"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "HTTPS_REQUIRED"
    assert insecure_client.get_cookie("fcc_session") is None

    secure_client = app.test_client()
    token = secure_client.get("/api/auth/csrf", base_url="https://localhost").get_json()["csrfToken"]
    secure_response = secure_client.post(
        "/api/auth/login",
        base_url="https://localhost",
        headers={"X-CSRF-Token": token, "Origin": "https://localhost"},
        json={"username": "admin", "password": "Correct horse battery 7!"},
    )
    assert secure_response.status_code == 200
    assert secure_response.headers["Strict-Transport-Security"] == "max-age=31536000"
    secure_cookie = secure_client.get_cookie("__Host-fcc_session", domain="localhost")
    assert secure_cookie is not None
    assert secure_cookie.secure is True
    assert secure_cookie.http_only is True
