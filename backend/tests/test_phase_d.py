from __future__ import annotations

import io

from sqlalchemy import func, select

from app.infrastructure.models import (
    CustomerFeatureDataSourceRevisionModel,
    FeatureConfigValueModel,
    RunModel,
    ScheduledTaskModel,
)
from app.scheduler.worker import SchedulerWorker
from conftest import initialize
from test_phase_b_features import PASSWORD, feature_zip, upload


def create_ready_feature(client, tmp_path, name: str = "阶段 D 功能"):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    customer = client.get("/api/customers").get_json()["items"][0]
    response = upload(client, csrf, customer["id"], feature_zip(name), "phase-d.zip")
    assert response.status_code == 201, response.get_json()
    feature = client.get(f"/api/customers/{customer['id']}/features").get_json()["items"][0]
    configured = client.put(
        f"/api/customer-features/{feature['id']}/config",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"api_token": "source-secret", "batch_size": 240}, "clearSecrets": []},
    )
    assert configured.status_code == 200, configured.get_json()
    return csrf, customer, feature


def test_feature_copy_shares_code_but_not_customer_inputs(client, app, tmp_path):
    csrf, source_customer, source_feature = create_ready_feature(client, tmp_path, "复制隔离测试")
    target_ids: list[str] = []
    for name in ("客户乙", "客户丙"):
        response = client.post(
            "/api/admin/customers",
            headers={"X-CSRF-Token": csrf},
            json={"name": name, "description": "复制目标"},
        )
        assert response.status_code == 201
        target_ids.append(response.get_json()["customer"]["id"])

    replacement = client.put(
        f"/api/customer-features/{source_feature['id']}/data-source",
        headers={"X-CSRF-Token": csrf},
        data={"file": (io.BytesIO(b"source-customer-current"), "private.xlsx")},
        content_type="multipart/form-data",
    )
    assert replacement.status_code == 200

    copied = client.post(
        f"/api/admin/customer-features/{source_feature['id']}/copy",
        headers={"X-CSRF-Token": csrf},
        json={"targetCustomerIds": target_ids},
    )
    assert copied.status_code == 200, copied.get_json()
    assert [item["status"] for item in copied.get_json()["items"]] == ["COPIED", "COPIED"]

    target_features = []
    for customer_id in target_ids:
        items = client.get(f"/api/customers/{customer_id}/features").get_json()["items"]
        assert len(items) == 1
        target = items[0]
        target_features.append(target)
        assert target["versionId"] == source_feature["versionId"]
        assert target["maxRuntimeSeconds"] is None
        assert target["dataSource"]["sourceKind"] == "DEFAULT"
        assert client.get(f"/api/customer-features/{target['id']}/data-source/download").data == b"default-data"
        config = client.get(f"/api/customer-features/{target['id']}/config").get_json()
        assert next(item for item in config["fields"] if item["key"] == "batch_size")["value"] == 100
        secret = next(item for item in config["fields"] if item["key"] == "api_token")
        assert secret["isSet"] is False

    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        revision_ids = [
            db.scalar(
                select(CustomerFeatureDataSourceRevisionModel.id).where(
                    CustomerFeatureDataSourceRevisionModel.customer_feature_id == target["id"]
                )
            )
            for target in target_features
        ]
        assert len(set(revision_ids)) == 2
        assert db.get(FeatureConfigValueModel, (target_features[0]["id"], "api_token")) is None

    duplicate = client.post(
        f"/api/admin/customer-features/{source_feature['id']}/copy",
        headers={"X-CSRF-Token": csrf},
        json={"targetCustomerIds": [target_ids[0]]},
    )
    assert duplicate.get_json()["items"][0]["status"] == "SKIPPED_EXISTS"
    assert source_customer["id"] not in target_ids


