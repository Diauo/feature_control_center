from __future__ import annotations

import argparse
import signal
from pathlib import Path

from app.scheduler.worker import SchedulerWorker
from app.infrastructure.system_logging import configure_system_logging
from app.web.app_factory import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="功能控制中心 Scheduler")
    parser.add_argument("--data-dir", type=Path, default=Path.cwd() / "data")
    parser.add_argument("--scheduler-id", default="primary")
    parser.add_argument("--once", action="store_true", help="处理当前到期任务后退出")
    parser.add_argument("--skip-migrations", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_system_logging(args.data_dir, "scheduler")
    app = create_app(data_dir=args.data_dir, run_database_migrations=not args.skip_migrations)
    services = app.extensions["fcc_services"]
    worker = SchedulerWorker(
        database=services.database,
        settings=services.settings,
        schedules=services.schedules,
        clock=services.clock,
        scheduler_id=args.scheduler_id,
    )

    def stop(_signum, _frame) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if args.once:
            worker.tick()
        else:
            worker.run_forever()
    finally:
        worker.shutdown()
        services.database.dispose()


if __name__ == "__main__":
    main()
