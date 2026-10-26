import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr


def read_secret(inline: SecretStr | None, path: Path | None, name: str) -> str:
    if inline and inline.get_secret_value().strip():
        return inline.get_secret_value().strip()
    if path:
        value = path.read_text().strip()
        if value:
            return value
    raise ValueError(f"{name} is empty")


def decode_key(value: str, name: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode())
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name} must be URL-safe base64") from error
    if len(key) != 32:
        raise ValueError(f"{name} must decode to exactly 32 bytes")
    return key


class AuditCipher:
    def __init__(self, encryption_key: bytes, lookup_key: bytes, key_id: str = "v1"):
        self.aes = AESGCM(encryption_key)
        self.lookup_key = lookup_key
        self.key_id = key_id

    def encrypt_text(self, value: str | None, *, context: str) -> str | None:
        if value is None:
            return None
        nonce = os.urandom(12)
        ciphertext = self.aes.encrypt(nonce, value.encode(), context.encode())
        encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode()
        return f"{self.key_id}:{encoded}"

    def decrypt_text(self, value: str | None, *, context: str) -> str | None:
        if value is None:
            return None
        key_id, encoded = value.split(":", 1)
        if key_id != self.key_id:
            raise ValueError(f"Unsupported audit encryption key: {key_id}")
        packed = base64.urlsafe_b64decode(encoded.encode())
        return self.aes.decrypt(packed[:12], packed[12:], context.encode()).decode()

    def encrypt_json(self, value: dict | None, *, context: str) -> str | None:
        if value is None:
            return None
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return self.encrypt_text(raw, context=context)

    def decrypt_json(self, value: str | None, *, context: str) -> dict | None:
        raw = self.decrypt_text(value, context=context)
        return json.loads(raw) if raw is not None else None

    def lookup(self, value: str) -> str:
        normalized = value.strip().casefold().encode()
        return hmac.new(self.lookup_key, normalized, hashlib.sha256).hexdigest()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
