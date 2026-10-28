"""Provider-neutral outbound email. Transports must not invent their own shape."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str
    content_id: str | None = None
    inline: bool = False


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    to: str
    subject: str
    text: str
    html: str
    from_name: str
    from_address: str
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    attachments: tuple[EmailAttachment, ...] = ()
    notification_id: str | None = None
    template_code: str | None = None
