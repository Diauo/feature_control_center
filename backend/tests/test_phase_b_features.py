from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.domain.identity import ValidationError
from app.infrastructure.models import (
    CustomerFeatureDataSourceRevisionModel,
    FeatureConfigValueModel,
    RuntimeEnvironmentModel,
)
from app.infrastructure.package_inspector import FeaturePackageInspector, PackageLimits
from app.runner.dependencies import DependencyPreparer
from app.runner.materializer import RunMaterializer, ScriptIdentity
from app.runner.worker import RunnerWorker
from app.security.config_cipher import ConfigCipherError
from conftest import initialize, login


PASSWORD = "Correct horse battery 7!"
LIMITS = PackageLimits(2_000_000, 100, 1_000_000, 2_000_000, 100)


def feature_zip(
    name: str,
    *,
    default_source: bytes | None = b"default-data",
    requirements: str = "",
    description: str = "测试同步功能",
    report: dict[str, object] | None = None,
) -> bytes:
    metadata = {
        "name": name,
        "description": description,
        "entrypoint": "run",
        "configs": {
            "batch_size": {"type": "integer", "label": "批量大小", "required": True, "min": 1, "max": 1000, "default": 100},
            "api_token": {"type": "secret", "label": "接口密钥", "required": True},
        },
        "data_source": {"filename": "dataSource.xlsx", "required": True, "extensions": [".xlsx"]},
    }
    if report is not None:
        metadata["report"] = report
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("__init__.py", f"__meta__ = {metadata!r}\nraise RuntimeError('must never import')\ndef run(context):\n    return None\n")
        if default_source is not None:
            archive.writestr("dataSource.xlsx", default_source)
        if requirements:
            archive.writestr("requirements.txt", requirements)
    return buffer.getvalue()


def upload(client, csrf: str, customer_id: str, package: bytes, filename: str = "feature.zip"):
    return client.post(
        "/api/admin/features/versions",
        headers={"X-CSRF-Token": csrf},
        data={"customerId": customer_id, "package": (io.BytesIO(package), filename)},
        content_type="multipart/form-data",
    )


def test_package_inspection_is_static_and_blocks_unsafe_archives():
    package = FeaturePackageInspector().inspect("safe.zip", feature_zip("安全功能"), LIMITS)
    assert package.metadata.name == "安全功能"
    assert package.metadata.entrypoint == "run"
    assert package.default_data_source.content == b"default-data"

    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../escape.py", "pass")
        archive.writestr("__init__.py", "__meta__={'name':'x'}\ndef run(): pass")
    with pytest.raises(ValidationError, match="不安全"):
        FeaturePackageInspector().inspect("bad.zip", bad.getvalue(), LIMITS)

    direct = feature_zip("直连依赖", requirements="demo @ https://example.invalid/demo.whl")
    with pytest.raises(ValidationError):
        FeaturePackageInspector().inspect("direct.zip", direct, LIMITS)


def test_report_metadata_is_normalized_and_rejects_secret_fields():
    schema = {
        "title": "同步结果",
        "item_label": "商品",
        "columns": [
            {"key": "sku", "label": "商品编码", "type": "string"},
            {"key": "quantity", "label": "库存", "type": "integer"},
        ],
    }
    inspected = FeaturePackageInspector().inspect(
        "report.zip",
        feature_zip("报表功能", report=schema),
        LIMITS,
    )
    assert inspected.metadata.report_schema == schema

    unsafe_schema = {
        "columns": [{"key": "api_token", "label": "接口密钥", "type": "string"}],
    }
    with pytest.raises(ValidationError, match="密钥"):
        FeaturePackageInspector().inspect(
            "unsafe-report.zip",
            feature_zip("不安全报表", report=unsafe_schema),
            LIMITS,
        )


def test_existing_ozon_package_is_accepted_without_execution():
    source = Path(__file__).parents[2] / "features" / "ozon.zip"
    inspected = FeaturePackageInspector().inspect(
        source.name,
        source.read_bytes(),
        PackageLimits(60_000_000, 1_000, 60_000_000, 220_000_000, 200),
    )
    assert inspected.metadata.name
    assert inspected.default_data_source is not None
    assert inspected.default_data_source.filename.lower().endswith(".xlsx")


