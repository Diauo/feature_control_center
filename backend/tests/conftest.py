from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.web.app_factory import create_app
from app.infrastructure.runtime_environment import EnvironmentBuildResult


@dataclass
class MutableClock:
    value: int = 1_800_000_000

    def now(self) -> int:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds


@dataclass
class FakeEnvironmentBuilder:
    calls: int = 0
    fail: bool = False

    def build(self, request_fingerprint, requirements_text, offline_wheels, settings):
        self.calls += 1
        if self.fail:
            from app.infrastructure.runtime_environment import EnvironmentBuildError

            raise EnvironmentBuildError("测试依赖源不可用")
        return EnvironmentBuildResult(
            resolved_fingerprint=request_fingerprint,
            resolved_lock_text=requirements_text,
            wheel_manifest=tuple(
                {"filename": item.filename, "sha256": item.sha256.hex(), "size": len(item.content)}
                for item in offline_wheels
            ),
            environment_path=f"/test/runtime/{request_fingerprint}",
        )


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def app(tmp_path: Path, clock: MutableClock) -> Iterator[Flask]:
    builder = FakeEnvironmentBuilder()
    application = create_app(data_dir=tmp_path / "data", testing=True, clock=clock, environment_builder=builder)
    application.extensions["test_environment_builder"] = builder
    yield application
    application.extensions["fcc_services"].database.dispose()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def preauth_csrf(client: FlaskClient) -> str:
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.get_json()["csrfToken"]


def bootstrap_code(data_dir: Path) -> str:
    text = (data_dir / "first-run.txt").read_text(encoding="utf-8")
    match = re.search(r"^初始化码：(\S+)$", text, re.MULTILINE)
    assert match is not None
    return match.group(1)


def initialize(client: FlaskClient, data_dir: Path, *, password: str = "Correct horse battery 7!") -> dict[str, Any]:
    response = client.post(
        "/api/setup/initialize",
        headers={"X-CSRF-Token": preauth_csrf(client)},
        json={
            "bootstrapCode": bootstrap_code(data_dir),
            "systemName": "测试功能中心",
            "adminUsername": "admin",
            "adminDisplayName": "测试管理员",
            "password": password,
            "customerName": "客户甲",
        },
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def login(client: FlaskClient, username: str, password: str):
    return client.post(
        "/api/auth/login",
        headers={"X-CSRF-Token": preauth_csrf(client)},
        json={"username": username, "password": password},
    )
