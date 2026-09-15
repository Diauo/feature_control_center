from __future__ import annotations

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.security.crypto import derive_key


class ConfigCipherError(RuntimeError):
    pass


class ConfigCipher:
    """Encrypt customer secrets while binding ciphertext to its owner and key."""

    _VERSION = b"\x01"

    def __init__(self, instance_key: bytes) -> None:
        self._cipher = AESGCM(derive_key(instance_key, b"feature-config-aesgcm-v1"))

    def encrypt(self, customer_feature_id: str, config_key: str, plaintext: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return self._VERSION + nonce + self._cipher.encrypt(nonce, plaintext, self._aad(customer_feature_id, config_key))

    def decrypt(self, customer_feature_id: str, config_key: str, ciphertext: bytes) -> bytes:
        if len(ciphertext) < 30 or ciphertext[:1] != self._VERSION:
            raise ConfigCipherError("配置密文格式无效")
        nonce = ciphertext[1:13]
        try:
            return self._cipher.decrypt(nonce, ciphertext[13:], self._aad(customer_feature_id, config_key))
        except InvalidTag as exc:
            raise ConfigCipherError("配置密文无法验证，实例密钥或记录归属可能不匹配") from exc

    @staticmethod
    def _aad(customer_feature_id: str, config_key: str) -> bytes:
        return f"fcc-config-v1\0{customer_feature_id}\0{config_key}".encode("utf-8")
