from __future__ import annotations

import json
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.security.crypto import derive_key


class RunSnapshotCipherError(RuntimeError):
    pass


class RunSnapshotCipher:
    """Encrypt the immutable per-run configuration with request-scoped AAD."""

    _VERSION = b"\x01"
    _NONCE_BYTES = 12

    def __init__(self, instance_key: bytes) -> None:
        self._key = derive_key(instance_key, b"run-config-snapshot-v1")

    def encrypt(self, request_id: str, values: dict[str, Any]) -> bytes:
        plaintext = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        nonce = secrets.token_bytes(self._NONCE_BYTES)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, self._aad(request_id))
        return self._VERSION + nonce + ciphertext

    def decrypt(self, request_id: str, payload: bytes) -> dict[str, Any]:
        if len(payload) < 1 + self._NONCE_BYTES + 16 or payload[:1] != self._VERSION:
            raise RunSnapshotCipherError("运行配置快照格式无效")
        nonce = payload[1 : 1 + self._NONCE_BYTES]
        ciphertext = payload[1 + self._NONCE_BYTES :]
        try:
            value = json.loads(AESGCM(self._key).decrypt(nonce, ciphertext, self._aad(request_id)))
        except (InvalidTag, UnicodeDecodeError, ValueError, TypeError) as exc:
            raise RunSnapshotCipherError("运行配置快照无法解密或已被篡改") from exc
        if not isinstance(value, dict):
            raise RunSnapshotCipherError("运行配置快照内容无效")
        return value

    @staticmethod
    def _aad(request_id: str) -> bytes:
        return f"fcc:run:{request_id}".encode("ascii")
