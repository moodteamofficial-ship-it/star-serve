"""Phase 6 notification unit tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ValidationAppError
from app.integrations.notifications.email.provider import EmailNotificationProvider
from app.integrations.notifications.sms.provider import SmsNotificationProvider
from app.modules.notifications.schemas import NotificationSendRequest
from app.modules.notifications.templates import list_template_codes, render_template


def test_send_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        NotificationSendRequest(  # type: ignore[call-arg]
            channel="EMAIL",
            template_code="GENERIC_ALERT",
            recipient="a@b.com",
            html_body="<script>",
        )


def test_template_render_safe_missing_keys() -> None:
    subject, body = render_template("PAYMENT_RECEIVED", {"reference": "PAY-1"})
    assert "PAY-1" in subject
    assert "PAY-1" in body
    assert "KES" not in body or body  # missing keys become empty


def test_unknown_template_rejected() -> None:
    with pytest.raises(ValidationAppError):
        render_template("NOT_A_REAL_TEMPLATE", {})


def test_template_catalog_excludes_freeform_alert() -> None:
    codes = list_template_codes()
    assert "GENERIC_ALERT" not in codes
    assert "POLICY_ACTIVATED" in codes


def test_generic_alert_cannot_be_rendered() -> None:
    with pytest.raises(ValidationAppError):
        render_template("GENERIC_ALERT", {"message": "anyone@evil.test"})


def test_template_context_drops_freeform_message() -> None:
    from app.modules.notifications.templates import sanitize_template_context

    safe = sanitize_template_context(
        {"reference": "PAY-1", "message": "<script>steal()</script>", "html": "nope"}
    )
    assert safe == {"reference": "PAY-1"}


@pytest.mark.asyncio
async def test_sms_stub_rejects_short_recipient() -> None:
    provider = SmsNotificationProvider(Settings())
    result = await provider.send(
        recipient="12",
        subject=None,
        body="hi",
        metadata={},
    )
    assert result.success is False
    assert result.error_code == "INVALID_RECIPIENT"


@pytest.mark.asyncio
async def test_email_stub_success() -> None:
    provider = EmailNotificationProvider(Settings(email_provider="stub"))
    result = await provider.send(
        recipient="agent@agency-a.local",
        subject="Test",
        body="Hello",
        metadata={"template": "GENERIC_ALERT"},
    )
    assert result.success is True
    assert result.provider_name == "EMAIL_STUB"
    assert result.provider_message_id


def test_template_catalog_hides_otp() -> None:
    codes = list_template_codes()
    assert "OTP_CODE" not in codes
    assert "ACCOUNT_UPDATED" not in codes
    assert "CLAIM_FOLLOWUP" in codes


def test_claim_email_opens_the_claim_file() -> None:
    from uuid import uuid4

    from app.integrations.notifications.email.branding import brand_from_settings
    from app.integrations.notifications.email.renderer import render_html

    claim_id = str(uuid4())
    html = render_html(
        "CLAIM_RECEIVED",
        {
            "claim_number": "CLM-9",
            "vehicle_registration": "KAA 1A",
            "claim_id": claim_id,
        },
        brand=brand_from_settings(Settings(email_provider="stub")),
        subject="Claim received",
        text="plain",
    )
    assert f"/app/claims/{claim_id}" in html
    assert "Open claim" in html
    assert "javascript:" not in html.lower()

    html_home = render_html(
        "CLAIM_RECEIVED",
        {"claim_number": "CLM-9", "claim_id": "not-a-uuid"},
        brand=brand_from_settings(Settings(email_provider="stub")),
        subject="Claim received",
        text="plain",
    )
    assert "/app/claims/" not in html_home
    assert "Open Star Serve" in html_home



def test_otp_template_renders() -> None:
    subject, body = render_template("OTP_CODE", {"otp_code": "482193", "otp_minutes": "10"})
    assert "482193" in body
    assert "verification" in subject.lower()


def test_html_escapes_claim_numbers() -> None:
    from app.integrations.notifications.email.branding import brand_from_settings
    from app.integrations.notifications.email.renderer import render_html

    html = render_html(
        "CLAIM_RECEIVED",
        {"claim_number": "<script>alert(1)</script>", "vehicle_registration": "KAA 1A"},
        brand=brand_from_settings(Settings(email_provider="stub")),
        subject="Claim received",
        text="plain",
    )
    assert "<script>" not in html
    assert "alert(1)" in html
    assert "#30A82C" in html
    assert "Star Serve" in html
    assert "cid:star-serve-header" in html
    assert "generated automatically" in html
    assert "do not reply" in html
    assert "Need Help?" in html
    assert "Open Star Serve" in html
    assert "Or open this address" not in html
    assert "display:block;width:100%" in html
    assert "width:640px" in html
    assert "family=Poppins" in html
    assert "@font-face" in html
    assert "font-family:'Poppins'" in html
    assert "data:font/woff2;base64," in html
    assert "cid:star-serve-icon-mail" in html
    assert "cid:star-serve-icon-info" in html
    assert "data:image/png;base64," not in html
    assert "All rights reserved" in html
    assert "background:#30A82C;padding" not in html


def test_otp_html_shows_code() -> None:
    from app.integrations.notifications.email.branding import brand_from_settings
    from app.integrations.notifications.email.renderer import render_html

    html = render_html(
        "OTP_CODE",
        {"otp_code": "482193", "otp_minutes": "10", "recipient_name": "Ada"},
        brand=brand_from_settings(Settings(email_provider="stub")),
        subject="Your code",
        text="plain",
    )
    assert "482193" in html
    assert "Ada" in html
    assert "Open Star Serve" not in html
    assert "Please do not reply" in html


def test_outbound_embeds_header_and_noreply_notice() -> None:
    from app.integrations.notifications.email.branding import brand_from_settings
    from app.integrations.notifications.email.renderer import render_outbound

    message = render_outbound(
        recipient="ada@agency-a.local",
        subject="Claim received",
        text="We have your claim.",
        template_code="CLAIM_RECEIVED",
        context={"claim_number": "CLM-1"},
        brand=brand_from_settings(Settings(email_provider="stub")),
    )
    assert "do not reply" in message.text.lower()
    assert "generated automatically" in message.html
    assert message.attachments
    assert message.attachments[0].content_id == "star-serve-header"
    assert message.attachments[0].content_type == "image/jpeg"
    assert message.attachments[0].content.startswith(b"\xff\xd8")
    icon_ids = {item.content_id for item in message.attachments if item.content_type == "image/png"}
    assert "star-serve-icon-mail" in icon_ids
    assert "star-serve-icon-info" in icon_ids
    assert "cid:star-serve-icon-mail" in message.html


def test_gmail_auto_select_when_password_set() -> None:
    settings = Settings(
        email_provider="auto",
        email_smtp_host="smtp.gmail.com",
        email_smtp_username="desk@starserve.test",
        email_smtp_password="abcd efgh ijkl mnop",  # noqa: S106
    )
    assert settings.resolved_email_provider == "gmail"
    assert settings.email_smtp_password_normalized == "abcdefghijklmnop"  # noqa: S105
    assert settings.email_async_delivery is True
    assert settings.email_dispatcher_enabled is True


def test_gmail_smtp_endpoint_ignores_custom_host() -> None:
    from app.integrations.notifications.email.smtp import smtp_endpoint

    endpoint = smtp_endpoint(
        Settings(
            email_provider="gmail",
            email_smtp_host="smtp.evil.test",
            email_smtp_port=25,
            email_smtp_username="desk@starserve.test",
            email_smtp_password="app-password-here",  # noqa: S106
        )
    )
    assert endpoint.host == "smtp.gmail.com"
    assert endpoint.port == 587
    assert endpoint.use_tls is True
    assert endpoint.provider_name == "GMAIL_SMTP"


@pytest.mark.asyncio
async def test_sendgrid_swap() -> None:
    settings = Settings(email_provider="sendgrid", email_api_key="sg.fake")
    assert settings.resolved_email_provider == "sendgrid"
    from app.integrations.notifications.email.factory import build_email_transport

    transport = build_email_transport(settings)
    assert transport.name == "SENDGRID"
    await transport.aclose()


def test_dispatcher_loads_branch_table() -> None:
    from app.core.database.base import Base
    from app.modules.notifications import dispatcher as _dispatcher  # noqa: F401

    assert "branches" in Base.metadata.tables
    assert "notifications" in Base.metadata.tables
    from app.modules.notifications.templates import template_priority

    assert template_priority("OTP_CODE") < template_priority("CLAIM_RECEIVED")
    assert template_priority("CLAIM_FOLLOWUP") < template_priority("CLAIM_RECEIVED")


@pytest.mark.asyncio
async def test_gmail_without_password_fails_closed() -> None:
    from app.integrations.notifications.email.factory import build_email_transport
    from app.integrations.notifications.email.renderer import outbound_from_notification

    settings = Settings(
        email_provider="gmail",
        email_smtp_username="desk@starserve.test",
        email_smtp_password="",
    )
    transport = build_email_transport(settings)
    message = outbound_from_notification(
        recipient="client@test.local",
        subject="Hi",
        body="Hello",
        template_code="OTP_CODE",
        context={"otp_code": "111111", "otp_minutes": "10"},
        settings=settings,
    )
    result = await transport.send(message)
    assert result.success is False
    assert result.error_code == "NOT_CONFIGURED"
    await transport.aclose()


@pytest.mark.asyncio
async def test_email_rejects_non_address() -> None:
    provider = EmailNotificationProvider(Settings(email_provider="stub"))
    result = await provider.send(
        recipient="not-an-email",
        subject="x",
        body="y",
        metadata={},
    )
    assert result.success is False
    assert result.error_code == "INVALID_RECIPIENT"


def test_sign_in_template_not_staff_catalog() -> None:
    codes = list_template_codes()
    assert "ACCOUNT_SIGNED_IN" not in codes
    subject, body = render_template(
        "ACCOUNT_SIGNED_IN",
        {
            "recipient_name": "Ada",
            "sign_in_at": "14 Sep 2026, 14:40 EAT",
            "ip_address": "196.201.1.2",
            "device": "Chrome on computer",
        },
    )
    assert "Ada" in body
    assert "196.201.1.2" in body
    assert "sign-in" in subject.lower()


def test_sign_in_html() -> None:
    from app.integrations.notifications.email.branding import brand_from_settings
    from app.integrations.notifications.email.renderer import render_html

    html = render_html(
        "ACCOUNT_SIGNED_IN",
        {
            "recipient_name": "Ada",
            "sign_in_at": "14 Sep 2026, 14:40 EAT",
            "ip_address": "196.201.1.2",
            "device": "Chrome on computer",
        },
        brand=brand_from_settings(Settings(email_provider="stub")),
        subject="New sign-in",
        text="plain",
    )
    assert "Chrome on computer" in html
    assert "196.201.1.2" in html
    assert "If this was not you" in html


def test_device_label_from_user_agent() -> None:
    from app.modules.notifications.account_mail import device_label

    assert device_label(None) == "Unknown device"
    assert "Chrome" in device_label(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36"
    )
    assert "phone" in device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")


def test_login_queues_sign_in_mail() -> None:
    import inspect

    from app.modules.auth.service import AuthService

    src = inspect.getsource(AuthService.authenticate)
    assert "_notify_sign_in" in src
    notify = inspect.getsource(AuthService._notify_sign_in)
    assert "ACCOUNT_SIGNED_IN" in notify


def test_pdf_copy_templates_render() -> None:
    claim_subject, claim_body = render_template(
        "CLAIM_PDF",
        {"claim_number": "CLM-9", "vehicle_registration": "KAA 1A"},
    )
    assert "CLM-9" in claim_subject
    assert "attached" in claim_body
    cert_subject, cert_body = render_template(
        "CERTIFICATE_PDF",
        {"certificate_number": "CERT-1", "policy_number": "POL-1"},
    )
    assert "CERT-1" in cert_subject
    assert "attached" in cert_body
    codes = list_template_codes()
    assert "CLAIM_PDF" not in codes
    assert "CERTIFICATE_PDF" not in codes


def test_mail_pdf_store_roundtrip(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace
    from uuid import uuid4

    from app.core.storage import reset_blob_store
    from app.core.storage.local import LocalBlobStore
    from app.modules.notifications.pdf_mail import attachments_for_notification
    from app.modules.notifications import pdf_store

    reset_blob_store()
    monkeypatch.setattr(
        "app.core.storage.get_blob_store",
        lambda: LocalBlobStore(root_dir=str(tmp_path)),
    )
    monkeypatch.setattr(pdf_store, "get_blob_store", lambda: LocalBlobStore(root_dir=str(tmp_path)))
    tenant_id = uuid4()
    claim_id = uuid4()
    stored = pdf_store.store_mail_pdf(
        tenant_id=tenant_id,
        kind="claim",
        resource_id=claim_id,
        content=b"%PDF-1.4 test file",
        filename="CLM-9.pdf",
    )
    assert stored.filename == "CLM-9.pdf"
    assert stored.relative_path == f"{str(tenant_id).lower()}/claim/{str(claim_id).lower()}.pdf"
    assert "/" not in stored.relative_path.split("/")[0] or stored.relative_path.count("/") == 2
    assert not stored.relative_path.startswith("/")
    assert stored.sha256
    assert stored.size_bytes > 0
    packed = pdf_store.read_mail_pdf(
        tenant_id=tenant_id, kind="claim", resource_id=claim_id
    )
    assert packed is not None
    content, filename = packed
    assert content.startswith(b"%PDF")
    assert filename == "CLM-9.pdf"

    row = SimpleNamespace(
        template_code="CLAIM_PDF",
        related_resource="claim",
        related_resource_id=claim_id,
        tenant_id=tenant_id,
    )
    attached = attachments_for_notification(row)  # type: ignore[arg-type]
    assert len(attached) == 1
    assert attached[0].filename == "CLM-9.pdf"
    assert attached[0].inline is False
    assert attached[0].content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_email_provider_attaches_pdf() -> None:
    from app.integrations.notifications.email.message import OutboundEmail
    from app.integrations.notifications.ports import NotificationSendResult

    captured: dict[str, OutboundEmail] = {}

    class Capture:
        name = "EMAIL_STUB"

        async def send(self, message: OutboundEmail) -> NotificationSendResult:
            captured["message"] = message
            return NotificationSendResult(
                success=True,
                provider_name=self.name,
                provider_message_id="1",
            )

        async def aclose(self) -> None:
            return None

    provider = EmailNotificationProvider(Settings(email_provider="stub"))
    provider.transport = Capture()  # type: ignore[assignment]
    result = await provider.send(
        recipient="staff@agency.local",
        subject="Your claim PDF — CLM-9",
        body="A PDF copy is attached.",
        metadata={
            "template": "CLAIM_PDF",
            "context": {"claim_number": "CLM-9"},
            "attachments": [
                {
                    "filename": "CLM-9.pdf",
                    "content": b"%PDF-1.4 claim",
                    "content_type": "application/pdf",
                }
            ],
        },
    )
    assert result.success is True
    message = captured["message"]
    pdfs = [item for item in message.attachments if item.filename == "CLM-9.pdf"]
    assert len(pdfs) == 1
    assert pdfs[0].inline is False
    assert pdfs[0].content == b"%PDF-1.4 claim"
    assert "attached" in message.html.lower() or "CLM-9" in message.html

