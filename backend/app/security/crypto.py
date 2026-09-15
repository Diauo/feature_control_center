from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass


def derive_key(instance_key: bytes, purpose: bytes) -> bytes:
    return hmac.new(instance_key, b"fcc:v1:" + purpose, hashlib.sha256).digest()


def digest_value(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def user_agent_digest(user_agent: str) -> bytes:
    return hashlib.sha256(user_agent.encode("utf-8", errors="replace")).digest()


def generate_opaque_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def generate_temporary_password(length: int = 18) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@dataclass(frozen=True, slots=True)
class SignedCsrfToken:
    value: str
    expires_at: int


class PreAuthCsrf:
    _PAYLOAD_BYTES = 8 + 16

    def __init__(self, instance_key: bytes, ttl_seconds: int = 900) -> None:
        self._key = derive_key(instance_key, b"preauth-csrf")
        self._ttl_seconds = ttl_seconds

    def issue(self, now: int) -> SignedCsrfToken:
        expires_at = now + self._ttl_seconds
        payload = struct.pack(">Q", expires_at) + secrets.token_bytes(16)
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(payload + signature).rstrip(b"=").decode("ascii")
        return SignedCsrfToken(value=token, expires_at=expires_at)

    def validate(self, token: str, now: int) -> bool:
        try:
            padding = "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode(token + padding)
        except (ValueError, TypeError):
            return False
        if len(raw) != self._PAYLOAD_BYTES + 32:
            return False
        payload, supplied_signature = raw[: self._PAYLOAD_BYTES], raw[self._PAYLOAD_BYTES :]
        expected_signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return False
        (expires_at,) = struct.unpack(">Q", payload[:8])
        return now <= expires_at

