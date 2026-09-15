from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.database import Database
from app.infrastructure.models import RunEventModel, RunModel


@dataclass(frozen=True, slots=True)
class PendingEvent:
    occurred_at_ms: int
    level: str
    source: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


def sanitize_message(value: object, max_bytes: int) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        char
        for char in text
        if char in {"\n", "\t"} or not unicodedata.category(char).startswith("C")
    )
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    suffix = "…[日志已截断]"
    room = max(0, max_bytes - len(suffix.encode("utf-8")))
    return encoded[:room].decode("utf-8", errors="ignore") + suffix


def normalize_context(value: object, max_bytes: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": sanitize_message(value, min(max_bytes, 4_096))}
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return {"value": "上下文无法序列化"}
    if len(payload.encode("utf-8")) <= max_bytes:
        return json.loads(payload)
    return {"truncated": True, "preview": sanitize_message(payload, max(128, max_bytes - 128))}


class RunEventWriter:
    def __init__(self, database: Database, *, max_event_bytes: int, max_context_bytes: int) -> None:
        self.database = database
        self.max_event_bytes = max_event_bytes
        self.max_context_bytes = max_context_bytes

    def append(self, request_id: str, events: list[PendingEvent]) -> int:
        if not events:
            with self.database.session() as db:
                run = db.get(RunModel, request_id)
                return run.last_event_sequence if run else 0
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            if run is None:
                return 0
            sequence = run.last_event_sequence
            for event in events:
                sequence += 1
                level = event.level if event.level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO"
                source = event.source if event.source in {"PLATFORM", "SDK", "STDOUT", "STDERR"} else "PLATFORM"
                context = normalize_context(event.context, self.max_context_bytes)
                db.add(
                    RunEventModel(
                        run_request_id=request_id,
                        sequence=sequence,
                        occurred_at_ms=event.occurred_at_ms,
                        level=level,
                        source=source,
                        message=sanitize_message(event.message, self.max_event_bytes),
                        context_json=json.dumps(context, ensure_ascii=False, separators=(",", ":")),
                    )
                )
            run.last_event_sequence = sequence
            return sequence
