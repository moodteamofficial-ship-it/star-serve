"""TextSMS: short payment messages, protected credentials, fast failure mapping."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.integrations.notifications.sms.provider import (
    SmsNotificationProvider,
    to_intl_msisdn,
    to_local_msisdn,
)
from app.modules.notifications.templates import SMS_FOOTER, render_template
from app.modules.payments.service import friendly_failure_reason

_TOKEN = "test-api-key-not-real"  # noqa: S105
_PARTNER = "17560"
_FULL = {
    "recipient_name": "Wanjiku",
    "reference": "PAY-1A2B3C4D5E6F",
    "amount": "7,450.00",
    "currency": "KES",
    "policy_number": "STAR/MPV/2026/000123",
    "vehicle_registration": "KDA 123A",
    "receipt": "TJK4ABCD12",
    "failure_reason": "insufficient M-Pesa balance",
}


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "sms_api_key": _TOKEN,
        "sms_partner_id": _PARTNER,
        "sms_api_url": "https://sms.example.test/api/services/sendsms/",
        "sms_sender_id": "STARSERVE",
        "sms_timeout_seconds": 5.0,
        "is_production": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _provider(handler, **overrides: object) -> SmsNotificationProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SmsNotificationProvider(_settings(**overrides), http_client=client)  # type: ignore[arg-type]


def _ok_payload(message_id: int = 8290842) -> dict:
    return {
        "responses": [
            {
                "respose-code": 200,
                "response-description": "Success",
                "mobile": 254712345678,
                "messageid": message_id,
                "networkid": "1",
            }
        ]
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+254712345678", "0712345678"),
        ("254712345678", "0712345678"),
        ("0712 345 678", "0712345678"),
        ("712345678", "0712345678"),
        ("+254112345678", "0112345678"),
        ("12", None),
        ("+447700900123", None),
        ("", None),
    ],
)
def test_phone_normalised_to_local_format(raw: str, expected: str | None) -> None:
    assert to_local_msisdn(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+254712345678", "254712345678"),
        ("0712345678", "254712345678"),
        ("712345678", "254712345678"),
        ("0112345678", "254112345678"),
        ("12", None),
    ],
)
def test_phone_normalised_to_intl_for_textsms(raw: str, expected: str | None) -> None:
    assert to_intl_msisdn(raw) == expected


@pytest.mark.parametrize("template", ["PAYMENT_RECEIVED", "PAYMENT_FAILED"])
def test_payment_sms_is_short_professional_and_signed(template: str) -> None:
    _, body = render_template(template, _FULL, channel="SMS")
    assert 180 <= len(body) <= 300, len(body)
    assert body.endswith(f"\n{SMS_FOOTER}")
    assert body.startswith("Dear Wanjiku,")
    assert "KES 7,450.00" in body
    assert "{" not in body


def test_payment_sms_never_exceeds_limit_with_long_values() -> None:
    ctx = {**_FULL, "recipient_name": "A" * 120, "policy_number": "P" * 120}
    for template in ("PAYMENT_RECEIVED", "PAYMENT_FAILED"):
        _, body = render_template(template, ctx, channel="SMS")
        assert len(body) <= 300
        assert body.endswith(SMS_FOOTER)


def test_payment_sms_falls_back_when_details_missing() -> None:
    _, body = render_template(
        "PAYMENT_RECEIVED", {"reference": "PAY-1", "amount": "100.00"}, channel="SMS"
    )
    assert body.startswith("Dear Customer,")
    assert "Receipt: PAY-1." in body
    assert "()" not in body


def test_sms_carries_referral_share_link_not_essay() -> None:
    link = "https://quote.starserveinsuranceagency.com/dashboard/#r=SSA2KYNG"
    ctx = {
        **_FULL,
        "referral_link": link,
        "referral_promo": "REFER A FRIEND AND EARN shs 50",
        "referral_note": "Your referral code is SSA2KYNG. Long essay that must not flood SMS.",
    }
    _, sms = render_template("PAYMENT_RECEIVED", ctx, channel="SMS")
    _, email = render_template("PAYMENT_RECEIVED", ctx, channel="EMAIL")
    assert "REFER A FRIEND AND EARN shs 50" in sms
    assert f"Share this link: {link}" in sms
    assert "Long essay" not in sms
    assert "referral code is SSA2KYNG" in email
    assert len(sms) <= 300


@pytest.mark.asyncio
async def test_send_posts_intl_phone_with_textsms_body_and_redacts_raw() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_payload(77))

    result = await _provider(handler).send(
        recipient="+254712345678", subject=None, body="Hello\nFrom Star Serve", metadata={}
    )
    assert result.success is True
    assert result.provider_name == "TEXTSMS"
    assert result.provider_message_id == "77"
    assert seen["body"] == {
        "apikey": _TOKEN,
        "partnerID": _PARTNER,
        "message": "Hello\nFrom Star Serve",
        "shortcode": "STARSERVE",
        "mobile": "254712345678",
    }
    stored = json.dumps(result.raw)
    assert _TOKEN not in stored
    assert "254712345678" not in stored
    assert "0712345678" not in stored


@pytest.mark.asyncio
async def test_canonical_response_code_key_also_succeeds() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "responses": [
                    {
                        "response-code": 200,
                        "response-description": "Success",
                        "messageid": 99,
                    }
                ]
            },
        )

    result = await _provider(handler).send(
        recipient="0712345678", subject=None, body="x", metadata={}
    )
    assert result.success is True
    assert result.provider_message_id == "99"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "AUTH_FAILED"),
        (403, "AUTH_FAILED"),
        (400, "REJECTED"),
        (429, "PROVIDER_UNAVAILABLE"),
        (502, "PROVIDER_UNAVAILABLE"),
    ],
)
async def test_http_errors_map_to_retry_policy(status: int, code: str) -> None:
    result = await _provider(lambda _r: httpx.Response(status, json={})).send(
        recipient="0712345678", subject=None, body="x", metadata={}
    )
    assert result.success is False
    assert result.error_code == code


@pytest.mark.asyncio
async def test_provider_body_failure_is_a_rejection() -> None:
    result = await _provider(
        lambda _r: httpx.Response(
            200,
            json={
                "responses": [
                    {
                        "response-code": 400,
                        "response-description": "Invalid mobile",
                    }
                ]
            },
        )
    ).send(recipient="0712345678", subject=None, body="x", metadata={})
    assert result.success is False
    assert result.error_code == "REJECTED"


@pytest.mark.asyncio
async def test_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    result = await _provider(handler).send(
        recipient="0712345678", subject=None, body="x", metadata={}
    )
    assert result.success is False
    assert result.error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_missing_credentials_in_production_is_not_configured() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    result = await _provider(handler, sms_api_key="").send(
        recipient="0712345678", subject=None, body="x", metadata={}
    )
    assert called is False
    assert result.error_code == "NOT_CONFIGURED"

    result = await _provider(handler, sms_partner_id="").send(
        recipient="0712345678", subject=None, body="x", metadata={}
    )
    assert called is False
    assert result.error_code == "NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_plain_http_url_refused() -> None:
    result = await _provider(
        lambda _r: httpx.Response(200), sms_api_url="http://sms.example.test/x"
    ).send(recipient="0712345678", subject=None, body="x", metadata={})
    assert result.error_code == "NOT_CONFIGURED"


def test_sms_routes_through_background_dispatcher_when_configured() -> None:
    assert "SMS" in Settings(sms_api_key=_TOKEN, sms_partner_id=_PARTNER).dispatcher_channels
    assert "SMS" not in Settings(sms_api_key=_TOKEN, sms_partner_id="").dispatcher_channels
    assert "SMS" not in Settings(sms_api_key="", sms_partner_id=_PARTNER).dispatcher_channels
    assert "SMS" not in Settings(
        sms_api_key=_TOKEN, sms_partner_id=_PARTNER, sms_deliver_inline=True
    ).dispatcher_channels


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        ("1", None, "insufficient M-Pesa balance"),
        ("1032", "Request cancelled by user", "the M-Pesa request was cancelled"),
        ("1037", None, "the M-Pesa prompt timed out"),
        (None, "The balance is insufficient for the transaction", "insufficient M-Pesa balance"),
        ("XYZ", "internal stack trace", "the payment could not be completed"),
    ],
)
def test_failure_reason_is_customer_safe(
    code: str | None, message: str | None, expected: str
) -> None:
    assert friendly_failure_reason(code, message) == expected
