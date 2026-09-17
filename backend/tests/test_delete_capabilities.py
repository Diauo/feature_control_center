from __future__ import annotations

from pathlib import Path

from conftest import initialize, login
from test_menu_permissions import NEW_PASSWORD, _create_user, _operator_client
from test_phase_b_features import PASSWORD, feature_zip, upload
from test_phase_d import create_ready_feature


def _fake_finished_run(app, customer, feature, *, request_id="a" * 32, status="SUCCEEDED", data_source_revision_id=None):
    from app.infrastructure.models import RunModel

    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        db.add(RunModel(
            request_id=request_id,
            customer_id=customer["id"],
            customer_feature_id=feature["id"],
            feature_version_id=feature["versionId"],
            data_source_revision_id=data_source_revision_id,
            feature_name=feature["name"],
            version_number=feature["versionNumber"],
            data_source_filename=None,
            config_snapshot_ciphertext=b"",
            secret_keys_json="[]",
            trigger_source="MANUAL",
            trigger_key=None,
            status=status,
            queued_at=1_800_000_000,
            last_event_sequence=0,
        ))
    return request_id


def test_feature_soft_delete_keeps_history_and_restore_reuses_registration(client, app, tmp_path: Path):
    csrf, customer, feature = create_ready_feature(client, tmp_path, "删除保留测试")
    revision_id = feature["dataSource"]["id"]
    run_id = _fake_finished_run(app, customer, feature, data_source_revision_id=revision_id)

    deleted = client.delete(f"/api/admin/customer-features/{feature['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 200, deleted.get_json()
    body = deleted.get_json()
    assert body["deleted"] is True
    assert body["configCount"] >= 1
    assert body["revisionBlanked"] == 1 and body["revisionPurged"] == 0

    # 功能列表不可见，运行历史仍可查
    assert client.get(f"/api/customers/{customer['id']}/features").get_json()["items"] == []
    runs = client.get(f"/api/runs?scope=customer&customerId={customer['id']}").get_json()["items"]
    assert [item["requestId"] for item in runs] == [run_id]
    assert client.get(f"/api/runs/{run_id}").status_code == 200

    # 配置与数据源入口关闭；重复删除被拒
    assert client.get(f"/api/customer-features/{feature['id']}/config").status_code == 409
    assert client.get(f"/api/customer-features/{feature['id']}/data-source").status_code == 409
    again = client.delete(f"/api/admin/customer-features/{feature['id']}", headers={"X-CSRF-Token": csrf})
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "FEATURE_DELETED"

    # 再次上传同一包 → 恢复原登记（同一 id），历史运行继续关联，新数据源修订号延续
    restored = upload(client, csrf, customer["id"], feature_zip("删除保留测试"), "restore.zip")
    assert restored.status_code == 201, restored.get_json()
    assert restored.get_json()["restored"] is True

    items = client.get(f"/api/customers/{customer['id']}/features").get_json()["items"]
    assert len(items) == 1 and items[0]["id"] == feature["id"]
    assert items[0]["dataSource"]["revisionNumber"] == 2
    runs_after = client.get(f"/api/runs?scope=customer&customerId={customer['id']}").get_json()["items"]
    assert [item["requestId"] for item in runs_after] == [run_id]


def test_feature_delete_blocked_by_active_run_and_run_creation(client, app, tmp_path: Path):
    csrf, customer, feature = create_ready_feature(client, tmp_path, "活跃任务保护")

    _fake_finished_run(app, customer, feature, request_id="b" * 32, status="QUEUED")
    blocked = client.delete(f"/api/admin/customer-features/{feature['id']}", headers={"X-CSRF-Token": csrf})
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "FEATURE_RUN_ACTIVE"

    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        from app.infrastructure.models import RunModel
        run = db.get(RunModel, "b" * 32)
        run.status = "SUCCEEDED"

    deleted = client.delete(f"/api/admin/customer-features/{feature['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 200

    run_attempt = client.post(f"/api/customer-features/{feature['id']}/runs", headers={"X-CSRF-Token": csrf})
    assert run_attempt.status_code == 409
    assert run_attempt.get_json()["error"]["code"] == "FEATURE_DELETED"


def test_feature_delete_requires_menu_and_customer_scope(client, app, tmp_path: Path):
    csrf, customer, feature = create_ready_feature(client, tmp_path, "越权保护")

    plain = _create_user(client, csrf, username="del-plain")
    plain_client, _ = _operator_client(app, plain)
    denied = plain_client.delete(
        f"/api/admin/customer-features/{feature['id']}",
        headers={"X-CSRF-Token": _csrf_for(plain_client)},
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "MENU_PERMISSION_REQUIRED"

    manager = _create_user(client, csrf, username="del-manager", menu_keys=["feature_admin"])
    manager_client, _ = _operator_client(app, manager)
    out_of_scope = manager_client.delete(
        f"/api/admin/customer-features/{feature['id']}",
        headers={"X-CSRF-Token": _csrf_for(manager_client)},
    )
    assert out_of_scope.status_code == 403
    assert out_of_scope.get_json()["error"]["code"] == "CUSTOMER_ACCESS_DENIED"


def _csrf_for(client) -> str:
    return client.get("/api/auth/csrf").get_json()["csrfToken"]


def test_user_delete_removes_operator_and_preserves_audit(client, app, tmp_path: Path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    created = _create_user(client, csrf, username="fire-me")
    user_id = created["user"]["id"]
    operator_client, _ = _operator_client(app, created)
    assert operator_client.get("/api/me").status_code == 200

    deleted = client.delete(f"/api/admin/users/{user_id}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 200, deleted.get_json()
    assert deleted.get_json()["deleted"] is True

    users = client.get("/api/admin/users?role=operator&page=1&pageSize=50").get_json()["items"]
    assert all(item["id"] != user_id for item in users)
    assert operator_client.get("/api/me").status_code == 401

    again = login(app.test_client(), "fire-me", NEW_PASSWORD)
    assert again.status_code == 401
    assert again.get_json()["error"]["code"] == "INVALID_CREDENTIALS"

    audit = client.get("/api/admin/audit-logs?action=admin.user.delete").get_json()["items"]
    assert audit[0]["targetId"] == user_id
    assert audit[0]["details"]["username"] == "fire-me"
    assert audit[0]["details"]["role"] == "operator"


def test_admin_and_self_cannot_be_deleted(client, tmp_path: Path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]

    me = client.get("/api/me").get_json()["user"]
    self_attempt = client.delete(f"/api/admin/users/{me['id']}", headers={"X-CSRF-Token": csrf})
    assert self_attempt.status_code == 409
    assert self_attempt.get_json()["error"]["code"] == "CANNOT_DELETE_SELF"

    second_admin = _create_user(client, csrf, username="admin-two", role="admin")
    admin_attempt = client.delete(
        f"/api/admin/users/{second_admin['user']['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert admin_attempt.status_code == 409
    assert admin_attempt.get_json()["error"]["code"] == "CANNOT_DELETE_ADMIN"


def test_user_delete_requires_recent_authentication(client, tmp_path: Path, clock):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    created = _create_user(client, csrf, username="stale-session")

    clock.advance(7200)
    stale = client.delete(f"/api/admin/users/{created['user']['id']}", headers={"X-CSRF-Token": csrf})
    assert stale.status_code == 428
    assert stale.get_json()["error"]["code"] == "REAUTHENTICATION_REQUIRED"

    reauth = client.post("/api/auth/reauthenticate", headers={"X-CSRF-Token": csrf}, json={"password": PASSWORD})
    assert reauth.status_code == 200, reauth.get_json()
    retried = client.delete(f"/api/admin/users/{created['user']['id']}", headers={"X-CSRF-Token": csrf})
    assert retried.status_code == 200
