"""Phase 5 payment / webhook unit tests."""

from decimal import Decimal
from time import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ValidationAppError
from app.integrations.payments.mpesa.provider import MpesaProvider, sign_mpesa_webhook_stub
from app.modules.payments.schemas import PaymentInitiateRequest
from app.modules.payments.service import TERMINAL_STATUSES
from app.modules.payments.enums import PaymentStatus


def test_initiate_request_forbids_client_amount() -> None:
    with pytest.raises(ValidationError):
        PaymentInitiateRequest(  # type: ignore[call-arg]
            policy_id=uuid4(),
            method="MPESA",
            phone="254700000000",
            amount=1,
        )


def test_terminal_statuses() -> None:
    assert PaymentStatus.SUCCESS.value in TERMINAL_STATUSES
    assert PaymentStatus.PENDING.value not in TERMINAL_STATUSES


@pytest.mark.asyncio
async def test_mpesa_requires_phone() -> None:
    provider = MpesaProvider(Settings(mpesa_webhook_secret="test-secret"))
    with pytest.raises(ValidationAppError):
        await provider.initiate(
            reference="PAY-1",
            amount=Decimal("100.00"),
            currency="KES",
            phone=None,
            metadata={},
        )


@pytest.mark.asyncio
async def test_mpesa_webhook_signature() -> None:
    secret = "test-secret"
    provider = MpesaProvider(Settings(mpesa_webhook_secret=secret))
    checkout = "ws_CO_abc"
    amount = "1500.00"
    payload = {
        "CheckoutRequestID": checkout,
        "Amount": amount,
        "ResultCode": "0",
        "MpesaReceiptNumber": "ABC123",
        "AccountReference": "PAY-TEST",
    }
    timestamp = str(int(time()))
    sig = sign_mpesa_webhook_stub(
        checkout_id=checkout,
        amount=amount,
        result_code="0",
        timestamp=timestamp,
        secret=secret,
    )
    ok = await provider.verify_webhook(
        headers={"X-StarServe-Signature": sig, "X-StarServe-Timestamp": timestamp},
        payload=payload,
    )
    assert ok.valid and ok.success
    assert ok.receipt == "ABC123"

    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={"X-StarServe-Signature": "bad"},
            payload=payload,
        )


@pytest.mark.asyncio
async def test_birdview_stub_initiate_and_webhook() -> None:
    from app.integrations.payments.birdview.provider import BirdViewProvider

    settings = Settings(
        birdview_live=False,
        birdview_webhook_secret="bv-secret",
        csrf_secret="unused",
        birdview_test_amount=1,
        app_env="development",
    )
    provider = BirdViewProvider(settings)
    initiated = await provider.initiate(
        reference="PAY-BVTEST",
        amount=Decimal("2049.00"),
        currency="KES",
        phone="254790359782",
        metadata={"policy_number": "POL-1"},
    )
    assert initiated.status == "PENDING"
    assert initiated.provider_checkout_id.startswith("bv_stub_")
    assert initiated.raw.get("stk_amount") == "1.00"

    qs = parse_qs(urlparse(str(initiated.raw["callbackUrl"])).query)
    verified = await provider.verify_webhook(
        headers={},
        payload={
            "ref": "PAY-BVTEST",
            "sig": qs["sig"][0],
            "amt": qs["amt"][0],
            "exp": qs["exp"][0],
            "CheckoutRequestID": initiated.provider_checkout_id,
            "ResultCode": "0",
            "Amount": qs["amt"][0],
            "MpesaReceiptNumber": "BVRECEIPT1",
        },
    )
    assert verified.valid and verified.success
    assert verified.receipt == "BVRECEIPT1"
    assert verified.reference == "PAY-BVTEST"

    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={},
            payload={
                "ref": "PAY-BVTEST",
                "sig": "bad",
                "amt": qs["amt"][0],
                "exp": qs["exp"][0],
                "CheckoutRequestID": initiated.provider_checkout_id,
                "ResultCode": "0",
                "Amount": qs["amt"][0],
            },
        )


