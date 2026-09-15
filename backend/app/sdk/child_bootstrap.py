from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import signal
import sys
import traceback
from pathlib import Path

try:
    from .runtime import (
        DEFAULT_REPORT_MAX_ITEMS,
        FeatureCancelled,
        FeatureContext,
        request_cancellation,
    )
except ImportError:  # Copied into the isolated run directory by Runner.
    from _fcc_runtime import (
        DEFAULT_REPORT_MAX_ITEMS,
        FeatureCancelled,
        FeatureContext,
        request_cancellation,
    )


def _handle_termination(_signum, _frame) -> None:
    request_cancellation()


def _load_feature(package_dir: Path):
    entry = package_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "feature_package",
        entry,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载功能入口")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(package_dir))
    spec.loader.exec_module(module)
    return module


async def _invoke(function, context: FeatureContext):
    parameters = list(inspect.signature(function).parameters.values())
    if len(parameters) == 1:
        result = function(context)
    elif len(parameters) == 2:
        result = function(context.legacy_config(), context)
    else:
        raise TypeError("功能入口必须是 run(ctx) 或兼容形式 run(configs, ctx)")
    if inspect.isawaitable(result):
        result = await result
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("Runner 启动参数无效", file=sys.stderr, flush=True)
        return 2
    input_file = Path(sys.argv[1]).resolve()
    payload = json.loads(input_file.read_text(encoding="utf-8"))
    signal.signal(signal.SIGTERM, _handle_termination)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handle_termination)
    context = FeatureContext(
        request_id=payload["requestId"],
        customer_id=payload["customerId"],
        feature_id=payload["customerFeatureId"],
        config=payload["config"],
        secret_keys=set(payload["secretKeys"]),
        data_source_path=payload.get("dataSourcePath"),
        cancel_file=payload["cancelFile"],
        event_token=payload["eventToken"],
        report_schema=payload.get("reportSchema"),
        report_max_items=payload.get("reportMaxItems", DEFAULT_REPORT_MAX_ITEMS),
    )
    try:
        module = _load_feature(Path(payload["packageDir"]).resolve())
        function = getattr(module, payload["entrypoint"], None)
        if not callable(function):
            raise RuntimeError(f"功能入口 {payload['entrypoint']} 不存在或不可调用")
        result = asyncio.run(_invoke(function, context))
        if isinstance(result, tuple) and result and isinstance(result[0], bool):
            message = str(result[1]) if len(result) > 1 else "旧式功能已返回执行结果"
            if result[0]:
                context.log.info(message, legacyResult=True)
            else:
                context.log.error(message, legacyResult=True)
                return 1
        context.report.complete_if_started()
        return 0
    except FeatureCancelled:
        return 20
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
