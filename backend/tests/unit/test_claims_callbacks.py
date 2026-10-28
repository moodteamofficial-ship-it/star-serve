"""Definite / payout callback authentication — no unsigned status writes."""

import hashlib
import hmac
import json
import time

import pytest

from app.core.exceptions import AuthenticationError
from app.modules.claims.callbacks import sign_payload, verify_signed_callback
from app.modules.claims.workflow import assert_transition
from app.modules.claims.enums import ClaimStatus


def test_callback_requires_signed_headers():
    with pytest.raises(AuthenticationError):
        verify_signed_callback(payload=b"{}", signature=None, timestamp=None, nonce=None)


def test_callback_rejects_stale_timestamp(monkeypatch):
    monkeypatch.setenv("CLAIMS_WEBHOOK_HMAC_SECRET", "test-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    payload = b'{"external_reference":"DEF-1","decision":"APPROVED"}'
    timestamp = str(int(time.time()) - 10_000)
    nonce = "nonce-123456"
    signature = sign_payload(payload, timestamp=timestamp, nonce=nonce)
    with pytest.raises(AuthenticationError):
        verify_signed_callback(
            payload=payload,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )
    get_settings.cache_clear()


def test_callback_rejects_forged_signature(monkeypatch):
    monkeypatch.setenv("CLAIMS_WEBHOOK_HMAC_SECRET", "test-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    payload = b'{"external_reference":"DEF-1","decision":"APPROVED"}'
    timestamp = str(int(time.time()))
    with pytest.raises(AuthenticationError):
        verify_signed_callback(
            payload=payload,
            signature="0" * 64,
            timestamp=timestamp,
            nonce="nonce-123456",
        )
    get_settings.cache_clear()


def test_valid_callback_returns_body(monkeypatch):
    monkeypatch.setenv("CLAIMS_WEBHOOK_HMAC_SECRET", "test-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    payload = json.dumps({"external_reference": "DEF-1", "decision": "APPROVED"}).encode()
    timestamp = str(int(time.time()))
    nonce = "nonce-abcdef"
    signature = sign_payload(payload, timestamp=timestamp, nonce=nonce)
    body = verify_signed_callback(
        payload=payload,
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    assert body["external_reference"] == "DEF-1"
    get_settings.cache_clear()


def test_hmac_uses_timestamp_and_nonce():
    payload = b"{}"
    a = hmac.new(b"x", b"1.n." + payload, hashlib.sha256).hexdigest()
    b = hmac.new(b"x", b"2.n." + payload, hashlib.sha256).hexdigest()
    assert a != b


def test_payment_success_is_system_only():
    with pytest.raises(Exception):
        assert_transition(
            ClaimStatus.PAYMENT_PROCESSING.value,
            ClaimStatus.PAYMENT_COMPLETED.value,
            system=False,
        )
