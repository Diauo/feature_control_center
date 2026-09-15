from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.domain.identity import ValidationError
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CustomerFeatureDataSourceRevisionModel,
    FeatureVersionModel,
    RunModel,
    RuntimeEnvironmentModel,
)
from app.infrastructure.paths import AppPaths
from app.infrastructure.package_inspector import extract_feature_package
from app.infrastructure.runtime_permissions import RuntimePermissionError, prepare_runs_root
from app.security.run_snapshot_cipher import RunSnapshotCipher


class RunMaterializationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScriptIdentity:
    uid: int | None = None
    gid: int | None = None


@dataclass(frozen=True, slots=True)
class PreparedRun:
    request_id: str
    work_dir: Path
    package_dir: Path
    input_file: Path
    cancel_file: Path
    python_executable: Path
    event_token: str
    report_schema: dict[str, object] | None
    report_max_items: int


class RunMaterializer:
    def __init__(
        self,
        database: Database,
        paths: AppPaths,
        snapshot_cipher: RunSnapshotCipher,
        script_identity: ScriptIdentity,
    ) -> None:
        self.database = database
        self.paths = paths
        self.snapshot_cipher = snapshot_cipher
        self.script_identity = script_identity
        self.runs_root = paths.temp_dir.resolve() / "runs"

    def prepare(self, request_id: str, event_token: str, report_max_items: int) -> PreparedRun:
        with self.database.session() as db:
            run = db.scalar(
                select(RunModel)
                .options(undefer(RunModel.config_snapshot_ciphertext))
                .where(RunModel.request_id == request_id)
            )
            if run is None:
                raise RunMaterializationError("任务记录不存在")
            version = db.scalar(
                select(FeatureVersionModel)
                .options(undefer(FeatureVersionModel.package_blob))
                .where(FeatureVersionModel.id == run.feature_version_id)
            )
            if version is None or version.status != "READY":
                raise RunMaterializationError("任务快照引用的功能版本不可用")
            if hashlib.sha256(version.package_blob).digest() != version.package_sha256:
                raise RunMaterializationError("功能包内容校验失败")
            data_source = None
            if run.data_source_revision_id:
                data_source = db.scalar(
                    select(CustomerFeatureDataSourceRevisionModel)
                    .options(undefer(CustomerFeatureDataSourceRevisionModel.content))
                    .where(CustomerFeatureDataSourceRevisionModel.id == run.data_source_revision_id)
                )
                if data_source is None or data_source.customer_feature_id != run.customer_feature_id:
                    raise RunMaterializationError("任务快照引用的数据源不存在")
                if hashlib.sha256(data_source.content).digest() != data_source.sha256:
                    raise RunMaterializationError("数据源内容校验失败")
            environment_path = None
            if version.runtime_environment_id:
                environment = db.get(RuntimeEnvironmentModel, version.runtime_environment_id)
                if environment is None or environment.status != "READY" or not environment.environment_path:
                    raise RunMaterializationError("功能依赖环境不可用")
                environment_path = environment.environment_path
            config = self.snapshot_cipher.decrypt(request_id, run.config_snapshot_ciphertext)
            secret_keys = json.loads(run.secret_keys_json)
            data_schema = json.loads(version.data_source_schema_json) if version.data_source_schema_json else None
            metadata = json.loads(version.metadata_json)
            report_schema = metadata.get("report") if isinstance(metadata, dict) else None
            package_blob = bytes(version.package_blob)
            package_filename = version.package_filename
            entrypoint = version.entrypoint
            customer_id = run.customer_id
            customer_feature_id = run.customer_feature_id

        self._prepare_runs_root()
        work_dir = (self.runs_root / request_id).resolve()
        if work_dir.parent != self.runs_root:
            raise RunMaterializationError("任务工作目录无效")
        if work_dir.exists():
            shutil.rmtree(work_dir)
        package_dir = work_dir / "package"
        package_dir.mkdir(parents=True, mode=0o700)
        try:
            extract_feature_package(package_filename, package_blob, package_dir)
        except ValidationError as exc:
            raise RunMaterializationError("功能包已经损坏或包含不安全内容") from exc

        data_source_path: Path | None = None
        if data_source is not None:
            if not data_schema or not isinstance(data_schema.get("filename"), str):
                raise RunMaterializationError("数据源路径声明缺失")
            data_source_path = self._safe_target(package_dir, data_schema["filename"])
            data_source_path.parent.mkdir(parents=True, exist_ok=True)
            data_source_path.write_bytes(data_source.content)

        runtime_source = Path(__file__).parents[1] / "sdk" / "runtime.py"
        bootstrap_source = Path(__file__).parents[1] / "sdk" / "child_bootstrap.py"
        runtime_file = work_dir / "_fcc_runtime.py"
        bootstrap_file = work_dir / "_fcc_bootstrap.py"
        shutil.copyfile(runtime_source, runtime_file)
        shutil.copyfile(bootstrap_source, bootstrap_file)
        legacy_util = work_dir / "app" / "util"
        legacy_util.mkdir(parents=True)
        (work_dir / "app" / "__init__.py").write_text("", encoding="utf-8")
        (legacy_util / "__init__.py").write_text("", encoding="utf-8")
        (legacy_util / "feature_execution_context.py").write_text(
            "from _fcc_runtime import FeatureContext as FeatureExecutionContext\n",
            encoding="utf-8",
            newline="\n",
        )
        sdk_shim = work_dir / "app" / "sdk"
        sdk_shim.mkdir()
        (sdk_shim / "__init__.py").write_text(
            "from _fcc_runtime import FeatureCancelled, FeatureContext\n"
            "__all__ = ['FeatureCancelled', 'FeatureContext']\n",
            encoding="utf-8",
            newline="\n",
        )
        cancel_file = work_dir / "cancel.requested"
        input_file = work_dir / "input.json"
        input_file.write_text(
            json.dumps(
                {
                    "requestId": request_id,
                    "customerId": customer_id,
                    "customerFeatureId": customer_feature_id,
                    "entrypoint": entrypoint,
                    "config": config,
                    "secretKeys": secret_keys,
                    "packageDir": str(package_dir),
                    "dataSourcePath": str(data_source_path) if data_source_path else None,
                    "cancelFile": str(cancel_file),
                    "eventToken": event_token,
                    "reportSchema": report_schema,
                    "reportMaxItems": report_max_items,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
            newline="\n",
        )
        (work_dir / "home").mkdir(exist_ok=True)
        (work_dir / "tmp").mkdir(exist_ok=True)

        python_executable = self._python_executable(environment_path)
        self._secure_tree(work_dir)
        return PreparedRun(
            request_id=request_id,
            work_dir=work_dir,
            package_dir=package_dir,
            input_file=input_file,
            cancel_file=cancel_file,
            python_executable=python_executable,
            event_token=event_token,
            report_schema=report_schema,
            report_max_items=report_max_items,
        )

    def cleanup(self, prepared: PreparedRun) -> None:
        shutil.rmtree(prepared.work_dir, ignore_errors=True)

    def _prepare_runs_root(self) -> None:
        if self.script_identity.gid is None:
            self.runs_root.mkdir(parents=True, exist_ok=True)
            return
        try:
            prepare_runs_root(self.runs_root, self.script_identity.gid)
        except RuntimePermissionError as exc:
            raise RunMaterializationError("无法准备任务工作目录权限") from exc

    @staticmethod
    def _safe_target(root: Path, relative: str) -> Path:
        parts = PurePosixPath(relative).parts
        destination = (root / Path(*parts)).resolve()
        if not destination.is_relative_to(root.resolve()):
            raise RunMaterializationError("数据源声明路径越界")
        return destination

    def _python_executable(self, environment_path: str | None) -> Path:
        if not environment_path:
            return Path(sys.executable).resolve()
        environment = Path(environment_path).resolve()
        allowed_root = (self.paths.runtime_cache / "environments").resolve()
        if not environment.is_relative_to(allowed_root):
            raise RunMaterializationError("依赖环境路径不在平台缓存目录内")
        executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not executable.is_file():
            raise RunMaterializationError("依赖环境的 Python 解释器不存在")
        return executable

    def _secure_tree(self, root: Path) -> None:
        for path in [root, *root.rglob("*")]:
            try:
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
                if self.script_identity.uid is not None and self.script_identity.gid is not None:
                    os.chown(path, self.script_identity.uid, self.script_identity.gid)
            except OSError as exc:
                raise RunMaterializationError("无法设置任务工作目录权限") from exc
