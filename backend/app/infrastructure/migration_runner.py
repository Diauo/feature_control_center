from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations(database_path: Path) -> None:
    migration_dir = Path(__file__).with_name("migrations")
    config = Config()
    config.set_main_option("script_location", str(migration_dir))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path.resolve().as_posix()}")
    command.upgrade(config, "head")


def main() -> None:
    parser = argparse.ArgumentParser(description="功能控制中心数据库迁移")
    parser.add_argument("--database", type=Path, required=True)
    arguments = parser.parse_args()
    run_migrations(arguments.database)


if __name__ == "__main__":
    main()
