from __future__ import annotations


DEFAULT_REPORT_MAX_ITEMS = 60_000
MIN_REPORT_MAX_ITEMS = 1
MAX_REPORT_MAX_ITEMS = 1_000_000


def normalize_report_max_items(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_REPORT_MAX_ITEMS
    return max(MIN_REPORT_MAX_ITEMS, min(MAX_REPORT_MAX_ITEMS, value))
