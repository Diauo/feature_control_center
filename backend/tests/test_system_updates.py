from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sqlite3
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.infrastructure.models import AuditLogModel, SystemUpdateModel
from app.infrastructure.paths import AppPaths
from app.launcher import ManagedProcesses, _start_services, _worker_heartbeats_ready
from app.update_tool import build_update_package
from app.update_package import UpdatePackageError, canonical_manifest, inspect_update_package
from app.update_supervisor import ReleaseDescriptor, backup_database, recover_rejected_control, restore_database
from app.web.app_factory import create_app
from conftest import initialize


def _package(
    private_key: Ed25519PrivateKey,
    *,
    target_version: str = "1.0.1",
    platform: str = "linux_x86_64",
    wheel_path: str = "wheels/feature_control_center-1.0.1-py3-none-any.whl",
    wheel_content: bytes | None = None,
    corrupt_signature: bool = False,
) -> bytes:
    content = wheel_content or os.urandom(2_048)
    manifest = {
        "schemaVersion": 1,
        "product": "feature-control-center",
        "version": target_version,
        "compatibleFrom": ">=1.0.0,<2.0.0",
        "launcherProtocol": 1,
        "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": platform,
        "databaseRevision": "0008_scope_paging_update",
        "rollbackCompatible": True,
        "appWheel": wheel_path,
        "releaseNotes": ["修复一个经过验证的问题"],
        "files": [
            {
                "path": wheel_path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    canonical = canonical_manifest(manifest)
    signature = private_key.sign(canonical)
    if corrupt_signature:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", canonical)
        archive.writestr("manifest.sig", base64.b64encode(signature))
        archive.writestr(wheel_path, content)
    return output.getvalue()


def test_signed_update_package_is_verified_before_use(tmp_path: Path):
    private_key = Ed25519PrivateKey.generate()
    package = tmp_path / "release.fcup"
    package.write_bytes(_package(private_key))

    inspected = inspect_update_package(
        package,
        current_version="1.0.0",
        maximum_bytes=10_000_000,
        public_key=private_key.public_key(),
        expected_platform="linux_x86_64",
    )

    assert inspected.manifest.version == "1.0.1"
    assert inspected.manifest.database_revision == "0008_scope_paging_update"
    assert inspected.manifest.rollback_compatible is True
    assert inspected.package_sha256 == hashlib.sha256(package.read_bytes()).digest()


def test_update_package_rejects_bad_signature_and_unsafe_manifest_path(tmp_path: Path):
    private_key = Ed25519PrivateKey.generate()
    bad_signature = tmp_path / "bad-signature.fcup"
    bad_signature.write_bytes(_package(private_key, corrupt_signature=True))
    with pytest.raises(UpdatePackageError) as signature_error:
        inspect_update_package(
            bad_signature,
            current_version="1.0.0",
            maximum_bytes=10_000_000,
            public_key=private_key.public_key(),
            expected_platform="linux_x86_64",
        )
    assert signature_error.value.code == "UPDATE_SIGNATURE_INVALID"

    unsafe = tmp_path / "unsafe.fcup"
    unsafe.write_bytes(_package(private_key, wheel_path="wheels/../escape.whl"))
    with pytest.raises(UpdatePackageError) as path_error:
        inspect_update_package(
            unsafe,
            current_version="1.0.0",
            maximum_bytes=10_000_000,
            public_key=private_key.public_key(),
            expected_platform="linux_x86_64",
        )
    assert path_error.value.code == "UPDATE_PACKAGE_PATH_INVALID"


def test_update_package_builder_creates_a_verifiable_offline_bundle(tmp_path: Path):
    private_key = Ed25519PrivateKey.generate()
    private_key_file = tmp_path / "signing-key.pem"
    private_key_file.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    app_wheel = wheelhouse / "feature_control_center-1.0.1-py3-none-any.whl"
    with zipfile.ZipFile(app_wheel, mode="w") as archive:
        archive.writestr(
            "feature_control_center-1.0.1.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: feature-control-center\nVersion: 1.0.1\n\n",
        )
    output = tmp_path / "release.fcup"

    build_update_package(
        wheelhouse=wheelhouse,
        private_key_file=private_key_file,
        output=output,
        version="1.0.1",
        compatible_from=">=1.0.0,<2.0.0",
        target_platform="linux_x86_64",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        database_revision="0008_scope_paging_update",
        notes_file=None,
        rollback_compatible=True,
    )

    inspected = inspect_update_package(
        output,
        current_version="1.0.0",
        maximum_bytes=10_000_000,
        public_key=private_key.public_key(),
        expected_platform="linux_x86_64",
    )
    assert inspected.manifest.app_wheel.endswith(app_wheel.name)
    assert inspected.manifest.version == "1.0.1"


def test_update_overview_and_default_rar_setting(client, tmp_path: Path):
    initialize(client, tmp_path / "data")

    settings = client.get("/api/admin/settings")
    assert settings.status_code == 200
    assert "rar" in settings.get_json()["values"]["feature.allowed_package_formats"]
    assert settings.get_json()["values"]["updates.max_package_bytes"] == 524_288_000
    assert settings.get_json()["values"]["runner.report_max_items"] == 60_000

    overview = client.get("/api/admin/system/updates")
    assert overview.status_code == 200
    assert overview.get_json()["currentVersion"] == "2.4.0"
    assert overview.get_json()["supervisor"]["available"] is False
    assert overview.get_json()["items"] == []
    assert overview.get_json()["pagination"]["total"] == 0


def test_update_database_backup_is_consistent_and_restorable(tmp_path: Path):
    paths = AppPaths(tmp_path / "data")
    paths.create_directories()
    connection = sqlite3.connect(paths.database)
    try:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('before')")
        connection.commit()
    finally:
        connection.close()

    backup = backup_database(paths, "a" * 32, "1.0.0")
    assert not list(paths.backups_dir.glob("*.partial"))
    connection = sqlite3.connect(paths.database)
    try:
        connection.execute("UPDATE sample SET value = 'after'")
        connection.commit()
    finally:
        connection.close()

    restore_database(paths, backup)
    connection = sqlite3.connect(paths.database)
    try:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("before",)
    finally:
        connection.close()


def test_rejected_control_releases_pending_update_and_writes_audit(tmp_path: Path):
    paths = AppPaths(tmp_path / "data")
    app = create_app(data_dir=paths.data_dir, testing=True)
    database = app.extensions["fcc_services"].database
    update_id = "b" * 32
    with database.session() as db:
        db.add(
            SystemUpdateModel(
                id=update_id,
                operation="APPLY",
                source_version="1.0.0",
                target_version="1.0.1",
                package_filename="release.fcup",
                package_sha256=b"a" * 32,
                package_size=1024,
                manifest_json="{}",
                release_notes_json="[]",
                status="PENDING",
                stage="QUEUED",
                progress=15,
                active_guard=1,
                rollback_compatible=True,
                client_ip="127.0.0.1",
                request_id="c" * 32,
                created_at=1_800_000_000,
                updated_at=1_800_000_000,
            )
        )

    recovered = recover_rejected_control(
        paths,
        {"updateId": update_id},
        RuntimeError("控制文件摘要不一致"),
    )

    assert recovered is True
    with database.session() as db:
        row = db.get(SystemUpdateModel, update_id)
        assert row is not None
        assert row.status == "READY"
        assert row.active_guard is None
        assert "控制文件摘要不一致" in (row.error_message or "")
        audit = db.query(AuditLogModel).filter_by(action="system.system_update.control_rejected").one()
        assert audit.target_id == update_id
    database.dispose()


def test_failed_update_retry_creates_a_new_record_and_preserves_history(client, app, tmp_path: Path, monkeypatch):
    initialized = initialize(client, tmp_path / "data")
    services = app.extensions["fcc_services"]
    source_id = "d" * 32
    package = b"previously-verified-update-package"
    digest = hashlib.sha256(package).digest()
    services.paths.update_inbox.joinpath(f"{source_id}.fcup").write_bytes(package)
    with services.database.session() as db:
        db.add(
            SystemUpdateModel(
                id=source_id,
                operation="APPLY",
                source_version=services.system_updates.version_provider(),
                target_version="2.2.1",
                package_filename="release.fcup",
                package_sha256=digest,
                package_size=len(package),
                manifest_json="{}",
                release_notes_json='["修复"]',
                status="ROLLED_BACK",
                stage="AUTOMATIC_ROLLBACK",
                progress=100,
                active_guard=None,
                rollback_compatible=True,
                error_message="候选版本未通过健康检查",
                created_by=initialized["user"]["id"],
                actor_display_name=initialized["user"]["displayName"],
                client_ip="127.0.0.1",
                request_id="e" * 32,
                created_at=1_800_000_000,
                updated_at=1_800_000_000,
                completed_at=1_800_000_000,
            )
        )
    monkeypatch.setattr(
        "app.application.system_updates.inspect_update_package",
        lambda *_args, **_kwargs: SimpleNamespace(package_sha256=digest),
    )

    response = client.post(
        f"/api/admin/system/updates/{source_id}/retry",
        headers={"X-CSRF-Token": initialized["csrfToken"]},
    )

    assert response.status_code == 201, response.get_json()
    created = response.get_json()["item"]
    assert created["id"] != source_id
    assert created["status"] == "READY"
    assert created["canApply"] is True
    assert services.paths.update_inbox.joinpath(f"{created['id']}.fcup").read_bytes() == package
    with services.database.session() as db:
        original = db.get(SystemUpdateModel, source_id)
        assert original is not None
        assert original.status == "ROLLED_BACK"
        assert original.error_message == "候选版本未通过健康检查"
        assert db.query(SystemUpdateModel).filter_by(package_sha256=digest).count() == 2


def test_candidate_heartbeat_must_match_the_spawned_worker_pids(tmp_path: Path):
    paths = AppPaths(tmp_path / "data")
    app = create_app(data_dir=paths.data_dir, testing=True)
    database = app.extensions["fcc_services"].database
    started_at = 1_800_000_000
    with sqlite3.connect(paths.database) as connection:
        connection.execute(
            "INSERT INTO runner_heartbeat "
            "(runner_id, instance_token, process_id, status, started_at, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("candidate-runner", "runner-token", 4101, "ACTIVE", started_at, started_at),
        )
        connection.execute(
            "INSERT INTO scheduler_heartbeat "
            "(scheduler_id, instance_token, process_id, status, started_at, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("candidate-scheduler", "scheduler-token", 4102, "ACTIVE", started_at, started_at),
        )
        connection.commit()
    matching = ManagedProcesses(
        SimpleNamespace(pid=4100), SimpleNamespace(pid=4101), SimpleNamespace(pid=4102)
    )
    stale = ManagedProcesses(
        SimpleNamespace(pid=4100), SimpleNamespace(pid=5101), SimpleNamespace(pid=5102)
    )

    assert _worker_heartbeats_ready(paths, matching, started_at) is True
    assert _worker_heartbeats_ready(paths, stale, started_at) is False
    database.dispose()


def test_partial_service_startup_terminates_every_process_already_spawned(tmp_path: Path, monkeypatch):
    class FakeProcess:
        pid = 6201

        def __init__(self) -> None:
            self.terminated = False
            self.waited = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True
            return 0

    first = FakeProcess()
    calls = 0

    def fake_popen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return first
        raise OSError("runner spawn failed")

    monkeypatch.setattr("app.launcher.subprocess.Popen", fake_popen)
    paths = AppPaths(tmp_path / "data")
    paths.create_directories()
    descriptor = ReleaseDescriptor(
        kind="bundled",
        version="1.0.0",
        python_executable=Path(sys.executable),
        release_dir_name=None,
        skip_migrations=False,
        database_revision="0008_scope_paging_update",
    )

    with pytest.raises(OSError, match="runner spawn failed"):
        _start_services(
            descriptor,
            paths=paths,
            host="127.0.0.1",
            port=8080,
            public_url="http://127.0.0.1:8080",
            web_uid=1000,
            web_gid=1000,
        )

    assert first.terminated is True
    assert first.waited is True
