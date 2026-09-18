"""工作台急停（停止功能的所有活动实例）端点的集成测试。"""

from __future__ import annotations

import time

from sqlalchemy import select

from app.infrastructure.models import RunEventModel, RunModel
from test_menu_permissions import _create_user, _operator_client
from test_phase_b_features import upload
from test_phase_c_runner import executable_zip, make_worker, setup_feature, wait_terminal


def test_emergency_stop_stops_running_run_and_exposes_active_run(client, app, tmp_path):
    source = """
import time
def run(ctx):
    ctx.log.info('loop started')
    while True:
        ctx.raise_if_cancelled()
        time.sleep(0.02)
"""
    csrf, customer_id, feature = setup_feature(client, tmp_path, executable_zip("急停运行", source))
    created = client.post(f"/api/customer-features/{feature['id']}/runs", headers={"X-CSRF-Token": csrf})
    assert created.status_code == 202
    request_id = created.get_json()["run"]["requestId"]
    services = app.extensions["fcc_services"]
    worker = make_worker(app, "emergency-stop-running")
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            worker.tick()
            with services.database.session() as db:
                run = db.get(RunModel, request_id)
                if run is not None and run.status == "RUNNING":
                    break
            time.sleep(0.03)
        else:
            raise AssertionError("任务未进入运行状态")

        listing = client.get(
            f"/api/customer-features?scope=customer&customerId={customer_id}&page=1&pageSize=20"
        )
        assert listing.status_code == 200
        item = next(entry for entry in listing.get_json()["items"] if entry["id"] == feature["id"])
        assert item["activeRun"] is not None
        assert item["activeRun"]["requestId"] == request_id
        assert item["activeRun"]["status"] in {"STARTING", "RUNNING"}

        stopped = client.post(
            f"/api/customer-features/{feature['id']}/runs/stop", headers={"X-CSRF-Token": csrf}
        )
        assert stopped.status_code == 200
        payload = stopped.get_json()
        assert payload["count"] == 1
        assert payload["runs"][0]["requestId"] == request_id
        assert payload["runs"][0]["status"] == "STOPPING"

        run = wait_terminal(worker, services, request_id)
        assert run.status == "STOPPED"
        assert run.stop_reason == "USER_REQUEST"

        listing = client.get(
            f"/api/customer-features?scope=customer&customerId={customer_id}&page=1&pageSize=20"
        )
        item = next(entry for entry in listing.get_json()["items"] if entry["id"] == feature["id"])
        assert item["activeRun"] is None
    finally:
        worker.shutdown()


def test_emergency_stop_cancels_queued_run_before_start(client, app, tmp_path):
    csrf, customer_id, feature = setup_feature(
        client, tmp_path, executable_zip("急停排队", "def run(ctx):\n    ctx.log.info('noop')\n")
    )
    created = client.post(f"/api/customer-features/{feature['id']}/runs", headers={"X-CSRF-Token": csrf})
    request_id = created.get_json()["run"]["requestId"]
    stopped = client.post(
        f"/api/customer-features/{feature['id']}/runs/stop", headers={"X-CSRF-Token": csrf}
    )
    assert stopped.status_code == 200
    payload = stopped.get_json()
    assert payload["count"] == 1
    assert payload["runs"] == [{"requestId": request_id, "status": "STOPPING"}]

    services = app.extensions["fcc_services"]
    worker = make_worker(app, "emergency-stop-queued")
    finalized = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            worker.tick()
            with services.database.session() as db:
                run = db.get(RunModel, request_id)
                if run is not None and run.status == "STOPPED":
                    finalized = run
                    break
            time.sleep(0.03)
        assert finalized is not None, "排队任务未在启动前被终止"
        assert finalized.stop_reason == "USER_REQUEST"
        assert finalized.finished_at is not None
        with services.database.session() as db:
            messages = [
                event.message
                for event in db.scalars(
                    select(RunEventModel).where(RunEventModel.run_request_id == request_id)
                )
            ]
        assert any("启动前收到停止请求" in message for message in messages)
    finally:
        worker.shutdown()


def test_emergency_stop_only_touches_target_feature(client, app, tmp_path):
    csrf, customer_id, feature_a = setup_feature(
        client, tmp_path, executable_zip("急停范围甲", "def run(ctx):\n    ctx.log.info('a')\n")
    )
    uploaded = upload(
        client,
        csrf,
        customer_id,
        executable_zip("急停范围乙", "def run(ctx):\n    ctx.log.info('b')\n"),
        "second.zip",
    )
    assert uploaded.status_code == 201
    items = client.get(f"/api/customers/{customer_id}/features").get_json()["items"]
    feature_b = next(entry for entry in items if entry["name"] == "急停范围乙")
    configured = client.put(
        f"/api/customer-features/{feature_b['id']}/config",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"api_token": "snapshot-secret"}, "clearSecrets": []},
    )
    assert configured.status_code == 200

    empty = client.post(f"/api/customer-features/{feature_b['id']}/runs/stop", headers={"X-CSRF-Token": csrf})
    assert empty.status_code == 200
    assert empty.get_json()["count"] == 0
    assert empty.get_json()["runs"] == []

    run_a = client.post(f"/api/customer-features/{feature_a['id']}/runs", headers={"X-CSRF-Token": csrf})
    run_b = client.post(f"/api/customer-features/{feature_b['id']}/runs", headers={"X-CSRF-Token": csrf})
    request_a = run_a.get_json()["run"]["requestId"]
    request_b = run_b.get_json()["run"]["requestId"]

    stopped = client.post(f"/api/customer-features/{feature_a['id']}/runs/stop", headers={"X-CSRF-Token": csrf})
    assert stopped.status_code == 200
    payload = stopped.get_json()
    assert payload["count"] == 1
    assert payload["runs"][0]["requestId"] == request_a
    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        assert db.get(RunModel, request_a).status == "STOPPING"
        assert db.get(RunModel, request_b).status == "QUEUED"

    again = client.post(f"/api/customer-features/{feature_a['id']}/runs/stop", headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200
    payload = again.get_json()
    assert payload["count"] == 1
    assert payload["runs"][0]["requestId"] == request_a
    assert payload["runs"][0]["status"] == "STOPPING"


def test_emergency_stop_respects_customer_scope_and_menu(client, app, tmp_path):
    csrf, customer_id, feature = setup_feature(
        client, tmp_path, executable_zip("急停权限", "def run(ctx):\n    ctx.log.info('noop')\n")
    )
    outsider = _create_user(client, csrf, username="stop-outsider", menu_keys=["workspace"], customer_ids=())
    outsider_client, outsider_csrf = _operator_client(app, outsider)
    denied = outsider_client.post(
        f"/api/customer-features/{feature['id']}/runs/stop", headers={"X-CSRF-Token": outsider_csrf}
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "CUSTOMER_ACCESS_DENIED"

    insider = _create_user(
        client, csrf, username="stop-insider", menu_keys=["workspace"], customer_ids=(customer_id,)
    )
    insider_client, insider_csrf = _operator_client(app, insider)
    allowed = insider_client.post(
        f"/api/customer-features/{feature['id']}/runs/stop", headers={"X-CSRF-Token": insider_csrf}
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["count"] == 0

    without_csrf = insider_client.post(f"/api/customer-features/{feature['id']}/runs/stop")
    assert without_csrf.status_code >= 400
