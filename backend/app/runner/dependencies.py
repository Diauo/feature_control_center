from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.application.settings import SettingsService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import CustomerFeatureModel, FeatureVersionModel, RuntimeEnvironmentModel
from app.infrastructure.package_inspector import FeaturePackageInspector
from app.infrastructure.runtime_environment import RuntimeEnvironmentBuilder
from app.infrastructure.runtime_permissions import publish_runtime_environment


class DependencyPreparer:
    """Prepare one persistent dependency environment outside request handling."""

    def __init__(
        self,
        database: Database,
        settings: SettingsService,
        clock: Clock,
        builder: RuntimeEnvironmentBuilder,
        script_gid: int | None = None,
        environments_root: Path | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        self.builder = builder
        self.script_gid = script_gid
        self.environments_root = environments_root
        if script_gid is not None and environments_root is None:
            raise ValueError("降权依赖环境必须指定受信任的缓存根目录")
        self.inspector = FeaturePackageInspector()

    def next_environment_id(self, excluded: set[str]) -> str | None:
        with self.database.session() as db:
            statement = (
                select(RuntimeEnvironmentModel.id)
                .where(RuntimeEnvironmentModel.status == "PREPARING")
                .order_by(RuntimeEnvironmentModel.updated_at)
            )
            for environment_id in db.scalars(statement):
                if environment_id not in excluded:
                    return environment_id
            return None

    def prepare(self, environment_id: str) -> None:
        missing_version = False
        with self.database.session() as db:
            environment = db.get(RuntimeEnvironmentModel, environment_id)
            if environment is None or environment.status != "PREPARING":
                return
            version = db.scalar(
                select(FeatureVersionModel)
                .options(undefer(FeatureVersionModel.package_blob))
                .where(FeatureVersionModel.runtime_environment_id == environment_id)
                .order_by(FeatureVersionModel.created_at)
                .limit(1)
            )
            if version is None:
                missing_version = True
                package_filename = ""
                package_blob = b""
                fingerprint = environment.request_fingerprint
                requirements = environment.requirements_text
            else:
                package_filename = version.package_filename
                package_blob = bytes(version.package_blob)
                fingerprint = environment.request_fingerprint
                requirements = environment.requirements_text
        if missing_version:
            self._finalize(environment_id, None, "没有功能版本引用这个依赖环境")
            return
        try:
            package = self.inspector.inspect(package_filename, package_blob, self.settings.package_limits())
            result = self.builder.build(
                fingerprint,
                requirements,
                package.offline_wheels,
                self.settings.dependencies(),
            )
            self._publish_environment(Path(result.environment_path))
        except Exception as exc:
            self._finalize(environment_id, None, str(exc)[-4_000:])
        else:
            self._finalize(environment_id, result, None)

    def _finalize(self, environment_id: str, result, error: str | None) -> None:
        now = self.clock.now()
        with self.database.session() as db:
            environment = db.get(RuntimeEnvironmentModel, environment_id)
            if environment is None:
                return
            environment.updated_at = now
            if error:
                environment.status = "FAILED"
                environment.failure_summary = error
            else:
                environment.status = "READY"
                environment.failure_summary = None
                environment.resolved_fingerprint = result.resolved_fingerprint
                environment.resolved_lock_text = result.resolved_lock_text
                environment.wheel_manifest_json = json.dumps(
                    result.wheel_manifest, ensure_ascii=False, separators=(",", ":")
                )
                environment.environment_path = result.environment_path
            versions = db.scalars(
                select(FeatureVersionModel).where(FeatureVersionModel.runtime_environment_id == environment.id)
            ).all()
            version_ids: list[str] = []
            for version in versions:
                version.status = "DEPENDENCY_FAILED" if error else "READY"
                version.prepare_error = error
                version_ids.append(version.id)
            if not version_ids:
                return
            features = db.scalars(
                select(CustomerFeatureModel).where(CustomerFeatureModel.feature_version_id.in_(version_ids))
            ).all()
            versions_by_id = {version.id: version for version in versions}
            for feature in features:
                version = versions_by_id[feature.feature_version_id]
                schema = json.loads(version.data_source_schema_json) if version.data_source_schema_json else None
                if not feature.is_enabled:
                    feature.status = "DISABLED"
                elif error:
                    feature.status = "DEPENDENCY_FAILED"
                elif schema and schema.get("required") and not feature.current_data_source_revision_id:
                    feature.status = "WAITING_DATA_SOURCE"
                else:
                    feature.status = "ACTIVE"
                feature.updated_at = now

    def _publish_environment(self, root: Path) -> None:
        if self.script_gid is not None:
            assert self.environments_root is not None
            publish_runtime_environment(self.environments_root, root, self.script_gid)
            return
        if not root.is_dir():
            return
        for path in [root, *root.rglob("*")]:
            try:
                if path.is_dir():
                    os.chmod(path, 0o755)
                else:
                    current = path.stat().st_mode
                    os.chmod(path, 0o755 if current & 0o111 else 0o644)
            except OSError:
                continue
