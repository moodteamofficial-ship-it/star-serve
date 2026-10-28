"""Build RFC 5322 MIME for SMTP and ESPs. Keep this free of provider SDKs."""

from __future__ import annotations

from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.integrations.notifications.email.message import OutboundEmail


def build_mime(message: OutboundEmail) -> EmailMessage:
    msg = EmailMessage()
    display = (message.from_name or "Star Serve").strip()
    mailbox = (message.from_address or "").strip()
    msg["From"] = str(Address(display_name=display, addr_spec=mailbox)) if mailbox else display
    msg["To"] = message.to.strip()
    msg["Subject"] = (message.subject or "Star Serve").strip()[:256]
    msg["Date"] = formatdate(localtime=False)
    domain = mailbox.split("@")[-1] if "@" in mailbox else "starserve.local"
    msg["Message-ID"] = make_msgid(idstring=(message.notification_id or None), domain=domain)
    if message.reply_to:
        msg["Reply-To"] = message.reply_to
    msg["X-StarServe-Template"] = (message.template_code or "")[:64]
    if message.notification_id:
        msg["X-StarServe-Notification"] = message.notification_id
    for key, value in message.headers.items():
        if key.lower() in {"from", "to", "subject", "date", "message-id"}:
            continue
        msg[key] = value

    msg.set_content(message.text or "")
    if message.html:
        msg.add_alternative(message.html, subtype="html")

    html_part = msg.get_body(preferencelist=("html",))
    related = html_part if html_part is not None else msg
    for item in message.attachments:
        maintype, _, subtype = (item.content_type or "application/octet-stream").partition("/")
        if item.inline and item.content_id and html_part is not None:
            related.add_related(
                item.content,
                maintype=maintype or "image",
                subtype=subtype or "png",
                cid=item.content_id,
                filename=item.filename,
            )
        else:
            msg.add_attachment(
                item.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=item.filename,
            )
    return msg
