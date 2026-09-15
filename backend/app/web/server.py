from __future__ import annotations

import argparse
from pathlib import Path

from waitress import serve

from app.infrastructure.system_logging import configure_system_logging
from app.web.app_factory import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="功能控制中心 Web 服务")
    parser.add_argument("--data-dir", type=Path, default=Path.cwd() / "data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--public-url", default="http://localhost:8080")
    parser.add_argument("--skip-migrations", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_system_logging(args.data_dir, "web")
    app = create_app(
        data_dir=args.data_dir,
        public_url=args.public_url,
        run_database_migrations=not args.skip_migrations,
    )
    # 代理头由 RequestSecurityResolver 按数据库中的可信 CIDR 处理；Waitress 不能先把它们全部删除。
    serve(app, host=args.host, port=args.port, threads=8, clear_untrusted_proxy_headers=False)


if __name__ == "__main__":
    main()
