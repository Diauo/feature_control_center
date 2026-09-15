from __future__ import annotations

import logging
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from app.application.auth import AuthService
from app.application.bootstrap import BootstrapService
from app.application.errors import ApplicationError
from app.application.features import FeatureService
from app.application.identity import IdentityService
from app.application.runs import RunService
from app.application.schedules import ScheduleService
from app.application.settings import SettingsService
from app.application.system_settings import SystemSettingsService
from app.application.system_operations import SystemOperationsService
from app.application.system_updates import SystemUpdateService
from app.domain.time import Clock, SystemClock
from app.infrastructure.database import Database
from app.infrastructure.instance_manager import InstanceManager
from app.infrastructure.migration_runner import run_migrations
from app.infrastructure.package_inspector import FeaturePackageInspector
from app.infrastructure.paths import AppPaths
from app.infrastructure.runtime_environment import PipRuntimeEnvironmentBuilder, RuntimeEnvironmentBuilder
from app.security.config_cipher import ConfigCipher
from app.security.run_snapshot_cipher import RunSnapshotCipher
from app.security.crypto import PreAuthCsrf
from app.security.passwords import PasswordService
from app.web.errors import register_error_handlers
from app.web.request_security import RequestSecurityResolver
from app.web.routes import admin, auth, customers, features, health, runs, schedules, setup, system_operations, system_settings, system_updates
from app.web.services import Services


def create_app(
    *,
    data_dir: Path | str | None = None,
    testing: bool = False,
    clock: Clock | None = None,
    public_url: str = "http://localhost:8080",
    environment_builder: RuntimeEnvironmentBuilder | None = None,
    run_database_migrations: bool = True,
) -> Flask:
    resolved_data_dir = Path(data_dir) if data_dir is not None else Path.cwd() / "data"
    paths = AppPaths(resolved_data_dir.resolve())
    database_existed = paths.database.exists()
    app_clock = clock or SystemClock()
    instance = InstanceManager(paths, app_clock)
    instance_key = instance.prepare_key(database_existed)
    if run_database_migrations:
        run_migrations(paths.database)
    database = Database(paths.database)
    database.configure_database()
    instance.bind_and_seed(database, instance_key)

    settings = SettingsService(database)
    passwords = PasswordService()
    auth_service = AuthService(database, settings, passwords, app_clock, instance_key)
    bootstrap_service = BootstrapService(
        database,
        instance,
        auth_service,
        passwords,
        app_clock,
        instance_key,
    )
    identity_service = IdentityService(database, passwords, auth_service, app_clock)
    system_settings_service = SystemSettingsService(database, settings, auth_service, app_clock)
    system_operations_service = SystemOperationsService(database, settings, paths, app_clock)
    system_updates_service = SystemUpdateService(
        database,
        settings,
        auth_service,
        paths,
        app_clock,
        system_operations_service.version,
    )
    config_cipher = ConfigCipher(instance_key)
    resolved_environment_builder = environment_builder or PipRuntimeEnvironmentBuilder(paths)
    feature_service = FeatureService(
        database,
        settings,
        auth_service,
        app_clock,
        FeaturePackageInspector(),
        config_cipher,
    )
    run_service = RunService(
        database,
        settings,
        app_clock,
        config_cipher,
        RunSnapshotCipher(instance_key),
    )
    schedule_service = ScheduleService(database, settings, app_clock, run_service)
    preauth_csrf = PreAuthCsrf(instance_key)

    static_dir = Path(__file__).with_name("static")
    app = Flask(__name__, static_folder=None)
    app.config.update(
        TESTING=testing,
        # The per-route guard enforces the administrator setting. This ceiling is
        # intentionally a little above its 2 GiB maximum so multipart framing is
        # never the reason an otherwise valid configured upload is rejected.
        MAX_CONTENT_LENGTH=2_148_532_224,
        JSON_SORT_KEYS=False,
    )
    app.extensions["fcc_services"] = Services(
        paths=paths,
        database=database,
        settings=settings,
        auth=auth_service,
        bootstrap=bootstrap_service,
        identity=identity_service,
        features=feature_service,
        runs=run_service,
        schedules=schedule_service,
        system_settings=system_settings_service,
        system_operations=system_operations_service,
        system_updates=system_updates_service,
        instance=instance,
        preauth_csrf=preauth_csrf,
        clock=app_clock,
    )
    app.extensions["fcc_request_security"] = RequestSecurityResolver(settings)
    app.extensions["fcc_environment_builder"] = resolved_environment_builder

    @app.before_request
    def enforce_request_size():
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        length = request.content_length
        is_feature_package = request.path == "/api/admin/features/versions"
        is_data_source = request.path.startswith("/api/customer-features/") and request.path.endswith("/data-source")
        is_update_package = request.path == "/api/admin/system/updates/packages"
        if (is_feature_package or is_data_source or is_update_package) and length is None:
            raise ApplicationError("UPLOAD_LENGTH_REQUIRED", "上传请求必须包含 Content-Length", status=411)
        if is_feature_package:
            maximum = settings.package_limits().max_package_bytes + 1_048_576
        elif is_data_source:
            maximum = settings.data_source_max_bytes() + 1_048_576
        elif is_update_package:
            maximum = settings.update_package_max_bytes() + 1_048_576
        else:
            maximum = 1_048_576
        if length is not None and length > maximum:
            raise ApplicationError("REQUEST_TOO_LARGE", "请求内容超过系统大小限制", status=413)
        return None

    app.register_blueprint(setup.blueprint)
    app.register_blueprint(auth.blueprint)
    app.register_blueprint(customers.blueprint)
    app.register_blueprint(admin.blueprint)
    app.register_blueprint(features.blueprint)
    app.register_blueprint(runs.blueprint)
    app.register_blueprint(schedules.blueprint)
    app.register_blueprint(system_settings.blueprint)
    app.register_blueprint(system_operations.blueprint)
    app.register_blueprint(system_updates.blueprint)
    app.register_blueprint(health.blueprint)
    register_error_handlers(app)
    _register_security_headers(app)
    _register_frontend(app, static_dir)

    status = instance.ensure_bootstrap(database, instance_key, public_url)
    if status.required:
        app.logger.warning("系统尚未初始化。初始化码已写入 %s", status.first_run_file)
    return app


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Request-ID", request.environ.setdefault("fcc.request_id", uuid.uuid4().hex))
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resolver = app.extensions["fcc_request_security"]
        if resolver.resolve(request).secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if response.content_type and response.content_type.startswith("application/json"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_frontend(app: Flask, static_dir: Path) -> None:
    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path: str = ""):
        if path.startswith("api/"):
            return jsonify({"error": {"code": "NOT_FOUND", "message": "接口不存在", "details": {}}}), 404
        candidate = static_dir / path
        if path and candidate.is_file():
            return send_from_directory(static_dir, path)
        index = static_dir / "index.html"
        if index.is_file():
            return send_from_directory(static_dir, "index.html")
        return (
            "<!doctype html><meta charset='utf-8'><title>功能控制中心</title>"
            "<h1>前端尚未构建</h1><p>开发环境请运行 frontend 的 Vite 服务。</p>",
            503,
            {"Content-Type": "text/html; charset=utf-8"},
        )
