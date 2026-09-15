from __future__ import annotations

from pathlib import Path

from conftest import initialize, login


ADMIN_PASSWORD = "Correct horse battery 7!"


def test_user_customer_lifecycle_and_forced_password_change(client, tmp_path: Path):
    admin = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = admin["csrfToken"]

    customer_response = client.post(
        "/api/admin/customers",
        headers={"X-CSRF-Token": csrf},
        json={"name": "客户乙", "description": "第二个客户"},
    )
    assert customer_response.status_code == 201
    customer_b = customer_response.get_json()["customer"]
    customer_a = client.get("/api/customers").get_json()["items"][0]

    created = client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "operator-one",
            "displayName": "业务员一",
            "role": "operator",
            "customerIds": [customer_a["id"], customer_b["id"]],
        },
    )
    assert created.status_code == 201, created.get_json()
    created_body = created.get_json()
    operator = created_body["user"]
    assert set(operator["customerIds"]) == {customer_a["id"], customer_b["id"]}

    operator_client = client.application.test_client()
    operator_login = login(operator_client, "operator-one", created_body["temporaryPassword"])
    assert operator_login.status_code == 200
    operator_payload = operator_login.get_json()
    assert operator_payload["user"]["mustChangePassword"] is True
    blocked = operator_client.get("/api/customers")
    assert blocked.status_code == 403
    assert blocked.get_json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    password_change = operator_client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": operator_payload["csrfToken"]},
        json={
            "currentPassword": created_body["temporaryPassword"],
            "newPassword": "Operator private password 9!",
        },
    )
    assert password_change.status_code == 200
    assigned = operator_client.get("/api/customers")
    assert {item["id"] for item in assigned.get_json()["items"]} == {customer_a["id"], customer_b["id"]}
    assert operator_client.get("/api/admin/users").status_code == 403

    updated = client.patch(
        f"/api/admin/users/{operator['id']}",
        headers={"X-CSRF-Token": csrf},
        json={
            "displayName": "业务员一（调整）",
            "role": "operator",
            "isActive": True,
            "customerIds": [customer_b["id"]],
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["user"]["customerIds"] == [customer_b["id"]]
    refreshed_context = operator_client.get("/api/me")
    assert refreshed_context.status_code == 200
    assert [item["id"] for item in refreshed_context.get_json()["customers"]] == [customer_b["id"]]
    assert [item["id"] for item in operator_client.get("/api/customers").get_json()["items"]] == [
        customer_b["id"]
    ]


def test_admin_safety_rules_and_input_validation(client, tmp_path: Path):
    payload = initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    csrf = payload["csrfToken"]
    current_user = client.get("/api/me").get_json()["user"]

    disable_self = client.patch(
        f"/api/admin/users/{current_user['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"isActive": False},
    )
    assert disable_self.status_code == 409
    assert disable_self.get_json()["error"]["code"] == "CANNOT_DISABLE_SELF"

    reset_self = client.post(
        f"/api/admin/users/{current_user['id']}/reset-password",
        headers={"X-CSRF-Token": csrf},
    )
    assert reset_self.status_code == 409
    assert reset_self.get_json()["error"]["code"] == "USE_CHANGE_PASSWORD"

    invalid_customers = client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={"username": "test-user", "displayName": "测试", "role": "operator", "customerIds": "bad"},
    )
    assert invalid_customers.status_code == 400
    assert invalid_customers.get_json()["error"]["code"] == "INVALID_CUSTOMER_IDS"


def test_login_is_rate_limited_without_revealing_account_state(client, tmp_path: Path):
    initialize(client, tmp_path / "data", password=ADMIN_PASSWORD)
    attacker = client.application.test_client()
    for _ in range(5):
        response = login(attacker, "admin", "definitely-wrong")
        assert response.status_code == 401
        assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"
    blocked = login(attacker, "admin", "definitely-wrong")
    assert blocked.status_code == 429
    assert blocked.get_json()["error"]["code"] == "LOGIN_RATE_LIMITED"
    assert blocked.get_json()["error"]["details"]["retryAfterSeconds"] >= 1
    assert int(blocked.headers["Retry-After"]) >= 1
