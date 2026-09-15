from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class ValidationError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


_USERNAME_ALLOWED = re.compile(r"^[\w.@+-]+$", re.UNICODE)


def normalize_username(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not 3 <= len(normalized) <= 64:
        raise ValidationError("INVALID_USERNAME", "用户名长度应为 3 到 64 个字符", field="username")
    if not _USERNAME_ALLOWED.fullmatch(normalized):
        raise ValidationError(
            "INVALID_USERNAME",
            "用户名只能包含文字、数字以及 . @ + - _",
            field="username",
        )
    return normalized.casefold()


def clean_display_name(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value).strip()
    if not 1 <= len(cleaned) <= 64:
        raise ValidationError("INVALID_DISPLAY_NAME", "显示名称长度应为 1 到 64 个字符", field="displayName")
    if any(unicodedata.category(char).startswith("C") for char in cleaned):
        raise ValidationError("INVALID_DISPLAY_NAME", "显示名称包含不支持的字符", field="displayName")
    return cleaned


def clean_customer_name(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value).strip()
    if not 1 <= len(cleaned) <= 120:
        raise ValidationError("INVALID_CUSTOMER_NAME", "客户名称长度应为 1 到 120 个字符", field="name")
    if any(unicodedata.category(char).startswith("C") for char in cleaned):
        raise ValidationError("INVALID_CUSTOMER_NAME", "客户名称包含不支持的字符", field="name")
    return cleaned


def parse_role(value: str) -> UserRole:
    try:
        return UserRole(value)
    except ValueError as exc:
        raise ValidationError("INVALID_ROLE", "用户角色无效", field="role") from exc