def _birdview_signed_callback(secret: str, reference: str, amount: str) -> dict[str, str]:
    from app.integrations.payments.birdview.provider import sign_birdview_callback

    exp = int(time()) + 600
    return {
        "ref": reference,
        "amt": amount,
        "exp": str(exp),
        "sig": sign_birdview_callback(
            reference=reference, amount=amount, exp=exp, secret=secret
        ),
    }


@pytest.mark.asyncio
async def test_birdview_success_requires_a_traceable_receipt() -> None:
    """ResultCode 0 with no M-Pesa receipt is not a settlement."""
    from app.integrations.payments.birdview.provider import BirdViewProvider

    settings = Settings(birdview_webhook_secret="bv-secret", app_env="development")
    provider = BirdViewProvider(settings)
    signed = _birdview_signed_callback("bv-secret", "PAY-NR", "1.00")

    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={},
            payload={**signed, "ResultCode": "0", "Amount": "1.00"},
        )

    # A failure callback needs no receipt.
    failed = await provider.verify_webhook(
        headers={},
        payload={**signed, "ResultCode": "1032", "ResultDesc": "Cancelled"},
    )
    assert failed.valid and not failed.success


@pytest.mark.asyncio
async def test_birdview_result_signature_binds_the_outcome() -> None:
    """The URL token proves nothing about the result, so a bad result sig is fatal."""
    from app.integrations.payments.birdview.provider import (
        BirdViewProvider,
        sign_birdview_result,
    )

    settings = Settings(birdview_webhook_secret="bv-secret", app_env="development")
    provider = BirdViewProvider(settings)
    signed = _birdview_signed_callback("bv-secret", "PAY-RS", "1.00")
    body = {
        **signed,
        "CheckoutRequestID": "bv_1",
        "ResultCode": "0",
        "Amount": "1.00",
        "MpesaReceiptNumber": "BVRECEIPT1",
    }

    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(headers={}, payload={**body, "rsig": "forged"})

    good = sign_birdview_result(
        reference="PAY-RS",
        amount="1.00",
        exp=int(signed["exp"]),
        result_code="0",
        checkout_id="bv_1",
        receipt="BVRECEIPT1",
        secret="bv-secret",
    )
    verified = await provider.verify_webhook(headers={}, payload={**body, "rsig": good})
    assert verified.valid and verified.success


@pytest.mark.asyncio
async def test_birdview_can_require_signed_results() -> None:
    from app.integrations.payments.birdview.provider import BirdViewProvider

    settings = Settings(
        birdview_webhook_secret="bv-secret",
        birdview_result_signature_required=True,
        app_env="development",
    )
    provider = BirdViewProvider(settings)
    signed = _birdview_signed_callback("bv-secret", "PAY-REQ", "1.00")
    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={},
            payload={
                **signed,
                "ResultCode": "0",
                "Amount": "1.00",
                "MpesaReceiptNumber": "BVRECEIPT1",
            },
        )


def test_live_birdview_needs_webhook_secret_and_https_callback() -> None:
    from app.core.config import Settings as S
    from app.main import _assert_production_secrets

    base = {
        "app_env": "production",
        "birdview_live": True,
        "birdview_webhook_secret": "x" * 32,
        "csrf_secret": "y" * 32,
        "encryption_key": "z" * 32,
        "jwt_algorithm": "RS256",
        "database_url": "postgresql+asyncpg://u:p@db.internal:5432/starserve",
        "birdview_callback_base_url": "https://api.example.com",
        "guest_quote_enabled": False,
    }
    _assert_production_secrets(S(**base))

    missing_secret = {**base, "birdview_webhook_secret": ""}
    with pytest.raises(RuntimeError):
        _assert_production_secrets(S(**missing_secret))

    http_callback = {**base, "birdview_callback_base_url": "http://api.example.com"}
    with pytest.raises(RuntimeError):
        _assert_production_secrets(S(**http_callback))


