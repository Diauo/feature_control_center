from __future__ import annotations

import argparse
import os
import signal
from pathlib import Path

from app.infrastructure.runtime_permissions import (
    prepare_root_directory,
    prepare_runs_root,
    repair_runtime_cache,
)
from app.infrastructure.system_logging import configure_system_logging
from app.runner.dependencies import DependencyPreparer
from app.runner.materializer import RunMaterializer, ScriptIdentity
from app.runner.worker import RunnerWorker
from app.web.app_factory import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="功能控制中心 Runner")
    parser.add_argument("--data-dir", type=Path, default=Path.cwd() / "data")
    parser.add_argument("--runner-id", default="primary")
    parser.add_argument("--once", action="store_true", help="队列清空后退出，供维护与测试使用")
    parser.add_argument("--skip-migrations", action="store_true", help=argparse.SUPPRESS)
    return parser


def resolve_script_identity() -> ScriptIdentity:
    if os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        return ScriptIdentity()
    try:
        import pwd

        account = pwd.getpwnam("fcc-script")
    except (ImportError, KeyError) as exc:
        raise RuntimeError("以 root 启动 Runner 时必须存在 fcc-script 系统账户") from exc
    return ScriptIdentity(uid=account.pw_uid, gid=account.pw_gid)


def main() -> None:
    args = build_parser().parse_args()
    configure_system_logging(args.data_dir, "runner")
    app = create_app(data_dir=args.data_dir, run_database_migrations=not args.skip_migrations)
    services = app.extensions["fcc_services"]
    builder = app.extensions["fcc_environment_builder"]
    script_identity = resolve_script_identity()
    if script_identity.gid is not None:
        repair_runtime_cache(services.paths.runtime_cache, script_identity.gid)
        prepare_root_directory(services.paths.temp_dir, 0o711)
        prepare_runs_root(services.paths.temp_dir / "runs", script_identity.gid)
    dependency_preparer = DependencyPreparer(
        services.database,
        services.settings,
        services.clock,
        builder,
        script_gid=script_identity.gid,
        environments_root=services.paths.runtime_cache / "environments",
    )
    materializer = RunMaterializer(
        services.database,
        services.paths,
        services.runs.snapshot_cipher,
        script_identity,
    )
    worker = RunnerWorker(
        database=services.database,
        settings=services.settings,
        clock=services.clock,
        materializer=materializer,
        dependency_preparer=dependency_preparer,
        runner_id=args.runner_id,
    )

    def stop(_signum, _frame) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if args.once:
            worker.run_until_idle(timeout_seconds=3_600)
            worker.shutdown()
        else:
            worker.run_forever()
    finally:
        services.database.dispose()


if __name__ == "__main__":
    main()
