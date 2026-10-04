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


def test_blank_numeric_env_values_fall_back_to_defaults(monkeypatch):
    from decimal import Decimal

    from app.core.config import Settings

    monkeypatch.setenv("TELEGRAM_API_ID", "")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", " ")
    monkeypatch.setenv("TIMEWEB_TEXT_INPUT_RUB_PER_M", "")
    s = Settings(_env_file=None)
    assert s.telegram_api_id == 0
    assert s.trusted_proxy_count == 0
    assert s.timeweb_text_input_rub_per_m == Decimal(270)
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    assert Settings(_env_file=None).telegram_api_id == 12345


def test_production_refuses_example_placeholders():
    import pytest

    from app.core.config import Settings

    s = Settings(_env_file=None, APP_ENV="production", APP_SECRET_KEY="dev-only-insecure-change-me",
                 TELETHON_SESSION_ENCRYPTION_KEY="x" * 40)
    with pytest.raises(RuntimeError, match="placeholder"):
        s.validate_production()
    s = Settings(_env_file=None, APP_ENV="production", APP_SECRET_KEY="y" * 40, TELETHON_SESSION_ENCRYPTION_KEY="")
    with pytest.raises(RuntimeError, match="TELETHON_SESSION_ENCRYPTION_KEY must be set"):
        s.validate_production()
    Settings(_env_file=None, APP_ENV="production", APP_SECRET_KEY="y" * 40,
             TELETHON_SESSION_ENCRYPTION_KEY="z" * 40).validate_production()


async def test_missing_encryption_key_is_a_clear_503(client, monkeypatch):
    from app.core.config import get_settings
    from tests.conftest import register

    ws = await register(client, "nokey@example.com")
    monkeypatch.setattr(get_settings(), "telethon_session_encryption_key", "")
    r = await client.post(f"/api/v1/workspaces/{ws}/telegram/auth/start", json={"phone": "+15550009999"})
    assert r.status_code == 503
    assert "TELETHON_SESSION_ENCRYPTION_KEY" in r.json()["detail"]
