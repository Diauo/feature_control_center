from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.infrastructure.package_inspector import FeaturePackageInspector, PackageLimits  # noqa: E402


LIMITS = PackageLimits(
    max_package_bytes=52_428_800,
    max_entries=1_000,
    max_entry_bytes=52_428_800,
    max_total_bytes=209_715_200,
    max_compression_ratio=200,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按平台正式规则校验交付功能包")
    parser.add_argument("archive", type=Path, help="客户交付 ZIP")
    return parser.parse_args()


def validate_python_sources(filename: str, content: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        for item in package.infolist():
            if item.is_dir() or not item.filename.endswith(".py"):
                continue
            source = package.read(item).decode("utf-8-sig")
            compile(source, f"{filename}/{item.filename}", "exec")


def verify(delivery_archive: Path) -> list[dict[str, object]]:
    inspector = FeaturePackageInspector()
    results: list[dict[str, object]] = []
    with zipfile.ZipFile(delivery_archive) as delivery:
        members = [item for item in delivery.infolist() if not item.is_dir()]
        package_members = [
            item
            for item in members
            if "/feature-packages/" in item.filename and item.filename.lower().endswith(".zip")
        ]
        if len(package_members) < 3:
            raise RuntimeError("交付包中的功能包数量不足")
        for member in sorted(package_members, key=lambda value: value.filename):
            content = delivery.read(member)
            filename = PurePosixPath(member.filename).name
            inspected = inspector.inspect(filename, content, LIMITS, allowed_formats=("zip",))
            validate_python_sources(filename, content)
            if "OZON库存同步" in filename:
                # 随包默认配置按"免配置"口径交付：凭证以带默认值的 string 字段提供，
                # 校验重点是四个凭证字段必须齐全（类型随交付口径演进，不限定 secret）。
                config_keys = set(inspected.metadata.config_schema)
                required_credentials = {"ME3_app_key", "ME3_secret", "OZON_api_key", "OZON_client_id"}
                missing = sorted(required_credentials - config_keys)
                if missing:
                    raise RuntimeError(f"{filename} 的密钥字段不完整：缺少 {', '.join(missing)}")
                if inspected.default_data_source is None or inspected.default_data_source.filename != "dataSource.xlsx":
                    raise RuntimeError(f"{filename} 没有正确登记默认数据源")
                if len(inspected.requirements_text.splitlines()) != 12:
                    raise RuntimeError(f"{filename} 的依赖锁不完整")
                if "offline" in filename and len(inspected.offline_wheels) != 12:
                    raise RuntimeError(f"{filename} 的离线 wheel 闭包不完整")
            results.append(
                {
                    "filename": filename,
                    "name": inspected.metadata.name,
                    "requirements": len(inspected.requirements_text.splitlines()),
                    "offlineWheels": len(inspected.offline_wheels),
                    "defaultDataSource": (
                        inspected.default_data_source.filename if inspected.default_data_source else None
                    ),
                }
            )
    return results


def main() -> None:
    archive = parse_arguments().archive.resolve()
    for result in verify(archive):
        print(
            f"{result['filename']}：{result['name']}，"
            f"依赖 {result['requirements']}，离线 wheel {result['offlineWheels']}，"
            f"数据源 {result['defaultDataSource'] or '无'}"
        )
    print("功能包平台规则校验通过。")


if __name__ == "__main__":
    main()
