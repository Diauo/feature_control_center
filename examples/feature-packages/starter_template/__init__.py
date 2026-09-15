from __future__ import annotations

from pathlib import Path


__meta__ = {
    "name": "功能包起步模板",
    "description": "复制此目录后替换名称、配置和业务逻辑",
    "entrypoint": "run",
    "configs": {
        "endpoint": {
            "type": "string",
            "label": "接口地址",
            "description": "目标系统的完整 HTTPS 地址",
            "required": True,
        },
        "api_token": {
            "type": "secret",
            "label": "接口密钥",
            "description": "密钥不会显示在配置列表、日志或执行快照中",
            "required": True,
        },
        "page_size": {
            "type": "integer",
            "label": "分页大小",
            "required": True,
            "default": 100,
            "min": 1,
            "max": 1000,
        },
        "mode": {
            "type": "enum",
            "label": "运行模式",
            "required": True,
            "default": "normal",
            "options": ["normal", "dry-run"],
        },
    },
    "data_source": {
        "filename": "dataSource.txt",
        "required": False,
        "extensions": [".txt"],
        "description": "可选文本数据源；可改成业务需要的任意单文件格式",
    },
    "report": {
        "title": "功能执行结果",
        "item_label": "数据",
        "columns": [
            {"key": "itemCode", "label": "业务编号", "type": "string"},
            {"key": "mode", "label": "运行模式", "type": "string"},
        ],
    },
}


def run(ctx) -> None:
    endpoint = ctx.config.get("endpoint")
    token = ctx.config.get_secret("api_token")
    page_size = ctx.config.get("page_size")
    mode = ctx.config.get("mode")
    source: Path | None = ctx.get_data_source_path()

    ctx.log.info(
        "任务开始",
        requestId=ctx.request_id,
        customerId=ctx.customer_id,
        endpoint=endpoint,
        pageSize=page_size,
        mode=mode,
        hasDataSource=source is not None,
    )

    # 在循环或耗时步骤之间调用，前端“停止”才能尽快结束脚本。
    ctx.raise_if_cancelled()

    # 业务代码在这里使用 token。禁止把 token 放入日志或返回值。
    _ = token
    if source is not None:
        ctx.log.info("已取得本次执行的数据源快照", filename=source.name, bytes=source.stat().st_size)

    ctx.report.start(expected_total=1)
    ctx.report.success(
        values={"itemCode": "DEMO-001", "mode": str(mode)},
        reason="示例业务处理成功",
    )

    ctx.log.info("任务完成", requestId=ctx.request_id)
