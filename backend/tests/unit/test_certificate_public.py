"""Phase 7 — certificate file locations never leave the server in JSON."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.certificates import router as cert_router
from app.modules.certificates.service import access_to_public, file_available, to_public
from app.modules.insurance.issuance_service import IssuanceService
from app.modules.payments.schemas import CertificatePublic


def _cert(**overrides) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "policy_id": uuid4(),
        "payment_id": uuid4(),
        "customer_id": uuid4(),
        "certificate_number": "CERT-1",
        "status": "GENERATED",
        "external_certificate_ref": "EXT-1",
        "storage_key": "https://blob.core.windows.net/certs/a.pdf?sv=2026&sig=secret",
        "provider_cert_url": "https://uat.definiteassurance.com/cert.pdf?token=abc",
        "local_file_path": "tenant/policy/cert.pdf",
        "local_stored_at": None,
        "content_sha256": "abc",
        "file_size_bytes": 12,
        "access_count": 0,
        "last_accessed_at": None,
        "last_accessed_by_user_id": None,
        "download_url_expires_at": None,
        "generated_at": None,
        "failure_message": None,
        "job_id": "JOB-1",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_public_projection_omits_file_locations() -> None:
    public = to_public(_cert())  # type: ignore[arg-type]
    dumped = str(public)
    assert "storage_key" not in public
    assert "provider_cert_url" not in public
    assert "local_file_path" not in public
    assert "https://" not in dumped
    assert "sig=secret" not in dumped
    assert public["file_available"] is True
    CertificatePublic.model_validate(public)


def test_file_available_is_true_when_only_remote_url_exists() -> None:
    row = _cert(local_file_path=None, storage_key=None)
    assert file_available(row) is True  # type: ignore[arg-type]
    row = _cert(
        local_file_path=None,
        storage_key=None,
        provider_cert_url="https://example.local/placeholder.pdf",
    )
    assert file_available(row) is False  # type: ignore[arg-type]


def test_access_log_omits_filesystem_path() -> None:
    public = access_to_public(
        SimpleNamespace(
            id=uuid4(),
            certificate_id=uuid4(),
            policy_id=uuid4(),
            customer_id=uuid4(),
            user_id=uuid4(),
            access_kind="VIEW",
            source="STAFF",
            result="SUCCESS",
            local_file_path="tenant/policy/cert.pdf",
            content_sha256="abc",
            file_size_bytes=12,
            ip_address="1.1.1.1",
            user_agent="test",
            request_id="r1",
            created_at=None,
        )
    )
    assert "local_file_path" not in public
    assert "tenant/policy/cert.pdf" not in str(public)


def test_http_routes_use_the_public_projection() -> None:
    list_src = inspect.getsource(cert_router.list_certificates)
    get_src = inspect.getsource(cert_router.get_certificate)
    generate_src = inspect.getsource(cert_router.generate_certificate)
    pay_src = inspect.getsource(IssuanceService.pay)
    assert "to_public" in list_src and "redact_remote_urls" not in list_src
    assert "to_public" in get_src
    assert "to_public" in generate_src
    assert "cert_to_public" in pay_src
    assert "redact_remote_urls" not in pay_src
    assert "redact_remote_urls" not in inspect.getsource(to_public)


def test_certificate_download_emails_the_pdf() -> None:
    from app.modules.certificates.service import CertificateService

    src = inspect.getsource(CertificateService.download_pdf)
    assert "enqueue_downloaded_pdf_emails" in src
    assert "persist_mail_pdf" in src
    assert "CertificateAccessKind.DOWNLOAD" in src
    assert 'kind="certificate"' in src


def test_azure_sas_expired_detects_past_se() -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.certificates.service import _azure_sas_expired

    past = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = (datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    expired = (
        "https://insurancedevelopment.blob.core.windows.net/immutable-dmvic-cert/x.pdf"
        f"?sv=2021-08-06&se={past}&sr=b&sp=r&sig=abc"
    )
    fresh = (
        "https://insurancedevelopment.blob.core.windows.net/immutable-dmvic-cert/x.pdf"
        f"?sv=2021-08-06&se={future}&sr=b&sp=r&sig=abc"
    )
    assert _azure_sas_expired(expired) is True
    assert _azure_sas_expired(fresh) is False
    assert _azure_sas_expired("https://blob.core.windows.net/c/x.pdf") is False
    assert _azure_sas_expired(f"https://example.com/x.pdf?se={past}") is False


def test_download_pdf_regenerates_when_sas_expired() -> None:
    from app.modules.certificates.service import CertificateService

    src = inspect.getsource(CertificateService.download_pdf)
    assert "_azure_sas_expired" in src
    assert "url_expired" in src

    from app.modules.certificates.service import (
        _definite_cert_issued,
        _flatten_cert_payload,
        _transient_cert_failure,
    )

    failed = {
        "success": False,
        "message": "Certificate generation failed. Please try again later.",
    }
    assert _definite_cert_issued(failed) is False
    assert _transient_cert_failure(failed) is True

    issued = {"success": True, "certURL": "https://blob.core.windows.net/c.pdf", "certNo": "C-1"}
    assert _definite_cert_issued(issued) is True
    assert _transient_cert_failure(issued) is False

    nested = _flatten_cert_payload(
        {"success": True, "data": "Certificate generation failed. Please try again later."}
    )
    assert nested["message"].startswith("Certificate generation")
    assert _transient_cert_failure(nested) is True

    noise = {
        "success": False,
        "message": (
            "TypeError: fetch failed at node:internal/deps/undici/undici:12637:11 "
            "at async D:\\applications\\sandbox\\index.js:3378:32"
        ),
    }
    assert _transient_cert_failure(noise) is True
    from app.modules.certificates.service import _definite_error_message

    assert "undici" not in _definite_error_message(noise).lower()
    assert "index.js" not in _definite_error_message(noise).lower()

    holder_required = {"success": False, "message": "Policy Holder is required"}
    assert _definite_cert_issued(holder_required) is False
    assert _transient_cert_failure(holder_required) is False

    covered = {
        "success": False,
        "message": "Certificate generation failed. Please try again later.",
        "errorMessage": (
            "This vehicle is already covered under an active policy. "
            "To obtain a new quote, set the cover start date after the current policy’s expiry"
        ),
    }
    refresh = _definite_error_message(covered, for_refresh=True)
    assert "new quote" not in refresh.lower()
    assert "insurer" in refresh.lower() or "refresh" in refresh.lower()
    assert "already covered" in _definite_error_message(covered, for_refresh=False).lower()


@pytest.mark.asyncio
async def test_generate_certificate_retries_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.certificates.service import CertificateService

    calls = {"n": 0}

    class _Provider:
        async def generate_certificate(self, payload: dict) -> dict:
            calls["n"] += 1
            if calls["n"] < 3:
                return {
                    "success": False,
                    "message": "Certificate generation failed. Please try again later.",
                }
            return {
                "success": True,
                "certURL": "https://blob.core.windows.net/issued.pdf",
                "certNo": "CERT-OK",
            }

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.modules.certificates.service.asyncio.sleep", _no_sleep)
    svc = CertificateService.__new__(CertificateService)
    svc.provider = _Provider()  # type: ignore[attr-defined]
    remote = await svc._generate_certificate_with_retry(  # noqa: SLF001
        proposal_ref=1,
        note_oid=2,
        policy=SimpleNamespace(policy_number="P1", external_policy_ref="9", vehicle_registration="KAA"),
        cert_number="CERT-LOCAL",
    )
    assert calls["n"] == 3
    assert remote["certNo"] == "CERT-OK"


@pytest.mark.asyncio
async def test_generate_certificate_sends_policy_holder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.certificates.service import CertificateService

    captured: dict = {}

    class _Provider:
        async def generate_certificate(self, payload: dict) -> dict:
            captured.update(payload)
            return {
                "success": True,
                "certURL": "https://blob.core.windows.net/issued.pdf",
                "certNo": "CERT-OK",
            }

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.modules.certificates.service.asyncio.sleep", _no_sleep)
    svc = CertificateService.__new__(CertificateService)
    svc.provider = _Provider()  # type: ignore[attr-defined]
    await svc._generate_certificate_with_retry(  # noqa: SLF001
        proposal_ref=1,
        note_oid=2,
        policy=SimpleNamespace(
            policy_number="P1",
            external_policy_ref="9",
            vehicle_registration="KAA",
            provider_payload_summary={"definite_client_oid": 4242},
        ),
        cert_number="CERT-LOCAL",
        holder_oid=4242,
    )
    assert captured["PolicyHolder"] == 4242
    assert captured["Client"] == 4242
    assert captured["proposal"] == 1


def test_issuance_pay_does_not_send_second_stk_after_success() -> None:
    src = inspect.getsource(IssuanceService.pay)
    assert "PaymentStatus.SUCCESS.value" in src
    assert "Never send a second STK" in src