def test_callback_ip_allowlist_matches_addresses_and_cidrs() -> None:
    from app.core.security.request import ip_in_allowlist

    assert ip_in_allowlist("41.90.1.5", "41.90.0.0/16, 10.0.0.1")
    assert ip_in_allowlist("10.0.0.1", "41.90.0.0/16, 10.0.0.1")
    assert not ip_in_allowlist("8.8.8.8", "41.90.0.0/16")
    # An empty allowlist never matches; callers decide what "unset" means.
    assert not ip_in_allowlist("41.90.1.5", "")
    assert not ip_in_allowlist(None, "41.90.0.0/16")


@pytest.mark.asyncio
async def test_birdview_test_amount_ignored_in_production() -> None:
    from app.integrations.payments.birdview.provider import resolve_birdview_charge_amount

    charged = resolve_birdview_charge_amount(
        Settings(app_env="production", birdview_test_amount=1),
        Decimal("100.00"),
    )
    assert charged == Decimal("100.00")


def test_dev_defaults_to_one_shilling_when_unset() -> None:
    from app.modules.payments.dev_charge import resolve_outbound_charge_kes

    charged = resolve_outbound_charge_kes(
        Settings(app_env="development", birdview_test_amount=None),
        Decimal("1949.00"),
    )
    assert charged == Decimal("1.00")


def test_staging_clamps_test_amount_to_one_shilling() -> None:
    from app.modules.payments.dev_charge import resolve_outbound_charge_kes

    charged = resolve_outbound_charge_kes(
        Settings(app_env="staging", birdview_test_amount=500, definite_assurance_test_amount_paid=1949),
        Decimal("1949.00"),
    )
    assert charged == Decimal("1.00")


def test_production_charges_full_premium() -> None:
    from app.modules.payments.dev_charge import resolve_outbound_charge_kes

    charged = resolve_outbound_charge_kes(
        Settings(app_env="production", birdview_test_amount=None),
        Decimal("1949.00"),
    )
    assert charged == Decimal("1949.00")


@pytest.mark.asyncio
async def test_birdview_phone_normalization() -> None:
    from app.integrations.payments.birdview.client import kenya_phone_for_birdview

    assert kenya_phone_for_birdview("+254790359782") == "0790359782"
    assert kenya_phone_for_birdview("0790359782") == "0790359782"


def test_candidate_stk_urls_prefers_resolvable_host() -> None:
    from app.integrations.payments.birdview.client import candidate_stk_urls

    primary = "https://payments.birdviewinsurance.com/mobile-payments/stk-push"
    fallback = "https://payments-ewrv.onrender.com/mobile-payments/stk-push"
    urls = candidate_stk_urls(
        primary,
        fallback=fallback,
        resolves=lambda host: host == "payments-ewrv.onrender.com",
    )
    assert urls[0] == fallback
    assert urls[1] == primary


