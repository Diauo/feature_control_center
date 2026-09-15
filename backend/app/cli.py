from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.application.audit import RequestMetadata, add_audit
from app.infrastructure.database import Database
from app.infrastructure.models import SystemSettingModel


def main() -> None:
    parser = argparse.ArgumentParser(prog="fccctl", description="功能控制中心主机侧恢复工具")
    parser.add_argument("--data-dir", default="/data", help="持久化数据目录")
    subcommands = parser.add_subparsers(dest="command", required=True)
    admin_access = subcommands.add_parser("admin-access", help="管理区访问恢复")
    admin_access.add_argument("action", choices=["reset"])
    arguments = parser.parse_args()
    if arguments.command == "admin-access" and arguments.action == "reset":
        reset_admin_access(Path(arguments.data_dir))


def reset_admin_access(data_dir: Path) -> None:
    database_file = data_dir.resolve() / "fcc.db"
    if not database_file.is_file():
        raise SystemExit(f"数据库不存在：{database_file}")
    database = Database(database_file)
    try:
        database.configure_database()
        now = int(time.time())
        with database.session() as db:
            mode = db.get(SystemSettingModel, "security.management_network_mode")
            cidrs = db.get(SystemSettingModel, "security.management_trusted_cidrs")
            if mode is None or cidrs is None:
                raise SystemExit("数据库尚未包含阶段 B 管理区设置，请先正常启动并完成迁移")
            mode.value_json = json.dumps("ACCOUNT_ONLY")
            cidrs.value_json = json.dumps([])
            mode.updated_at = cidrs.updated_at = now
            mode.updated_by = cidrs.updated_by = None
            add_audit(
                db,
                now=now,
                request=RequestMetadata(client_ip="local-cli", user_agent="fccctl"),
                action="recovery.admin_access.reset",
                outcome="success",
                target_type="system_settings",
                target_id="management_network",
            )
    finally:
        database.dispose()
    print("管理区网络限制已重置为仅账户权限。请登录后重新检查可信代理和 CIDR 设置。")


if __name__ == "__main__":
    main()
