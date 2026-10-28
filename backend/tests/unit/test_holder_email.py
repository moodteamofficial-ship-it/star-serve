"""Definite LIVE needs the holder email on settle + generateCertificate."""

from types import SimpleNamespace

from app.modules.insurance.provider_fields import extract_holder_email


def test_policy_summary_customer_snapshot_is_used() -> None:
    summary = {"definite_client_oid": 298872, "customer": {"email": " Jane@Example.com "}}
    assert extract_holder_email(None, summary) == "jane@example.com"


def test_live_customer_row_wins_over_snapshot() -> None:
    customer = SimpleNamespace(email="new@example.com")
    summary = {"customer": {"email": "old@example.com"}}
    assert extract_holder_email(customer, summary) == "new@example.com"


def test_flat_customer_email_key_still_supported() -> None:
    assert extract_holder_email({"customer_email": "a@b.co"}) == "a@b.co"


def test_blank_or_invalid_values_are_skipped() -> None:
    customer = SimpleNamespace(email="")
    summary = {"customer_email": "not-an-email", "customer": {"email": "real@x.ke"}}
    assert extract_holder_email(customer, {"email": None}, summary) == "real@x.ke"
    assert extract_holder_email(None, {}, SimpleNamespace(email=None)) is None
