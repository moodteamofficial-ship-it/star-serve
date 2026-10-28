"""Agent kit mail: branded copy, QR card inline + attached, multi-channel, never blocks."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.integrations.notifications.email.branding import brand_from_settings
from app.integrations.notifications.email.mime import build_mime
from app.integrations.notifications.email.provider import _extra_attachments
from app.integrations.notifications.email.renderer import AGENT_QR_CID, render_outbound
from app.modules.intermediaries.agent_qr import (
    agent_qr_filename,
    agent_qr_url,
    build_agent_qr_card_png,
)
from app.modules.notifications.pdf_mail import attachments_for_notification, attachments_metadata
from app.modules.notifications.templates import render_template

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _row(context: dict, *, template: str = "AGENT_APPROVED") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        template_code=template,
        context_json=context,
        related_resource="intermediary",
        related_resource_id=uuid4(),
        tenant_id=uuid4(),
    )


def test_qr_card_is_a_png_with_the_welcome_link() -> None:
    png = build_agent_qr_card_png(agent_name="Lawrence Larry", agent_code="101180")
    assert png.startswith(PNG_MAGIC)
    assert agent_qr_url("101180").endswith("/#a=101180")
    assert agent_qr_filename("101180") == "StarServe-Agent-QR-101180.png"


def test_qr_url_never_points_at_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.intermediaries import agent_qr

    monkeypatch.setattr(
        agent_qr, "get_settings", lambda: SimpleNamespace(email_app_url="http://localhost:5173")
    )
    assert agent_qr.agent_qr_url("101180").startswith(
        "https://quote.starserveinsuranceagency.com/dashboard/#a="
    )


def test_registered_template_has_clear_instructions_without_dashes() -> None:
    subject, body = render_template(
        "AGENT_REGISTERED",
        {
            "recipient_name": "Lawrence Larry",
            "agent_code": "101180",
            "agent_link": "https://quote.starserveinsuranceagency.com/dashboard/#a=101180",
        },
    )
    assert "101180" in subject
    assert "Lawrence Larry" in body
    assert "How to use your agent code:" in body
    assert "Share your personal link" in body
    assert "#a=101180" in body
    assert "—" not in body
    assert " - " not in body


def test_registered_sms_is_short_with_code_and_link() -> None:
    _, body = render_template(
        "AGENT_REGISTERED",
        {
            "recipient_name": "Wanjiku",
            "agent_code": "101180",
            "agent_link": "https://quote.starserveinsuranceagency.com/dashboard/#a=101180",
        },
        channel="SMS",
    )
    assert "101180" in body
    assert "#a=101180" in body
    assert len(body) <= 300
    assert body.endswith("From Star Serve")
    assert "—" not in body


def test_template_renders_code_and_link() -> None:
    subject, body = render_template(
        "AGENT_APPROVED",
        {
            "recipient_name": "Lawrence Larry",
            "agent_code": "101180",
            "agent_link": "https://quote.starserveinsuranceagency.com/dashboard/#a=101180",
        },
    )
    assert "approved" in subject.lower()
    assert "Lawrence Larry" in body
    assert "#a=101180" in body
    assert "—" not in body


@pytest.mark.parametrize("template", ["AGENT_REGISTERED", "AGENT_APPROVED"])
def test_attachments_inline_and_downloadable(template: str) -> None:
    items = attachments_for_notification(
        _row({"recipient_name": "Lawrence Larry", "agent_code": "101180"}, template=template)
    )
    assert [item.inline for item in items] == [True, False]
    assert items[0].content_id == AGENT_QR_CID
    assert all(item.content.startswith(PNG_MAGIC) for item in items)
    assert all(item.filename == "StarServe-Agent-QR-101180.png" for item in items)


def test_no_agent_code_means_no_attachment() -> None:
    assert attachments_for_notification(_row({"recipient_name": "X"})) == []


def test_html_shows_qr_inline_and_mime_embeds_it() -> None:
    link = "https://quote.starserveinsuranceagency.com/dashboard/#a=101180"
    row = _row({"recipient_name": "Lawrence Larry", "agent_code": "101180"}, template="AGENT_REGISTERED")
    extra = _extra_attachments(attachments_metadata(row))
    message = render_outbound(
        recipient="agent@example.com",
        subject="Your kit",
        text="plain",
        template_code="AGENT_REGISTERED",
        context={"recipient_name": "Lawrence Larry", "agent_code": "101180", "agent_link": link},
        brand=brand_from_settings(Settings(email_provider="stub")),
        extra_attachments=extra,
    )
    assert f"cid:{AGENT_QR_CID}" in message.html
    assert link in message.html
    assert "Open your referral link" in message.html
    assert "How to use your agent code" in message.html
    mime = build_mime(message).as_string()
    assert f"Content-ID: {AGENT_QR_CID}" in mime
    assert 'attachment; filename="StarServe-Agent-QR-101180.png"' in mime


def test_foreign_agent_link_is_not_rendered_as_a_button() -> None:
    message = render_outbound(
        recipient="agent@example.com",
        subject="Approved",
        text="plain",
        template_code="AGENT_APPROVED",
        context={"agent_code": "101180", "agent_link": "https://evil.example/#a=101180"},
        brand=brand_from_settings(Settings(email_provider="stub")),
    )
    assert "evil.example" not in message.html
    assert "Open your referral link" not in message.html


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_register_queues_enabled_channels_and_survives_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.intermediaries.service import IntermediaryService
    from app.modules.notifications import service as notif_service
    from app.modules.system_config import service as cfg_service

    sent: list[dict] = []

    class FakeNotify:
        def __init__(self, session, ctx) -> None:
            pass

        async def enqueue_transactional(self, **kwargs):
            sent.append(kwargs)

    class FakeCfg:
        def __init__(self, session) -> None:
            pass

        async def outbound_allowed(self, channel: str, *, live: bool = True) -> bool:
            return channel in {"EMAIL", "SMS"}

    monkeypatch.setattr(notif_service, "NotificationService", FakeNotify)
    monkeypatch.setattr(cfg_service, "SystemConfigService", FakeCfg)
    svc = IntermediaryService.__new__(IntermediaryService)
    svc.session = SimpleNamespace(begin_nested=lambda: _Nested())
    svc.ctx = SimpleNamespace(tenant_id=uuid4())

    async def _agency_ctx():
        return svc.ctx

    svc._agency_ctx = _agency_ctx  # type: ignore[method-assign]
    row = SimpleNamespace(
        id=uuid4(),
        name="Lawrence Larry",
        email="agent@example.com",
        phone="254700715792",
        agent_code="101180",
        branch_id=None,
    )
    await svc._notify_agent_kit(row, template_code="AGENT_REGISTERED")
    channels = {item["channel"] for item in sent}
    assert channels == {"EMAIL", "SMS"}
    assert all(item["template_code"] == "AGENT_REGISTERED" for item in sent)
    assert all(item["context"]["agent_link"].endswith("#a=101180") for item in sent)
    assert not any(item["channel"] == "WHATSAPP" for item in sent)

    class Boom(FakeNotify):
        async def enqueue_transactional(self, **kwargs):
            raise RuntimeError("smtp down")

    monkeypatch.setattr(notif_service, "NotificationService", Boom)
    await svc._notify_agent_kit(row, template_code="AGENT_REGISTERED")  # must not raise


@pytest.mark.asyncio
async def test_available_kit_channels_only_enabled_with_recipient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.intermediaries.service import IntermediaryService
    from app.modules.system_config import service as cfg_service

    class FakeCfg:
        def __init__(self, session) -> None:
            pass

        async def outbound_allowed(self, channel: str, *, live: bool = True) -> bool:
            return channel in {"EMAIL", "WHATSAPP"}

    monkeypatch.setattr(cfg_service, "SystemConfigService", FakeCfg)
    svc = IntermediaryService.__new__(IntermediaryService)
    svc.session = SimpleNamespace()
    row = SimpleNamespace(
        email="agent@example.com",
        phone="254700715792",
    )
    assert await svc._available_kit_channels(row) == ["EMAIL", "WHATSAPP"]

    row_no_phone = SimpleNamespace(email="agent@example.com", phone="")
    assert await svc._available_kit_channels(row_no_phone) == ["EMAIL"]


@pytest.mark.asyncio
async def test_approval_queues_email_and_survives_mail_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.intermediaries.service import IntermediaryService
    from app.modules.notifications import service as notif_service
    from app.modules.system_config import service as cfg_service

    sent: list[dict] = []

    class FakeNotify:
        def __init__(self, session, ctx) -> None:
            pass

        async def enqueue_transactional(self, **kwargs):
            sent.append(kwargs)

    class FakeCfg:
        def __init__(self, session) -> None:
            pass

        async def outbound_allowed(self, channel: str, *, live: bool = True) -> bool:
            return channel == "EMAIL"

    monkeypatch.setattr(notif_service, "NotificationService", FakeNotify)
    monkeypatch.setattr(cfg_service, "SystemConfigService", FakeCfg)
    svc = IntermediaryService.__new__(IntermediaryService)
    svc.session = SimpleNamespace(begin_nested=lambda: _Nested())
    svc.ctx = SimpleNamespace(tenant_id=uuid4())

    async def _agency_ctx():
        return svc.ctx

    svc._agency_ctx = _agency_ctx  # type: ignore[method-assign]
    row = SimpleNamespace(
        id=uuid4(),
        name="Lawrence Larry",
        email="agent@example.com",
        phone="",
        agent_code="101180",
        branch_id=None,
    )
    await svc._notify_agent_kit(row, template_code="AGENT_APPROVED")
    assert sent and sent[0]["template_code"] == "AGENT_APPROVED"
    assert sent[0]["recipient"] == "agent@example.com"
    assert sent[0]["context"]["agent_link"].endswith("#a=101180")

    class Boom(FakeNotify):
        async def enqueue_transactional(self, **kwargs):
            raise RuntimeError("smtp down")

    monkeypatch.setattr(notif_service, "NotificationService", Boom)
    await svc._notify_agent_kit(row, template_code="AGENT_APPROVED")  # must not raise
