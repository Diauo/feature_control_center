from __future__ import annotations

import argparse
from pathlib import Path

from app.web.app_factory import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="功能控制中心版本启动预检")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--skip-migrations", action="store_true")
    arguments = parser.parse_args()
    app = create_app(
        data_dir=arguments.data_dir,
        public_url=arguments.public_url,
        run_database_migrations=not arguments.skip_migrations,
    )
    app.extensions["fcc_services"].database.dispose()


if __name__ == "__main__":
    main()
