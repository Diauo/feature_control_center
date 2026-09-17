from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask
from flask.testing import FlaskClient

from conftest import initialize, login


ADMIN_PASSWORD = "Correct horse battery 7!"
NEW_PASSWORD = "Menu permissions 9!"


def _create_user(
    admin_client: FlaskClient,
    csrf: str,
    *,
    username: str,
    role: str = "operator",
    menu_keys: Any = None,
    customer_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "username": username,
        "displayName": username,
        "role": role,
        "customerIds": list(customer_ids),
    }
    if menu_keys is not None:
        payload["menuKeys"] = menu_keys
    response = admin_client.post("/api/admin/users", headers={"X-CSRF-Token": csrf}, json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _operator_client(app: Flask, created: dict[str, Any]) -> tuple[FlaskClient, str]:
    client = app.test_client()
    first = login(client, created["user"]["username"], created["temporaryPassword"])
    assert first.status_code == 200, first.get_json()
    changed = client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": first.get_json()["csrfToken"]},
        json={"currentPassword": created["temporaryPassword"], "newPassword": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.get_json()
    return client, changed.get_json()["csrfToken"]


def test_default_operator_menus_are_workspace_and_runs(client, app, tmp_path: Path):
    payload = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = payload["csrfToken"]
    customer = client.get("/api/customers").get_json()["items"][0]

    created = _create_user(client, csrf, username="menu-default", customer_ids=(customer["id"],))
    assert created["user"]["menuKeys"] == ["workspace", "runs"]

    operator, _ = _operator_client(app, created)
    assert operator.get(f"/api/customer-features?scope=customer&customerId={customer['id']}").status_code == 200
    assert operator.get("/api/runs?scope=all").status_code == 200

    denied = operator.get("/api/schedules?scope=all")
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "MENU_PERMISSION_REQUIRED"
    assert operator.get("/api/admin/feature-definitions").status_code == 403
    assert operator.get("/api/admin/users").status_code == 403
    assert operator.get("/api/admin/audit-logs").status_code == 403

    me = operator.get("/api/me").get_json()
    assert me["user"]["menuKeys"] == ["workspace", "runs"]


def test_menu_grants_control_each_menu_area(client, app, tmp_path: Path):
    payload = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = payload["csrfToken"]
    customer = client.get("/api/customers").get_json()["items"][0]

    workspace_only = _create_user(
        client, csrf, username="menu-ws", menu_keys=["workspace"], customer_ids=(customer["id"],)
    )
    operator, _ = _operator_client(app, workspace_only)
    assert operator.get(f"/api/customer-features?scope=customer&customerId={customer['id']}").status_code == 200
    assert operator.get("/api/runs?scope=all").status_code == 403

    all_business = _create_user(
        client,
        csrf,
        username="menu-business",
        menu_keys=["workspace", "runs", "schedules"],
        customer_ids=(customer["id"],),
    )
    operator2, _ = _operator_client(app, all_business)
    assert operator2.get("/api/schedules?scope=all").status_code == 200
    assert operator2.get("/api/runs?scope=all").status_code == 200

    manager = _create_user(
        client,
        csrf,
        username="menu-manager",
        menu_keys=["feature_admin", "users", "customers", "audit"],
    )
    operator3, _ = _operator_client(app, manager)
    assert operator3.get("/api/admin/feature-definitions").status_code == 200
    assert operator3.get("/api/admin/users").status_code == 200
    assert operator3.get("/api/admin/customers").status_code == 200
    assert operator3.get("/api/admin/audit-logs").status_code == 200
    assert operator3.get("/api/customer-features?scope=all").status_code == 200
    assert operator3.get("/api/runs?scope=all").status_code == 403
    assert operator3.get("/api/schedules?scope=all").status_code == 403


def test_menu_grant_validation(client, tmp_path: Path):
    payload = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = payload["csrfToken"]

    cases = (["settings"], [], ["workspace", "unknown"], "workspace")
    for index, bad in enumerate(cases):
        response = client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": f"menu-bad-{index}",
                "displayName": "坏授权",
                "role": "operator",
                "menuKeys": bad,
            },
        )
        assert response.status_code == 400, (bad, response.get_json())
        assert response.get_json()["error"]["code"] == "INVALID_MENU_KEYS"

    admin_created = _create_user(client, csrf, username="menu-admin", role="admin", menu_keys=["workspace"])
    assert admin_created["user"]["menuKeys"] == [
        "workspace",
        "runs",
        "schedules",
        "feature_admin",
        "users",
        "customers",
        "audit",
        "settings",
    ]


def test_menu_change_takes_effect_without_relogin(client, app, tmp_path: Path):
    payload = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = payload["csrfToken"]
    created = _create_user(client, csrf, username="menu-live")
    operator, _ = _operator_client(app, created)
    assert operator.get("/api/runs?scope=all").status_code == 200

    updated = client.patch(
        f"/api/admin/users/{created['user']['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"menuKeys": ["workspace"]},
    )
    assert updated.status_code == 200
    assert updated.get_json()["user"]["menuKeys"] == ["workspace"]

    assert operator.get("/api/runs?scope=all").status_code == 403
    assert operator.get("/api/me").get_json()["user"]["menuKeys"] == ["workspace"]

    restored = client.patch(
        f"/api/admin/users/{created['user']['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"menuKeys": ["workspace", "runs"]},
    )
    assert restored.status_code == 200
    assert operator.get("/api/runs?scope=all").status_code == 200


def test_settings_menu_remains_admin_only(client, app, tmp_path: Path):
    payload = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = payload["csrfToken"]

    me = client.get("/api/me").get_json()
    assert me["user"]["menuKeys"] == [
        "workspace",
        "runs",
        "schedules",
        "feature_admin",
        "users",
        "customers",
        "audit",
        "settings",
    ]

    granted_everything = _create_user(
        client,
        csrf,
        username="menu-seven",
        menu_keys=["workspace", "runs", "schedules", "feature_admin", "users", "customers", "audit"],
    )
    operator, _ = _operator_client(app, granted_everything)
    denied = operator.get("/api/admin/settings")
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "ADMIN_REQUIRED"
    assert operator.get("/api/admin/users").status_code == 200
