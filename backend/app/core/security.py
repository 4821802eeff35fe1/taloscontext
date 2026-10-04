"""Password hashing and Telethon session string encryption.

Never log raw values passed to these functions — see core/logging.py for the
structlog redaction processor that backs this up at the log layer.
"""
from __future__ import annotations

import base64
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw_password)
    except VerifyMismatchError:
        return False


class EncryptionKeyMissingError(RuntimeError):
    """Raised instead of handling Telegram secrets without an encryption key."""


def _fernet() -> Fernet:
    key = get_settings().telethon_session_encryption_key
    if not key:
        raise EncryptionKeyMissingError(
            "Telegram session encryption is not configured: set TELETHON_SESSION_ENCRYPTION_KEY "
            "in .env and restart the API, worker and scheduler."
        )
    # Accept either a raw passphrase or an already-valid Fernet key.
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_session_string(session_string: str) -> str:
    return _fernet().encrypt(session_string.encode("utf-8")).decode("utf-8")


def decrypt_session_string(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt Telegram session — key mismatch or corrupt data") from exc


def mask_phone(phone: str) -> str:
    digits = phone.strip()
    if len(digits) <= 4:
        return "*" * len(digits)
    return digits[:3] + "*" * (len(digits) - 5) + digits[-2:]
