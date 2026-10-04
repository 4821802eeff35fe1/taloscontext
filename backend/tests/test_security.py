from app.core.security import (
    decrypt_session_string,
    encrypt_session_string,
    hash_password,
    mask_phone,
    verify_password,
)


def test_session_encryption_roundtrip():
    original = "1BVtsOHcBu...fake-telethon-session-string...=="
    encrypted = encrypt_session_string(original)
    assert encrypted != original
    assert decrypt_session_string(encrypted) == original


def test_password_hash_and_verify():
    hashed = hash_password("correct-password")
    assert verify_password("correct-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_mask_phone():
    assert mask_phone("+15551234567") == "+15*******67"
    assert mask_phone("123") == "***"
