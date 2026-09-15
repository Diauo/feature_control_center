from __future__ import annotations

import csv


__meta__ = {
    "name": "交付验收示例",
    "description": "读取客户数据源并逐行输出结构化日志，不访问外部网络",
    "entrypoint": "run",
    "configs": {
        "batch_name": {
            "type": "string",
            "label": "批次名称",
            "description": "显示在执行日志中的业务批次名称",
            "required": True,
            "default": "交付验收",
            "min": 1,
            "max": 80,
        },
        "dry_run": {
            "type": "boolean",
            "label": "演练模式",
            "description": "示例功能只记录该值，不会发起外部请求",
            "required": True,
            "default": True,
        },
    },
    "data_source": {
        "filename": "dataSource.csv",
        "required": True,
        "extensions": [".csv"],
        "description": "UTF-8 CSV 文件，字段为 item_code、quantity、note",
    },
    "report": {
        "title": "交付验收结果",
        "item_label": "商品",
        "columns": [
            {"key": "itemCode", "label": "商品编号", "type": "string"},
            {"key": "quantity", "label": "数量", "type": "string"},
            {"key": "note", "label": "备注", "type": "string"},
        ],
    },
}


def run(ctx) -> None:
    source = ctx.get_data_source_path()
    if source is None:
        raise RuntimeError("本功能必须提供数据源")

    batch_name = ctx.config.get("batch_name")
    dry_run = ctx.config.get("dry_run")
    ctx.log.info("验收任务开始", batchName=batch_name, dryRun=dry_run, requestId=ctx.request_id)

    rows = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {"item_code", "quantity", "note"}
        if not required_fields.issubset(set(reader.fieldnames or [])):
            raise ValueError("数据源缺少 item_code、quantity 或 note 字段")
        rows = list(enumerate(reader, start=2))

    ctx.report.start(expected_total=len(rows))
    processed = 0
    for row_number, row in rows:
        ctx.raise_if_cancelled()
        item_code = (row.get("item_code") or "").strip()
        if not item_code:
            ctx.log.warning("商品编号为空，已跳过", rowNumber=row_number)
            ctx.report.skipped(
                values={
                    "itemCode": "",
                    "quantity": (row.get("quantity") or "").strip(),
                    "note": (row.get("note") or "").strip(),
                },
                reason=f"第 {row_number} 行商品编号为空",
                reason_code="ITEM_CODE_EMPTY",
            )
            continue
        processed += 1
        ctx.log.info(
            "验收商品已处理",
            rowNumber=row_number,
            itemCode=item_code,
            quantity=(row.get("quantity") or "").strip(),
            note=(row.get("note") or "").strip(),
        )
        ctx.report.success(
            values={
                "itemCode": item_code,
                "quantity": (row.get("quantity") or "").strip(),
                "note": (row.get("note") or "").strip(),
            },
            reason="验收数据处理成功",
        )

    ctx.log.info("验收任务完成", processed=processed, requestId=ctx.request_id)