@pytest.mark.asyncio
async def test_stk_push_retries_fallback_after_dns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.exceptions import ExternalServiceError
    from app.integrations.payments.birdview.client import BirdViewClient

    seen: list[str] = []

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"success": True, "data": {"CheckoutRequestID": "ws_CO_1"}}

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> _FakeResponse:
            seen.append(url)
            if "payments.birdviewinsurance.com" in url:
                raise httpx.ConnectError(
                    "[Errno 8] nodename nor servname provided, or not known",
                    request=httpx.Request("POST", url),
                )
            return _FakeResponse()

    monkeypatch.setattr("app.integrations.payments.birdview.client.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        "app.integrations.payments.birdview.client.candidate_stk_urls",
        lambda primary, fallback=None: [
            "https://payments.birdviewinsurance.com/mobile-payments/stk-push",
            "https://payments-ewrv.onrender.com/mobile-payments/stk-push",
        ],
    )
    client = BirdViewClient(
        Settings(
            birdview_stk_url="https://payments.birdviewinsurance.com/mobile-payments/stk-push",
            birdview_stk_fallback_url="https://payments-ewrv.onrender.com/mobile-payments/stk-push",
        )
    )
    body = await client.stk_push(
        amount=Decimal("1"),
        phone="0790359782",
        transaction_reference="PAY-TEST",
        transaction_description="Premium",
        callback_url="https://example.com/cb",
    )
    assert body["data"]["CheckoutRequestID"] == "ws_CO_1"
    assert seen == [
        "https://payments.birdviewinsurance.com/mobile-payments/stk-push",
        "https://payments-ewrv.onrender.com/mobile-payments/stk-push",
    ]

    class _AlwaysFail(_FakeAsyncClient):
        async def post(self, url: str, **kwargs: object) -> _FakeResponse:
            raise httpx.ConnectError(
                "[Errno 8] nodename nor servname provided, or not known",
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("app.integrations.payments.birdview.client.httpx.AsyncClient", _AlwaysFail)
    with pytest.raises(ExternalServiceError):
        await client.stk_push(
            amount=Decimal("1"),
            phone="0790359782",
            transaction_reference="PAY-TEST",
            transaction_description="Premium",
            callback_url="https://example.com/cb",
        )


@pytest.mark.asyncio
async def test_birdview_production_refuses_csrf_secret_fallback() -> None:
    from app.integrations.payments.birdview.provider import (
        BirdViewProvider,
        build_birdview_callback_url,
    )

    settings = Settings(
        app_env="production",
        birdview_live=False,
        birdview_webhook_secret="",
        csrf_secret="change-me-csrf-dev-only",
        allow_insecure_production=True,
    )
    with pytest.raises(ValidationAppError):
        build_birdview_callback_url(
            reference="PAY-X", amount=Decimal("1.00"), settings=settings
        )

    provider = BirdViewProvider(settings)
    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={},
            payload={"ref": "PAY-X", "sig": "abc", "ResultCode": "0"},
        )


@pytest.mark.asyncio
async def test_birdview_production_requires_result_code() -> None:
    from app.integrations.payments.birdview.provider import (
        BirdViewProvider,
        sign_birdview_callback,
    )

    settings = Settings(
        app_env="production",
        birdview_webhook_secret="bv-secret",
        csrf_secret="unused",
        allow_insecure_production=True,
    )
    provider = BirdViewProvider(settings)
    sig = sign_birdview_callback(
        reference="PAY-X", amount="1.00", exp=int(time()) + 3600, secret="bv-secret"
    )
    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={},
            payload={
                "ref": "PAY-X",
                "sig": sig,
                "amt": "1.00",
                "exp": str(int(time()) + 3600),
                "success": True,
            },
        )


@pytest.mark.asyncio
async def test_mpesa_stub_refused_in_production() -> None:
    provider = MpesaProvider(
        Settings(app_env="production", mpesa_consumer_key="", allow_insecure_production=True)
    )
    with pytest.raises(ValidationAppError):
        await provider.initiate(
            reference="PAY-1",
            amount=Decimal("100.00"),
            currency="KES",
            phone="254700000000",
            metadata={},
        )


def test_certificate_fetch_host_allowlist() -> None:
    from app.modules.certificates.service import certificate_fetch_allowed

    hosts = "definiteassurance.com,blob.core.windows.net"
    assert certificate_fetch_allowed(
        "https://uat.definiteassurance.com/cert.pdf", allowed_hosts=hosts
    )
    assert not certificate_fetch_allowed("http://uat.definiteassurance.com/cert.pdf", allowed_hosts=hosts)
    assert not certificate_fetch_allowed("https://evil.example/cert.pdf", allowed_hosts=hosts)


def test_wallet_top_up_requires_reason() -> None:
    from app.modules.payments.schemas import WalletTopUpRequest

    with pytest.raises(ValidationError):
        WalletTopUpRequest(amount=Decimal("10.00"), currency="KES")
    WalletTopUpRequest(amount=Decimal("10.00"), currency="KES", description="Agency float top-up")


@pytest.mark.asyncio
async def test_wallet_provider_refuses_immediate_success() -> None:
    from app.integrations.payments.wallet.provider import WalletPaymentProvider

    provider = WalletPaymentProvider()
    with pytest.raises(ValidationAppError):
        await provider.initiate(
            reference="PAY-W",
            amount=Decimal("50.00"),
            currency="KES",
            phone=None,
            metadata={},
        )
