"""Audit metadata scrubbing — never persist secrets."""

from app.modules.audit.service import _scrub


def test_scrub_redacts_sensitive_keys() -> None:
    cleaned = _scrub(
        {
            "password": "secret",
            "refresh_token": "abc",
            "customer_id": "ok",
            "api_key": "xyz",
        }
    )
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["refresh_token"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["customer_id"] == "ok"
