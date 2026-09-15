from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|token|authorization|cookie|api[_-]?key|secret)(\s*[=:]\s*)([^\s,;]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _safe_text(value: object, limit: int) -> str:
    text = _CONTROL_PATTERN.sub("", str(value))
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", text)
    return text[:limit]


class DailyJsonLogHandler(logging.Handler):
    """Append one bounded JSON object per line and rotate by UTC calendar day."""

    def __init__(self, root: Path, service: str) -> None:
        super().__init__(logging.INFO)
        self.root = root / service
        self.service = service
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            now = datetime.now(UTC)
            payload: dict[str, Any] = {
                "timestamp": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "service": self.service,
                "level": record.levelname,
                "logger": _safe_text(record.name, 160),
                "message": _safe_text(record.getMessage(), 16_384),
            }
            request_id = getattr(record, "request_id", None)
            if request_id:
                payload["requestId"] = _safe_text(request_id, 64)
            if record.exc_info:
                payload["exception"] = _safe_text(logging.Formatter().formatException(record.exc_info), 32_768)
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            destination = self.root / f"{now:%Y-%m-%d}.jsonl"
            with self._write_lock:
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o660)
                with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line)
        except Exception:
            self.handleError(record)


def configure_system_logging(data_dir: Path, service: str) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    marker = f"fcc:{service}"
    if any(getattr(handler, "fcc_marker", None) == marker for handler in root.handlers):
        return
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    stream.fcc_marker = marker  # type: ignore[attr-defined]
    file_handler = DailyJsonLogHandler(data_dir / "system-logs", service)
    file_handler.fcc_marker = marker  # type: ignore[attr-defined]
    root.addHandler(stream)
    root.addHandler(file_handler)
