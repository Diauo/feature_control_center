from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class MenuKey(StrEnum):
    WORKSPACE = "workspace"
    RUNS = "runs"
    SCHEDULES = "schedules"
    FEATURE_ADMIN = "feature_admin"
    USERS = "users"
    CUSTOMERS = "customers"
    AUDIT = "audit"
    SETTINGS = "settings"


ALL_MENU_KEYS: tuple[str, ...] = tuple(key.value for key in MenuKey)
GRANTABLE_MENU_KEYS: tuple[str, ...] = tuple(
    key.value for key in MenuKey if key is not MenuKey.SETTINGS
)
DEFAULT_OPERATOR_MENUS: tuple[str, ...] = (MenuKey.WORKSPACE.value, MenuKey.RUNS.value)


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


def clean_menu_keys(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError("INVALID_MENU_KEYS", "菜单权限格式无效", field="menuKeys")
    unique: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in GRANTABLE_MENU_KEYS:
            raise ValidationError("INVALID_MENU_KEYS", "菜单权限包含不支持的菜单", field="menuKeys")
        if item not in unique:
            unique.append(item)
    if not unique:
        raise ValidationError("INVALID_MENU_KEYS", "业务员至少需要一个菜单权限", field="menuKeys")
    return unique


def ordered_menu_keys(keys: Iterable[str]) -> list[str]:
    selected = set(keys)
    return [key for key in ALL_MENU_KEYS if key in selected]

