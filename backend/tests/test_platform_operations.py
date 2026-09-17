from __future__ import annotations

import io
import json
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import py7zr

from app.domain.identity import ValidationError
from app.infrastructure.package_inspector import FeaturePackageInspector, PackageLimits, package_format_for_filename
from app.runner.retention import SystemLogRetentionCleaner
from conftest import initialize


LIMITS = PackageLimits(2_000_000, 100, 1_000_000, 2_000_000, 100)


def _feature_files() -> dict[str, bytes]:
    metadata = {
        "name": "多格式功能",
        "description": "验证归档适配器",
        "entrypoint": "run",
        "configs": {},
        "data_source": {"filename": "dataSource.xlsx", "required": True, "extensions": [".xlsx"]},
    }
    return {
        "__init__.py": f"__meta__ = {metadata!r}\ndef run(context):\n    return None\n".encode(),
        "dataSource.xlsx": b"source",
    }


def _tar_package(mode: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        for name, content in _feature_files().items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "mode"),
    [
        ("feature.tar", "w:"),
        ("feature.tar.gz", "w:gz"),
        ("feature.tbz2", "w:bz2"),
        ("feature.txz", "w:xz"),
    ],
)
def test_tar_family_packages_share_the_same_static_validation(filename: str, mode: str):
    inspected = FeaturePackageInspector().inspect(filename, _tar_package(mode), LIMITS)
    assert inspected.metadata.name == "多格式功能"
    assert inspected.default_data_source is not None
    assert inspected.default_data_source.content == b"source"


def test_disabled_package_format_is_rejected_before_parsing():
    with pytest.raises(ValidationError, match="未启用"):
        FeaturePackageInspector().inspect("feature.tar", _tar_package("w:"), LIMITS, ("zip",))


def test_7z_package_uses_the_same_metadata_and_data_source_contract():
    buffer = io.BytesIO()
    with py7zr.SevenZipFile(buffer, mode="w") as archive:
        for name, content in _feature_files().items():
            archive.writestr(content, name)
    inspected = FeaturePackageInspector().inspect("feature.7z", buffer.getvalue(), LIMITS)
    assert inspected.metadata.entrypoint == "run"
    assert inspected.default_data_source is not None


def test_rar_is_recognized_but_self_extracting_or_invalid_content_is_rejected():
    assert package_format_for_filename("feature.RAR") == "rar"
    with pytest.raises(ValidationError, match="RAR 格式不匹配"):
        FeaturePackageInspector().inspect("feature.rar", b"MZ" + b"Rar!\x1a\x07\x00", LIMITS)


def test_system_status_logs_and_audit_snapshots(client, app, tmp_path: Path):
    initialize(client, tmp_path / "data")
    status = client.get("/api/admin/system/status")
    assert status.status_code == 200
    assert status.get_json()["version"] == "2.2.0"
    assert {item["name"] for item in status.get_json()["services"]} == {"web", "runner", "scheduler"}

    log_dir = tmp_path / "data" / "system-logs" / "web"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    line = {"timestamp": f"{today}T00:00:00.000Z", "service": "web", "level": "INFO", "logger": "test", "message": "ready"}
    (log_dir / f"{today}.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    logs = client.get(f"/api/admin/system/logs?service=web&date={today}")
    assert logs.status_code == 200
    assert logs.get_json()["items"][0]["message"] == "ready"

    settings = client.get("/api/admin/settings")
    assert settings.status_code == 200
    audit = client.get("/api/admin/audit-logs?category=ADMIN&action=admin.settings.view")
    item = audit.get_json()["items"][0]
    assert item["actorRole"] == "admin"
    assert item["actorUsername"] == "admin"
    assert item["requestMethod"] == "GET"
    assert item["requestPath"] == "/api/admin/settings"
    assert item["requestId"]


def test_system_log_retention_keeps_the_active_day(app, clock, tmp_path: Path):
    services = app.extensions["fcc_services"]
    today = datetime.fromtimestamp(clock.now(), UTC).date()
    directory = tmp_path / "data" / "system-logs" / "runner"
    directory.mkdir(parents=True, exist_ok=True)
    old = directory / f"{today - timedelta(days=181):%Y-%m-%d}.jsonl"
    active = directory / f"{today:%Y-%m-%d}.jsonl"
    old.write_text("old\n", encoding="utf-8")
    active.write_text("active\n", encoding="utf-8")

    result = SystemLogRetentionCleaner(services.paths, services.settings, clock).purge()
    assert result.deleted_files == 1
    assert not old.exists()
    assert active.exists()
