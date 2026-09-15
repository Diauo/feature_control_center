from __future__ import annotations

import time


__meta__ = {
    "name": "实时日志稳定性测试",
    "description": "每隔 0.3 秒输出一条结构化日志，用于验证正常结束、主动停止和页面响应",
    "entrypoint": "run",
    "configs": {
        "log_count": {
            "type": "integer",
            "label": "日志条数",
            "description": "默认运行约 30 秒，范围为 1 到 1000 条",
            "required": True,
            "default": 100,
            "min": 1,
            "max": 1000,
        },
    },
    "report": {
        "title": "实时日志稳定性测试结果",
        "item_label": "测试项",
        "columns": [
            {"key": "testSequence", "label": "测试序号", "type": "integer"},
            {"key": "progress", "label": "进度百分比", "type": "number"},
        ],
    },
}


def run(ctx) -> None:
    total = int(ctx.config.get("log_count", 100))
    ctx.report.start(expected_total=total)
    ctx.log.info("实时日志稳定性测试开始", total=total, intervalSeconds=0.3, requestId=ctx.request_id)

    started_at = time.monotonic()
    for sequence in range(1, total + 1):
        ctx.raise_if_cancelled()
        elapsed = round(time.monotonic() - started_at, 3)
        ctx.log.info(
            "测试日志",
            sequence=sequence,
            total=total,
            progressPercent=round(sequence * 100 / total, 1),
            elapsedSeconds=elapsed,
        )
        ctx.report.success(
            values={"testSequence": sequence, "progress": round(sequence * 100 / total, 1)},
            reason="测试日志已正常输出",
        )
        time.sleep(0.3)
        ctx.raise_if_cancelled()

    ctx.log.info(
        "实时日志稳定性测试完成",
        total=total,
        elapsedSeconds=round(time.monotonic() - started_at, 3),
        requestId=ctx.request_id,
    )
