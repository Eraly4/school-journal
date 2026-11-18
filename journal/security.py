"""Защита приложения: безопасное хранение паролей (PBKDF2-SHA256 + соль)."""
import hashlib
import hmac
import os

ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$", 1)
    except ValueError:
        return False
    expected = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(expected, stored)