def test_all_customer_scope_keeps_customer_identity_and_paginates(client, app, tmp_path):
    csrf, source_customer, source_feature = create_ready_feature(client, tmp_path, "聚合范围测试")
    target = client.post(
        "/api/admin/customers",
        headers={"X-CSRF-Token": csrf},
        json={"name": "聚合客户乙", "description": "用于验证全部客户"},
    ).get_json()["customer"]
    copied = client.post(
        f"/api/admin/customer-features/{source_feature['id']}/copy",
        headers={"X-CSRF-Token": csrf},
        json={"targetCustomerIds": [target["id"]]},
    )
    assert copied.status_code == 200

    first_page = client.get("/api/customer-features?scope=all&page=1&pageSize=1")
    second_page = client.get("/api/customer-features?scope=all&page=2&pageSize=1")
    assert first_page.status_code == 200
    assert first_page.get_json()["pagination"] == {
        "page": 1, "pageSize": 1, "total": 2, "totalPages": 2,
    }
    rows = first_page.get_json()["items"] + second_page.get_json()["items"]
    assert {row["customerId"] for row in rows} == {source_customer["id"], target["id"]}
    assert {row["customerName"] for row in rows} == {source_customer["name"], target["name"]}

    target_feature_id = copied.get_json()["items"][0]["customerFeatureId"]
    configured = client.put(
        f"/api/customer-features/{target_feature_id}/config",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"api_token": "target-secret", "batch_size": 100}, "clearSecrets": []},
    )
    assert configured.status_code == 200, configured.get_json()
    for feature_id in (source_feature["id"], target_feature_id):
        response = client.post(
            f"/api/customer-features/{feature_id}/runs",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 202, response.get_json()
    schedule_features = (
        (source_customer["id"], source_feature["id"], "客户甲计划"),
        (target["id"], target_feature_id, "客户乙计划"),
    )
    for customer_id, feature_id, name in schedule_features:
        response = client.post(
            "/api/schedules",
            headers={"X-CSRF-Token": csrf},
            json={
                "customerId": customer_id,
                "customerFeatureId": feature_id,
                "name": name,
                "cronExpression": "0 9 * * *",
                "isEnabled": True,
            },
        )
        assert response.status_code == 201, response.get_json()

    run_pages = [
        client.get("/api/runs?scope=all&page=1&pageSize=1").get_json(),
        client.get("/api/runs?scope=all&page=2&pageSize=1").get_json(),
    ]
    schedule_pages = [
        client.get("/api/schedules?scope=all&page=1&pageSize=1").get_json(),
        client.get("/api/schedules?scope=all&page=2&pageSize=1").get_json(),
    ]
    assert run_pages[0]["pagination"]["total"] == 2
    assert schedule_pages[0]["pagination"]["total"] == 2
    assert {page["items"][0]["customerName"] for page in run_pages} == {
        source_customer["name"], target["name"],
    }
    assert {page["items"][0]["customerName"] for page in schedule_pages} == {
        source_customer["name"], target["name"],
    }


def test_scheduler_enqueues_once_records_missed_and_log_filters(client, app, tmp_path, clock):
    csrf, customer, feature = create_ready_feature(client, tmp_path, "定时运行测试")
    created = client.post(
        "/api/schedules",
        headers={"X-CSRF-Token": csrf},
        json={
            "customerId": customer["id"],
            "customerFeatureId": feature["id"],
            "name": "每天同步",
            "cronExpression": "0 9 * * *",
            "isEnabled": True,
        },
    )
    assert created.status_code == 201, created.get_json()
    task = created.get_json()["schedule"]
    assert task["timezone"] == "Asia/Hong_Kong"
    assert task["nextRunAt"] > clock.now()

    services = app.extensions["fcc_services"]
    due_at = clock.now()
    with services.database.session() as db:
        row = db.get(ScheduledTaskModel, task["id"])
        row.next_run_at = due_at

    worker = SchedulerWorker(
        database=services.database,
        settings=services.settings,
        schedules=services.schedules,
        clock=services.clock,
        scheduler_id="phase-d-test",
    )
    assert worker.tick() == 1
    with services.database.session() as db:
        run = db.scalar(select(RunModel).where(RunModel.trigger_source == "SCHEDULED"))
        assert run is not None
        request_id = run.request_id
        assert run.trigger_key == f"schedule:{task['id']}:{due_at}"
        row = db.get(ScheduledTaskModel, task["id"])
        assert row.last_outcome == "ENQUEUED"
        row.next_run_at = due_at

    assert worker.tick() == 1
    with services.database.session() as db:
        assert db.scalar(select(func.count(RunModel.request_id))) == 1
        row = db.get(ScheduledTaskModel, task["id"])
        assert row.last_outcome == "DUPLICATE"
        run = db.get(RunModel, request_id)
        run.status = "SUCCEEDED"
        run.finished_at = clock.now()
        run.final_event_sequence = run.last_event_sequence

    missed_response = client.post(
        "/api/schedules",
        headers={"X-CSRF-Token": csrf},
        json={
            "customerId": customer["id"],
            "customerFeatureId": feature["id"],
            "name": "错过时点",
            "cronExpression": "30 10 * * *",
            "isEnabled": True,
        },
    )
    missed_id = missed_response.get_json()["schedule"]["id"]
    with services.database.session() as db:
        db.get(ScheduledTaskModel, missed_id).next_run_at = clock.now() - 61
    assert worker.tick() == 1
    with services.database.session() as db:
        missed = db.get(ScheduledTaskModel, missed_id)
        assert missed.last_outcome == "MISSED"
        assert missed.missed_count == 1
        assert db.scalar(select(func.count(RunModel.request_id))) == 1

    filtered = client.get(
        f"/api/runs?customerId={customer['id']}&triggerSource=SCHEDULED"
        f"&customerFeatureId={feature['id']}&status=SUCCEEDED&requestId={request_id[:10]}"
        f"&queuedFrom={clock.now() - 1}&queuedTo={clock.now() + 1}"
    )
    assert filtered.status_code == 200, filtered.get_json()
    assert [item["requestId"] for item in filtered.get_json()["items"]] == [request_id]
    worker.shutdown()


def test_schedule_crud_is_available_to_linked_operator(client, app, tmp_path):
    csrf, customer, feature = create_ready_feature(client, tmp_path, "操作员调度测试")
    created_user = client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "scheduler-operator",
            "displayName": "调度操作员",
            "role": "operator",
            "customerIds": [customer["id"]],
        },
    ).get_json()
    operator = app.test_client()
    from conftest import login

    logged_in = login(operator, "scheduler-operator", created_user["temporaryPassword"]).get_json()
    changed = operator.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": logged_in["csrfToken"]},
        json={
            "currentPassword": created_user["temporaryPassword"],
            "newPassword": "Operator schedule password 9!",
        },
    ).get_json()
    operator_csrf = changed["csrfToken"]
    created = operator.post(
        "/api/schedules",
        headers={"X-CSRF-Token": operator_csrf},
        json={
            "customerId": customer["id"],
            "customerFeatureId": feature["id"],
            "name": "工作日同步",
            "cronExpression": "15 8 * * 1-5",
            "isEnabled": True,
        },
    )
    assert created.status_code == 201, created.get_json()
    task = created.get_json()["schedule"]
    updated = operator.put(
        f"/api/schedules/{task['id']}",
        headers={"X-CSRF-Token": operator_csrf},
        json={"name": "暂停的工作日同步", "cronExpression": "15 8 * * 1-5", "isEnabled": False},
    )
    assert updated.status_code == 200
    assert updated.get_json()["schedule"]["nextRunAt"] is None
    assert operator.get(f"/api/schedules?customerId={customer['id']}").status_code == 200
    assert operator.delete(f"/api/schedules/{task['id']}", headers={"X-CSRF-Token": operator_csrf}).status_code == 204