def test_default_data_source_replacement_and_secret_encryption(client, app, tmp_path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    customer_id = client.get("/api/customers").get_json()["items"][0]["id"]

    created = upload(client, csrf, customer_id, feature_zip("库存同步"))
    assert created.status_code == 201, created.get_json()
    version = created.get_json()["version"]
    assert version["status"] == "READY"
    features = client.get(f"/api/customers/{customer_id}/features").get_json()["items"]
    assert len(features) == 1
    feature = features[0]
    assert feature["dataSource"]["sourceKind"] == "DEFAULT"
    assert client.get(f"/api/customer-features/{feature['id']}/data-source/download").data == b"default-data"

    replacement = client.put(
        f"/api/customer-features/{feature['id']}/data-source",
        headers={"X-CSRF-Token": csrf},
        data={"file": (io.BytesIO(b"customer-specific"), "business.xlsx")},
        content_type="multipart/form-data",
    )
    assert replacement.status_code == 200, replacement.get_json()
    assert replacement.get_json()["current"]["revisionNumber"] == 2
    assert client.get(f"/api/customer-features/{feature['id']}/data-source/download").data == b"customer-specific"

    config = client.get(f"/api/customer-features/{feature['id']}/config")
    assert config.status_code == 200
    token_field = next(item for item in config.get_json()["fields"] if item["key"] == "api_token")
    assert token_field["isSet"] is False
    assert "value" not in token_field
    saved = client.put(
        f"/api/customer-features/{feature['id']}/config",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"batch_size": 250, "api_token": "secret-value-never-return"}, "clearSecrets": []},
    )
    assert saved.status_code == 200, saved.get_json()
    assert "secret-value-never-return" not in saved.get_data(as_text=True)
    assert saved.get_json()["complete"] is True

    services = app.extensions["fcc_services"]
    with services.database.session() as db:
        revisions = db.scalars(select(CustomerFeatureDataSourceRevisionModel).where(
            CustomerFeatureDataSourceRevisionModel.customer_feature_id == feature["id"]
        ).order_by(CustomerFeatureDataSourceRevisionModel.revision_number)).all()
        assert [item.revision_number for item in revisions] == [1, 2]
        encrypted = db.get(FeatureConfigValueModel, (feature["id"], "api_token"))
        assert encrypted.value_json is None
        assert b"secret-value-never-return" not in encrypted.encrypted_value
        with pytest.raises(ConfigCipherError):
            services.features.cipher.decrypt("another-customer-feature", "api_token", encrypted.encrypted_value)


def test_customer_access_is_enforced_for_data_source(client, tmp_path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    customer_a = client.get("/api/customers").get_json()["items"][0]
    customer_b = client.post("/api/admin/customers", headers={"X-CSRF-Token": csrf}, json={"name": "客户乙", "description": ""}).get_json()["customer"]
    created = upload(client, csrf, customer_a["id"], feature_zip("客户隔离功能"))
    feature_id = client.get(f"/api/customers/{customer_a['id']}/features").get_json()["items"][0]["id"]
    assert created.status_code == 201
    user = client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={"username": "only-b", "displayName": "只管乙", "role": "operator", "customerIds": [customer_b["id"]]},
    ).get_json()
    operator = app_client = client.application.test_client()
    logged_in = login(operator, "only-b", user["temporaryPassword"]).get_json()
    changed = operator.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": logged_in["csrfToken"]},
        json={"currentPassword": user["temporaryPassword"], "newPassword": "Operator private password 9!"},
    ).get_json()
    denied = app_client.get(f"/api/customer-features/{feature_id}/data-source/download")
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "CUSTOMER_ACCESS_DENIED"


