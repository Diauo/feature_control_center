from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.instance_manager import InstanceStateError
from app.web.app_factory import create_app
from conftest import MutableClock, bootstrap_code, initialize, preauth_csrf


def test_first_run_initializes_once_and_persists_server_session(app, client, tmp_path: Path, clock: MutableClock):
    data_dir = tmp_path / "data"
    assert (data_dir / "fcc.db").is_file()
    assert (data_dir / "instance.key").is_file()
    assert (data_dir / "first-run.txt").is_file()

    invalid = client.post(
        "/api/setup/initialize",
        headers={"X-CSRF-Token": preauth_csrf(client)},
        json={
            "bootstrapCode": "wrong-code",
            "systemName": "测试功能中心",
            "adminUsername": "admin",
            "adminDisplayName": "测试管理员",
            "password": "Correct horse battery 7!",
            "customerName": "客户甲",
        },
    )
    assert invalid.status_code == 401
    assert invalid.get_json()["error"]["code"] == "INVALID_BOOTSTRAP_CODE"

    payload = initialize(client, data_dir)
    assert payload["user"]["role"] == "admin"
    assert not (data_dir / "first-run.txt").exists()
    cookie = client.get_cookie("fcc_session")
    assert cookie is not None
    assert cookie.http_only is True
    assert cookie.max_age == 86_400

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.get_json()["customers"][0]["name"] == "客户甲"

    with sqlite3.connect(data_dir / "fcc.db") as connection:
        digest, = connection.execute("SELECT token_digest FROM session WHERE revoked_at IS NULL").fetchone()
        denied_count, = connection.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='setup.initialize' AND outcome='denied'"
        ).fetchone()
        mode, = connection.execute("PRAGMA journal_mode").fetchone()
    assert isinstance(digest, bytes) and len(digest) == 32
    assert cookie.value.encode("utf-8") != digest
    assert denied_count == 1
    assert mode.lower() == "wal"

    app.extensions["fcc_services"].database.dispose()
    restarted = create_app(data_dir=data_dir, testing=True, clock=clock)
    try:
        restarted_client = restarted.test_client()
        restarted_client.set_cookie("fcc_session", cookie.value)
        restored = restarted_client.get("/api/me")
        assert restored.status_code == 200
        assert restored.get_json()["user"]["username"] == "admin"
    finally:
        restarted.extensions["fcc_services"].database.dispose()


def test_mutating_requests_require_csrf(client, tmp_path: Path):
    initialize(client, tmp_path / "data")
    response = client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "CSRF_INVALID"


def test_idle_expiry_and_logout_revoke_server_state(client, tmp_path: Path, clock: MutableClock):
    payload = initialize(client, tmp_path / "data")
    clock.advance(28_800)
    assert client.get("/api/me").status_code == 401

    logged_in = client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": preauth_csrf(client)},
        json={"username": "admin", "password": "Correct horse battery 7!"},
    )
    assert logged_in.status_code == 200
    logged_out = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": logged_in.get_json()["csrfToken"]},
    )
    assert logged_out.status_code == 200
    assert logged_out.headers["Clear-Site-Data"] == '"cache", "storage"'
    assert client.get("/api/me").status_code == 401


def test_existing_database_without_instance_key_fails_closed(app, tmp_path: Path, clock: MutableClock):
    data_dir = tmp_path / "data"
    app.extensions["fcc_services"].database.dispose()
    (data_dir / "instance.key").unlink()
    with pytest.raises(InstanceStateError, match="instance.key"):
        create_app(data_dir=data_dir, testing=True, clock=clock)


def test_security_headers_health_and_spa_fallback(client):
    live = client.get("/api/health/live")
    assert live.status_code == 200
    assert live.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in live.headers["Content-Security-Policy"]
    assert live.headers["Cache-Control"] == "no-store"

    ready = client.get("/api/health/ready")
    assert ready.status_code == 200
    assert ready.get_json()["database"] is True
    frontend = client.get("/some/client/route")
    assert frontend.status_code == 200
    assert b'<div id="app"></div>' in frontend.data


def test_bootstrap_code_is_one_time(client, tmp_path: Path):
    data_dir = tmp_path / "data"
    code = bootstrap_code(data_dir)
    initialize(client, data_dir)
    other = client.application.test_client()
    response = other.post(
        "/api/setup/initialize",
        headers={"X-CSRF-Token": preauth_csrf(other)},
        json={
            "bootstrapCode": code,
            "systemName": "另一个系统",
            "adminUsername": "other-admin",
            "adminDisplayName": "其他管理员",
            "password": "Another secure password 8!",
            "customerName": "客户乙",
        },
    )
    assert response.status_code in {401, 409}