def test_scheduler_skips_overlapping_feature_and_reconciles_system_timezone(client, app, tmp_path, clock):
    csrf, customer, feature = create_ready_feature(client, tmp_path, "重叠调度测试")
    task_ids: list[str] = []
    for name in ("计划一", "计划二"):
        response = client.post(
            "/api/schedules",
            headers={"X-CSRF-Token": csrf},
            json={
                "customerId": customer["id"],
                "customerFeatureId": feature["id"],
                "name": name,
                "cronExpression": "0 * * * *",
                "isEnabled": True,
            },
        )
        task_ids.append(response.get_json()["schedule"]["id"])
    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        for task_id in task_ids:
            db.get(ScheduledTaskModel, task_id).next_run_at = clock.now()
    worker = SchedulerWorker(
        database=services.database,
        settings=services.settings,
        schedules=services.schedules,
        clock=services.clock,
        scheduler_id="overlap-test",
    )
    assert worker.tick() == 2
    with services.database.session() as db:
        outcomes = {db.get(ScheduledTaskModel, task_id).last_outcome for task_id in task_ids}
        assert outcomes == {"ENQUEUED", "SKIPPED_ACTIVE"}

    timezone_update = client.put(
        "/api/admin/settings",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"system.timezone": "UTC"}},
    )
    assert timezone_update.status_code == 200, timezone_update.get_json()
    assert services.schedules.reconcile_timezone() == 2
    with services.database.session() as db:
        rows = [db.get(ScheduledTaskModel, task_id) for task_id in task_ids]
        assert {row.timezone for row in rows} == {"UTC"}
        assert all(row.next_run_at > clock.now() for row in rows)
    worker.shutdown()
