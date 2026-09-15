from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.domain.identity import ValidationError


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        self._dummy_hash = self._hasher.hash("not-a-real-password-value")

    @staticmethod
    def validate(password: str) -> None:
        if len(password) < 12:
            raise ValidationError("PASSWORD_TOO_SHORT", "密码至少需要 12 个字符", field="password")
        if len(password) > 256 or len(password.encode("utf-8")) > 1024:
            raise ValidationError("PASSWORD_TOO_LONG", "密码过长", field="password")
        if password.isspace():
            raise ValidationError("PASSWORD_INVALID", "密码不能全部为空白字符", field="password")

    def hash(self, password: str) -> str:
        self.validate(password)
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        if self._oversized(password):
            self.verify_unknown_user("")
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def verify_unknown_user(self, password: str) -> None:
        candidate = "" if self._oversized(password) else password
        try:
            self._hasher.verify(self._dummy_hash, candidate)
        except (VerifyMismatchError, InvalidHashError):
            pass

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True

    @staticmethod
    def _oversized(password: str) -> bool:
        return len(password) > 256 or len(password.encode("utf-8", errors="replace")) > 1024
