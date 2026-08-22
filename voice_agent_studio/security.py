from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        raw_salt = base64.urlsafe_b64decode(salt)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), raw_salt, int(iterations))
        return hmac.compare_digest(base64.urlsafe_b64encode(actual).decode(), expected)
    except (ValueError, TypeError):
        return False


def generate_master_key() -> str:
    return Fernet.generate_key().decode()


@dataclass
class Vault:
    key: bytes

    @classmethod
    def from_environment(cls) -> Vault:
        value = os.environ.get("VAS_MASTER_KEY", "")
        key_file = os.environ.get("VAS_MASTER_KEY_FILE", "")
        if key_file:
            try:
                with open(key_file) as source:
                    value = source.read().strip()
            except OSError as exc:
                raise RuntimeError("Unable to read VAS_MASTER_KEY_FILE") from exc
        if not value:
            raise RuntimeError(
                "VAS_MASTER_KEY or VAS_MASTER_KEY_FILE is required; generate one with the CLI"
            )
        try:
            Fernet(value.encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeError("VAS_MASTER_KEY is not a valid Fernet key") from exc
        return cls(value.encode())

    def encrypt(self, value: str) -> bytes:
        return Fernet(self.key).encrypt(value.encode())

    def decrypt(self, value: bytes) -> str:
        try:
            return Fernet(self.key).decrypt(value).decode()
        except InvalidToken as exc:
            raise RuntimeError("Unable to decrypt stored secret") from exc
