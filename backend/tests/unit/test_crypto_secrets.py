"""Envelope encryption for dedicated DSNs."""

import pytest

from app.core.security.crypto import (
    assert_dedicated_dsn_allowed,
    decrypt_secret,
    encrypt_secret,
    is_fernet_token,
)


def test_encrypt_then_decrypt_roundtrip() -> None:
    original = "postgresql+asyncpg://user:secret@db:5432/starserve"
    token = encrypt_secret(original)
    assert token.startswith("gAAAA")
    assert decrypt_secret(token) == original
    assert is_fernet_token(token)


def test_plaintext_postgres_dsn_passes_through_only_when_legacy() -> None:
    dsn = "postgresql+asyncpg://starserve:starserve@localhost:5432/starserve"
    assert decrypt_secret(dsn) == dsn
    with pytest.raises(ValueError):
        decrypt_secret(dsn, require_envelope=True)


def test_dedicated_dsn_host_must_be_allowlisted() -> None:
    assert assert_dedicated_dsn_allowed(
        "postgresql+asyncpg://u:p@localhost:5432/starserve"
    ).startswith("postgresql")
    with pytest.raises(ValueError):
        assert_dedicated_dsn_allowed("postgresql+asyncpg://u:p@evil.example:5432/x")