def test_dependency_environment_is_reused_and_failed_build_can_retry(client, app, tmp_path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    customer_id = client.get("/api/customers").get_json()["items"][0]["id"]
    builder = app.extensions["test_environment_builder"]
    first = upload(client, csrf, customer_id, feature_zip("依赖功能一", requirements="httpx==0.28.1\n"), "one.zip")
    second = upload(client, csrf, customer_id, feature_zip("依赖功能二", requirements="httpx==0.28.1\n"), "two.zip")
    assert first.get_json()["version"]["status"] == "PREPARING"
    assert second.get_json()["version"]["status"] == "PREPARING"
    services = app.extensions["fcc_services"]
    worker = RunnerWorker(
        database=services.database,
        settings=services.settings,
        clock=services.clock,
        materializer=RunMaterializer(services.database, services.paths, services.runs.snapshot_cipher, ScriptIdentity()),
        dependency_preparer=DependencyPreparer(services.database, services.settings, services.clock, builder),
        runner_id="phase-b-test",
    )
    worker.run_until_idle()
    definitions = client.get("/api/admin/feature-definitions").get_json()["items"]
    assert {item["status"] for definition in definitions for item in definition["versions"]} == {"READY"}
    assert builder.calls == 1
    with app.extensions["fcc_services"].database.session() as db:
        assert len(db.scalars(select(RuntimeEnvironmentModel)).all()) == 1

    builder.fail = True
    failed = upload(client, csrf, customer_id, feature_zip("失败后重试", requirements="urllib3==2.6.3\n"), "fail.zip")
    failed_version = failed.get_json()["version"]
    assert failed_version["status"] == "PREPARING"
    worker.run_until_idle()
    failed_version = next(
        version
        for definition in client.get("/api/admin/feature-definitions").get_json()["items"]
        for version in definition["versions"]
        if version["id"] == failed_version["id"]
    )
    assert failed_version["status"] == "DEPENDENCY_FAILED"
    builder.fail = False
    retried = client.post(
        f"/api/admin/feature-versions/{failed_version['id']}/prepare",
        headers={"X-CSRF-Token": csrf},
    )
    assert retried.status_code == 200
    assert retried.get_json()["version"]["status"] == "PREPARING"
    worker.run_until_idle()
    assert services.features.get_version(failed_version["id"])["status"] == "READY"
    worker.shutdown()


def test_new_version_preserves_customer_data_source_until_explicit_reset(client, tmp_path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    customer_id = client.get("/api/customers").get_json()["items"][0]["id"]
    first = upload(client, csrf, customer_id, feature_zip("版本功能", default_source=b"v1"), "v1.zip").get_json()["version"]
    feature = client.get(f"/api/customers/{customer_id}/features").get_json()["items"][0]
    client.put(
        f"/api/customer-features/{feature['id']}/data-source",
        headers={"X-CSRF-Token": csrf},
        data={"file": (io.BytesIO(b"customer-current"), "current.xlsx")},
        content_type="multipart/form-data",
    )
    second_response = upload(client, csrf, customer_id, feature_zip("版本功能", default_source=b"v2", description="第二版"), "v2.zip")
    assert second_response.get_json()["activatedForCustomer"] is False
    second = second_response.get_json()["version"]
    before = client.get(f"/api/customers/{customer_id}/features").get_json()["items"][0]
    assert before["versionId"] == first["id"]
    activated = client.post(
        f"/api/admin/customer-features/{feature['id']}/activate-version",
        headers={"X-CSRF-Token": csrf},
        json={"versionId": second["id"], "useDefaultDataSource": False},
    )
    assert activated.status_code == 200, activated.get_json()
    assert client.get(f"/api/customer-features/{feature['id']}/data-source/download").data == b"customer-current"


def test_management_network_uses_resolved_client_and_prevents_lockout(client, tmp_path):
    session = initialize(client, tmp_path / "data", password=PASSWORD)
    csrf = session["csrfToken"]
    blocked = client.put(
        "/api/admin/settings",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"security.management_network_mode": "TRUSTED_NETWORKS", "security.management_trusted_cidrs": ["203.0.113.8/32"]}},
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "NETWORK_LOCKOUT_PREVENTED"

    proxy = client.put(
        "/api/admin/settings",
        headers={"X-CSRF-Token": csrf},
        json={"values": {"security.trusted_proxy_cidrs": ["10.0.0.0/8"]}},
    )
    assert proxy.status_code == 200
    enabled = client.put(
        "/api/admin/settings",
        environ_base={"REMOTE_ADDR": "10.1.1.1"},
        headers={"X-CSRF-Token": csrf, "X-Forwarded-For": "203.0.113.8"},
        json={"values": {"security.management_network_mode": "TRUSTED_NETWORKS", "security.management_trusted_cidrs": ["203.0.113.8/32"]}},
    )
    assert enabled.status_code == 200, enabled.get_json()
    spoofed = client.get(
        "/api/admin/users",
        environ_base={"REMOTE_ADDR": "198.51.100.4"},
        headers={"X-Forwarded-For": "203.0.113.8"},
    )
    assert spoofed.status_code == 403
    allowed = client.get(
        "/api/admin/users",
        environ_base={"REMOTE_ADDR": "10.1.1.1"},
        headers={"X-Forwarded-For": "203.0.113.8"},
    )
    assert allowed.status_code == 200
