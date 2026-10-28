"""Branded HTML + plaintext for transactional mail.

Values are escaped. Templates are data, not a string-format of raw HTML, so a
placeholder can never break out of the layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any
from uuid import UUID

from app.integrations.notifications.email.branding import EmailBrand, brand_from_settings
from app.integrations.notifications.email.fonts import poppins_font_face_css
from app.integrations.notifications.email.icons import ICON_KINDS, icon_cid, icon_png
from app.integrations.notifications.email.message import EmailAttachment, OutboundEmail
from app.modules.notifications.templates import sanitize_template_context


@dataclass(frozen=True, slots=True)
class EmailCopy:
    preheader: str
    eyebrow: str
    title: str
    intro: str
    fields: tuple[tuple[str, str], ...]
    footnote: str
    otp: bool = False
    agent: bool = False


# Inline image id for the approval email's QR card (attached by the notification layer).
AGENT_QR_CID = "star-serve-agent-qr"

_COPY: dict[str, EmailCopy] = {
    "OTP_CODE": EmailCopy(
        preheader="Your Star Serve verification code",
        eyebrow="Security",
        title="Your verification code",
        intro="Use this code to continue. It expires shortly and should not be shared with anyone.",
        fields=(("Expires", "otp_minutes"),),
        footnote="Star Serve will never ask for this code by phone or WhatsApp.",
        otp=True,
    ),
    "OTP_LOGIN": EmailCopy(
        preheader="Your Star Serve sign-in code",
        eyebrow="Sign in",
        title="Your sign-in code",
        intro="Use this code to finish signing in. It expires shortly.",
        fields=(("Expires", "otp_minutes"),),
        footnote="If you did not try to sign in, you can ignore this email.",
        otp=True,
    ),
    "OTP_VERIFY": EmailCopy(
        preheader="Confirm your Star Serve account",
        eyebrow="Verify account",
        title="Confirm it is you",
        intro="Enter this code to verify your account. It expires shortly.",
        fields=(("Expires", "otp_minutes"),),
        footnote="Star Serve will never ask for this code by phone or WhatsApp.",
        otp=True,
    ),
    "PAYMENT_RECEIVED": EmailCopy(
        preheader="We received your premium payment",
        eyebrow="Payment",
        title="Payment received",
        intro="Thank you. Your premium payment has been recorded.",
        fields=(
            ("Reference", "reference"),
            ("Amount", "amount_line"),
            ("Policy", "policy_number"),
            ("Receipt", "receipt"),
        ),
        footnote="Keep this note for your records.",
    ),
    "POLICY_ACTIVATED": EmailCopy(
        preheader="Your cover is now active",
        eyebrow="Policy",
        title="Your policy is active",
        intro="Cover is in force. Drive with the documents your agency issued.",
        fields=(
            ("Policy", "policy_number"),
            ("Vehicle", "vehicle_registration"),
            ("Cover", "cover_window"),
            ("Your referral code", "referral_code"),
            ("Share link", "referral_link"),
            ("Refer and save", "referral_offer"),
            ("Referral credit", "referral_credit"),
        ),
        footnote="Questions about cover? Reply to this email or contact your agency.",
    ),
    "CERTIFICATE_READY": EmailCopy(
        preheader="Your certificate is ready",
        eyebrow="Certificate",
        title="Certificate ready",
        intro="Your insurance certificate has been issued.",
        fields=(
            ("Certificate", "certificate_number"),
            ("Policy", "policy_number"),
            ("External ref", "external_certificate_ref"),
        ),
        footnote="Carry a copy as required by law.",
    ),
    "CERTIFICATE_PDF": EmailCopy(
        preheader="Your certificate PDF is attached",
        eyebrow="Certificate",
        title="Certificate PDF",
        intro="A PDF copy of this insurance certificate is attached to this email.",
        fields=(
            ("Certificate", "certificate_number"),
            ("Policy", "policy_number"),
            ("Vehicle", "vehicle_registration"),
        ),
        footnote="Carry a copy as required by law.",
    ),
    "PROPOSAL_APPROVED": EmailCopy(
        preheader="Your proposal was approved",
        eyebrow="Quote",
        title="Proposal approved",
        intro="Your proposal has been approved. Complete payment to activate cover.",
        fields=(
            ("Vehicle", "vehicle_registration"),
            ("Product", "product_code"),
            ("Premium", "gross_premium"),
        ),
        footnote="This is not a policy until payment is received.",
    ),
    "CLAIM_RECEIVED": EmailCopy(
        preheader="We have your claim",
        eyebrow="Claim",
        title="We have received your claim",
        intro="Your file is with the claims desk. We will write again as it moves.",
        fields=(
            ("Claim", "claim_number"),
            ("Vehicle", "vehicle_registration"),
            ("Note", "detail"),
        ),
        footnote="Keep your claim number handy when you call.",
    ),
    "CLAIM_UNDER_REVIEW": EmailCopy(
        preheader="Your claim is under review",
        eyebrow="Claim",
        title="Under review",
        intro="An assessor is reviewing your claim.",
        fields=(("Claim", "claim_number"),),
        footnote="You do not need to do anything unless we ask.",
    ),
    "CLAIM_INFORMATION_REQUIRED": EmailCopy(
        preheader="We need a little more to continue your claim",
        eyebrow="Claim",
        title="More information needed",
        intro="We cannot continue this claim until we have the items below.",
        fields=(
            ("Claim", "claim_number"),
            ("Needed", "detail"),
        ),
        footnote="Reply through your agency or the claims desk as soon as you can.",
    ),
    "CLAIM_FOLLOWUP": EmailCopy(
        preheader="A follow-up on your claim",
        eyebrow="Claim",
        title="Follow-up on your claim",
        intro="There is an open follow-up on your file.",
        fields=(
            ("Claim", "claim_number"),
            ("Subject", "followup_subject"),
            ("Due", "due_at"),
            ("Note", "detail"),
        ),
        footnote="Your agency is here if anything is unclear.",
    ),
    "CLAIM_VETTING_PASSED": EmailCopy(
        preheader="Your claim passed internal review",
        eyebrow="Claim",
        title="Internal review passed",
        intro="Your claim has passed our internal review.",
        fields=(("Claim", "claim_number"),),
        footnote="The next step is with the insurer where required.",
    ),
    "CLAIM_FORWARDED": EmailCopy(
        preheader="Your claim was sent to the insurer",
        eyebrow="Claim",
        title="Sent to the insurer",
        intro="Your claim has been forwarded to the insurer for a decision.",
        fields=(("Claim", "claim_number"),),
        footnote="Timelines depend on the insurer. We will write when there is news.",
    ),
    "CLAIM_APPROVED": EmailCopy(
        preheader="Your claim was approved",
        eyebrow="Claim",
        title="Claim approved",
        intro="Good news — this claim has been approved.",
        fields=(
            ("Claim", "claim_number"),
            ("Amount", "amount_line"),
        ),
        footnote="Payment follows the terms of the policy and any excess.",
    ),
    "CLAIM_REJECTED": EmailCopy(
        preheader="An update on your claim",
        eyebrow="Claim",
        title="Claim update",
        intro="This claim was not approved. Your agency can walk you through the decision.",
        fields=(("Claim", "claim_number"),),
        footnote="You may still have options. Speak to your agency.",
    ),
    "CLAIM_PAYMENT_INITIATED": EmailCopy(
        preheader="A claim payment has been started",
        eyebrow="Claim",
        title="Payment started",
        intro="A payment for this claim has been initiated.",
        fields=(
            ("Claim", "claim_number"),
            ("Amount", "amount_line"),
        ),
        footnote="Bank and mobile-money rails can take a short while to settle.",
    ),
    "CLAIM_PAYMENT_COMPLETED": EmailCopy(
        preheader="Your claim payment has been completed",
        eyebrow="Claim",
        title="Payment completed",
        intro="The payment for this claim has been completed.",
        fields=(
            ("Claim", "claim_number"),
            ("Amount", "amount_line"),
        ),
        footnote="If you do not see the funds, contact your agency with the claim number.",
    ),
    "CLAIM_CLIENT_MESSAGE": EmailCopy(
        preheader="A new note on your claim",
        eyebrow="Claim",
        title="New update on your claim",
        intro="There is a new update on your claim file.",
        fields=(
            ("Claim", "claim_number"),
            ("Note", "detail"),
        ),
        footnote="Contact your agency if you need the full conversation.",
    ),
    "CLAIM_PDF": EmailCopy(
        preheader="Your claim PDF is attached",
        eyebrow="Claim",
        title="Claim PDF",
        intro="A PDF copy of this claim file is attached to this email.",
        fields=(
            ("Claim", "claim_number"),
            ("Vehicle", "vehicle_registration"),
        ),
        footnote="Keep your claim number handy when you call.",
    ),
    "ACCOUNT_UPDATED": EmailCopy(
        preheader="Your Star Serve account was updated",
        eyebrow="Account",
        title="Account updated",
        intro="A change was saved on your Star Serve account.",
        fields=(
            ("Account", "recipient_name"),
            ("What changed", "detail"),
        ),
        footnote="If you did not expect this, contact your administrator immediately.",
    ),
    "ACCOUNT_PASSWORD_CHANGED": EmailCopy(
        preheader="Your Star Serve password was changed",
        eyebrow="Security",
        title="Password changed",
        intro="The password on this account was changed. You can ignore this if it was you.",
        fields=(("Account", "recipient_name"),),
        footnote="If this was not you, reset the password and tell your administrator.",
    ),
    "ACCOUNT_STATUS_CHANGED": EmailCopy(
        preheader="Your Star Serve account status changed",
        eyebrow="Account",
        title="Account status changed",
        intro="The status of this Star Serve account was updated.",
        fields=(
            ("Account", "recipient_name"),
            ("Status", "status"),
        ),
        footnote="Contact your administrator if you need access restored.",
    ),
    "ACCOUNT_SIGNED_IN": EmailCopy(
        preheader="New sign-in to your Star Serve account",
        eyebrow="Security",
        title="New sign-in",
        intro=(
            "Someone just signed in to your Star Serve account. "
            "If this was you, no action is needed."
        ),
        fields=(
            ("When", "sign_in_at"),
            ("Device", "device"),
            ("IP address", "ip_address"),
        ),
        footnote=(
            "If this was not you, change your password and tell your administrator "
            "straight away."
        ),
    ),
    "AGENT_REGISTERED": EmailCopy(
        preheader="Your Star Serve agent code, QR card, and referral link",
        eyebrow="Agent",
        title="Your agent kit is ready",
        intro=(
            "Welcome to Star Serve. Below is your personal QR card and referral link. "
            "Share them so customers get a quote with your agent code already applied. "
            "The link and QR go live once your account is approved."
        ),
        fields=(
            ("Agent", "recipient_name"),
            ("Agent code", "agent_code"),
        ),
        footnote=(
            "How to use your agent code: share your personal link, show or print your QR card, "
            "or tell customers the code to enter when they buy cover. "
            "Your QR card is also attached so you can save or print it."
        ),
        agent=True,
    ),
    "AGENT_APPROVED": EmailCopy(
        preheader="Your Star Serve agent account is approved",
        eyebrow="Agent",
        title="You are approved",
        intro=(
            "Your Star Serve agent account is approved. Sign in with your email and password. "
            "Keep sharing your personal link and QR card so customers quote under your code."
        ),
        fields=(
            ("Agent", "recipient_name"),
            ("Agent code", "agent_code"),
        ),
        footnote=(
            "Your personal referral link and QR card are included again so you have them handy."
        ),
        agent=True,
    ),
    "CUSTOMER_REFERRAL_KIT": EmailCopy(
        preheader="Your Star Serve referral code, QR card, and share link",
        eyebrow="Referral",
        title="Your referral kit is ready",
        intro=(
            "Share the QR card and link below with a friend. When they get a quote and pay for "
            "cover, you earn credit off your next Star Serve cover."
        ),
        fields=(
            ("Name", "recipient_name"),
            ("Referral code", "referral_code"),
        ),
        footnote=(
            "How to use your referral code: share your personal link, show or print your QR card, "
            "or tell a friend the code to enter when they buy cover. "
            "Your QR card is also attached so you can save or print it."
        ),
        agent=True,
    ),
}


def render_outbound(
    *,
    recipient: str,
    subject: str,
    text: str,
    template_code: str | None,
    context: dict[str, Any] | None,
    brand: EmailBrand,
    notification_id: str | None = None,
    extra_attachments: tuple[EmailAttachment, ...] | list[EmailAttachment] = (),
) -> OutboundEmail:
    safe = sanitize_template_context(context)
    _enrich(safe)
    html = render_html(template_code or "", safe, brand=brand, subject=subject, text=text)
    notice = (
        "This message was generated automatically. Please do not reply — "
        "this mailbox is not monitored."
    )
    full_text = f"{text.rstrip()}\n\n{notice}" if text.strip() else notice
    attachments: list[EmailAttachment] = []
    if brand.header_bytes and not brand.header_url:
        attachments.append(
            EmailAttachment(
                filename="star-serve-email-header.jpg",
                content=brand.header_bytes,
                content_type="image/jpeg",
                content_id=brand.header_cid,
                inline=True,
            )
        )
    elif brand.logo_bytes and not brand.logo_url:
        attachments.append(
            EmailAttachment(
                filename="star-serve-logo.png",
                content=brand.logo_bytes,
                content_type="image/png",
                content_id=brand.logo_cid,
                inline=True,
            )
        )
    for kind in ICON_KINDS:
        attachments.append(
            EmailAttachment(
                filename=f"star-serve-icon-{kind}.png",
                content=icon_png(kind),
                content_type="image/png",
                content_id=icon_cid(kind),
                inline=True,
            )
        )
    for item in extra_attachments:
        attachments.append(item)
    return OutboundEmail(
        to=recipient,
        subject=subject,
        text=full_text,
        html=html,
        from_name=brand.from_name,
        from_address=brand.from_address,
        reply_to=brand.reply_to,
        attachments=tuple(attachments),
        notification_id=notification_id,
        template_code=template_code,
    )


def render_html(
    template_code: str,
    context: dict[str, str],
    *,
    brand: EmailBrand,
    subject: str,
    text: str,
) -> str:
    copy = _COPY.get(template_code.upper())
    if copy is None:
        copy = EmailCopy(
            preheader=subject or "Star Serve",
            eyebrow="Update",
            title=subject or "Star Serve",
            intro=text or "There is an update on your Star Serve account.",
            fields=(),
            footnote="This is a service message from Star Serve.",
        )
    inner = _body(copy, context, brand)
    return _shell(inner, brand=brand, preheader=copy.preheader)


def _enrich(safe: dict[str, str]) -> None:
    amount = (safe.get("amount") or "").strip()
    currency = (safe.get("currency") or "").strip()
    if amount and currency:
        safe["amount_line"] = f"{currency} {amount}"
    elif amount:
        safe["amount_line"] = amount
    start = (safe.get("cover_start_date") or "").strip()
    end = (safe.get("cover_end_date") or "").strip()
    if start and end:
        safe["cover_window"] = f"{start} – {end}"
    elif start or end:
        safe["cover_window"] = start or end
    minutes = (safe.get("otp_minutes") or "").strip()
    if minutes and minutes.isdigit():
        n = int(minutes)
        safe["otp_minutes"] = f"{n} minute" if n == 1 else f"{n} minutes"


def _type(brand: EmailBrand, extra: str = "") -> str:
    return (
        f"font-family:{brand.font_stack};"
        "mso-generic-font-family:swiss;mso-font-alt:Arial;"
        f"{extra}"
    )


def _icon_well(brand: EmailBrand, kind: str) -> str:
    src = f"cid:{icon_cid(kind)}"
    return (
        f"<td width=\"32\" valign=\"middle\" style=\"width:32px;padding:0 10px 0 0;"
        f"{_type(brand)}\">"
        f"<img src=\"{src}\" width=\"32\" height=\"32\" alt=\"\" "
        "style=\"display:block;border:0;outline:none;text-decoration:none;"
        "width:32px;height:32px;\" />"
        "</td>"
    )


def _body(copy: EmailCopy, context: dict[str, str], brand: EmailBrand) -> str:
    greeting = context.get("recipient_name") or ""
    hello = f"Hello {escape(greeting)}," if greeting else "Hello,"
    rows: list[str] = []
    values = [
        (label, (context.get(key) or "").strip())
        for label, key in copy.fields
        if (context.get(key) or "").strip()
    ]
    for index, (label, value) in enumerate(values):
        pad = "padding:0 0 12px;" if index < len(values) - 1 else "padding:0;"
        rows.append(
            "<tr>"
            f"<td style=\"{pad}color:{brand.muted};font-size:11px;line-height:1.45;"
            f"width:34%;vertical-align:top;{_type(brand)}\">{escape(label)}</td>"
            f"<td style=\"{pad}color:{brand.ink};font-size:13px;line-height:1.45;"
            f"font-weight:600;{_type(brand)}\">{escape(value)}</td>"
            "</tr>"
        )
    facts = ""
    if rows and not copy.otp:
        facts = (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"margin:8px 0 28px;\">"
            f"{''.join(rows)}</table>"
        )
    if copy.otp:
        hero = _otp_block(context, brand)
    elif copy.agent:
        hero = _agent_block(brand, context)
    else:
        hero = _cta_block(brand, context)
    notice = _security_notice(copy, brand)
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        "<tr><td align=\"center\" style=\"padding:8px 0 6px;\">"
        f"<h1 style=\"margin:0;color:{brand.ink};font-size:18px;line-height:1.3;"
        f"font-weight:700;{_type(brand)}\">{escape(copy.title)}</h1>"
        "</td></tr>"
        "<tr><td align=\"center\" style=\"padding:0 0 20px;\">"
        f"<p style=\"margin:0;color:{brand.muted};font-size:12px;line-height:1.5;"
        f"{_type(brand)}\">A service message from {escape(brand.product_name)}</p>"
        "</td></tr></table>"
        f"<p style=\"margin:0 0 10px;color:{brand.ink};font-size:13px;line-height:1.6;"
        f"{_type(brand)}\">{hello}</p>"
        f"<p style=\"margin:0 0 20px;color:{brand.ink};font-size:13px;line-height:1.6;"
        f"{_type(brand)}\">{escape(copy.intro)}</p>"
        f"{hero}{facts}{notice}"
    )


def _otp_block(context: dict[str, str], brand: EmailBrand) -> str:
    code = (context.get("otp_code") or "").strip()
    expires = (context.get("otp_minutes") or "").strip()
    hint = f"Expires in {escape(expires)}." if expires else ""
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"margin:0 0 28px;\"><tr><td align=\"center\">"
        f"<p style=\"margin:0 0 10px;color:{brand.muted};font-size:11px;{_type(brand)}\">"
        "Enter this code to continue</p>"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\">"
        f"<tr><td align=\"center\" bgcolor=\"{brand.green}\" "
        f"style=\"background:{brand.green};border-radius:{brand.radius_sm};"
        f"padding:12px 28px;{_type(brand)}\">"
        f"<span style=\"font-size:18px;letter-spacing:0.24em;font-weight:700;color:{brand.white};"
        f"{_type(brand)}\">"
        f"{escape(code) if code else '••••••'}</span>"
        "</td></tr></table>"
        f"<p style=\"margin:10px 0 0;color:{brand.muted};font-size:11px;line-height:1.5;"
        f"{_type(brand)}\">{hint}</p>"
        "</td></tr></table>"
    )


def _claim_app_url(brand: EmailBrand, context: dict[str, str]) -> tuple[str, str]:
    """Deep-link staff to the claim file. Invalid ids fall back to the app home."""
    base = (brand.app_url or "").rstrip("/")
    raw = (context.get("claim_id") or "").strip()
    try:
        claim_id = str(UUID(raw))
    except (ValueError, TypeError):
        return base, "Open Star Serve"
    return f"{base}/app/claims/{claim_id}", "Open claim"


def _cta_block(brand: EmailBrand, context: dict[str, str]) -> str:
    href, label = _claim_app_url(brand, context)
    url = escape(href, quote=True)
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"margin:4px 0 28px;\"><tr><td>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        "<tr><td align=\"center\" width=\"100%\" "
        f"bgcolor=\"{brand.green}\" "
        f"style=\"width:100%;background:{brand.green};border-radius:{brand.radius_sm};"
        f"{_type(brand)}\">"
        f"<a href=\"{url}\" target=\"_blank\" "
        f"style=\"display:block;width:100%;box-sizing:border-box;background:{brand.green};"
        f"color:{brand.white};font-size:13px;font-weight:600;line-height:1;"
        f"text-align:center;text-decoration:none;border-radius:{brand.radius_sm};"
        f"padding:14px 22px;{_type(brand)}\">{escape(label)}</a>"
        "</td></tr></table>"
        "</td></tr></table>"
    )


def _agent_link(brand: EmailBrand, context: dict[str, str]) -> str:
    """Only https links on our own welcome origin make it into the button."""
    link = (context.get("agent_link") or context.get("referral_link") or "").strip()
    base = (brand.app_url or "").rstrip("/")
    if link.startswith("https://") and (
        link.startswith(f"{base}/") or link.startswith("https://quote.starserveinsuranceagency.com/")
    ):
        return link
    return ""


def _agent_block(brand: EmailBrand, context: dict[str, str]) -> str:
    link = _agent_link(brand, context)
    button = ""
    if link:
        url = escape(link, quote=True)
        button = (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"margin:18px 0 0;\"><tr>"
            f"<td align=\"center\" bgcolor=\"{brand.green}\" "
            f"style=\"background:{brand.green};border-radius:{brand.radius_sm};{_type(brand)}\">"
            f"<a href=\"{url}\" target=\"_blank\" "
            f"style=\"display:block;background:{brand.green};color:{brand.white};"
            "font-size:13px;font-weight:600;line-height:1;text-align:center;"
            f"text-decoration:none;border-radius:{brand.radius_sm};padding:14px 22px;"
            f"{_type(brand)}\">Open your referral link</a>"
            "</td></tr></table>"
        )
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"margin:0 0 24px;\"><tr><td align=\"center\" "
        f"style=\"background:{brand.surface};border-radius:{brand.radius_sm};"
        "padding:20px 16px;\">"
        f"<img src=\"cid:{AGENT_QR_CID}\" width=\"260\" alt=\"Your Star Serve agent QR code\" "
        "style=\"display:block;border:0;outline:none;text-decoration:none;"
        "width:260px;max-width:100%;height:auto;margin:0 auto;border-radius:10px;\" />"
        f"<p style=\"margin:12px 0 0;color:{brand.muted};font-size:11px;line-height:1.5;"
        f"{_type(brand)}\">Customers scan this to quote under your agent code.</p>"
        f"{button}"
        "</td></tr></table>"
    )


def _security_notice(copy: EmailCopy, brand: EmailBrand) -> str:
    detail = escape(copy.footnote) if copy.footnote else (
        "For your security, do not share this email with anyone."
    )
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        f"style=\"margin:4px 0 8px;background:{brand.surface};border-radius:{brand.radius_sm};\">"
        "<tr><td style=\"padding:16px 18px;\">"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        "<tr>"
        f"{_icon_well(brand, 'info')}"
        "<td valign=\"middle\">"
        f"<p style=\"margin:0 0 3px;font-size:12px;font-weight:600;color:{brand.ink};"
        f"line-height:1.4;{_type(brand)}\">Please do not reply</p>"
        f"<p style=\"margin:0;font-size:12px;color:{brand.muted};line-height:1.5;"
        f"{_type(brand)}\">"
        "This email is generated automatically and this mailbox is not monitored. "
        f"{detail}"
        "</p></td></tr></table></td></tr></table>"
    )


def _help_section(brand: EmailBrand) -> str:
    support = escape(brand.support_address)
    rows = [
        _help_row(
            brand,
            "mail",
            f"<a href=\"mailto:{support}\" style=\"color:{brand.ink};text-decoration:none;"
            f"{_type(brand)}\">{support}</a>",
        )
    ]
    if brand.support_phone:
        phone = escape(brand.support_phone)
        tel = "".join(ch for ch in brand.support_phone if ch.isdigit() or ch == "+")
        href = f"tel:{tel}" if tel else ""
        value = (
            f"<a href=\"{escape(href, quote=True)}\" style=\"color:{brand.ink};"
            f"text-decoration:none;{_type(brand)}\">{phone}</a>"
            if href
            else phone
        )
        rows.append(_help_row(brand, "phone", value))
    if brand.support_hours:
        rows.append(_help_row(brand, "clock", escape(brand.support_hours)))
    return (
        f"<h2 style=\"margin:0 0 6px;color:{brand.ink};font-size:14px;line-height:1.3;"
        f"font-weight:700;{_type(brand)}\">Need Help?</h2>"
        f"<p style=\"margin:0 0 12px;color:{brand.muted};font-size:12px;line-height:1.5;"
        f"{_type(brand)}\">Our team is available to assist you:</p>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        f"{''.join(_with_help_row_gaps(rows))}</table>"
    )


def _with_help_row_gaps(rows: list[str]) -> list[str]:
    spaced: list[str] = []
    for index, row in enumerate(rows):
        spaced.append(row)
        if index < len(rows) - 1:
            spaced.append(
                "<tr><td colspan=\"2\" height=\"14\" style=\"height:14px;"
                "font-size:0;line-height:0;\">&nbsp;</td></tr>"
            )
    return spaced


def _help_row(brand: EmailBrand, kind: str, value_html: str) -> str:
    return (
        "<tr>"
        f"{_icon_well(brand, kind)}"
        f"<td valign=\"middle\" style=\"padding:4px 0;color:{brand.ink};font-size:13px;"
        f"line-height:1.4;{_type(brand)}\">{value_html}</td>"
        "</tr>"
    )


def _footer_section(brand: EmailBrand) -> str:
    year = date.today().year
    legal = escape(brand.legal_line) if brand.legal_line else ""
    legal_html = f"<br />{legal}" if legal else ""
    return (
        f"<p style=\"margin:0;color:{brand.muted};font-size:11px;line-height:1.6;"
        f"text-align:center;{_type(brand)}\">"
        f"&copy; {year} {escape(brand.product_name)}. All rights reserved."
        f"{legal_html}"
        "</p>"
    )


def _header_markup(brand: EmailBrand) -> str:
    """Full-bleed reception photo. Falls back to the wordmark on white."""
    if brand.header_url or brand.header_bytes:
        src = (
            escape(brand.header_url, quote=True)
            if brand.header_url
            else f"cid:{brand.header_cid}"
        )
        return (
            f"<img src=\"{src}\" width=\"{brand.card_width}\" height=\"288\" "
            f"alt=\"{escape(brand.product_name)} Insurance Agency\" "
            "style=\"display:block;border:0;outline:none;text-decoration:none;"
            f"width:100%;max-width:{brand.card_width}px;height:auto;\" />"
        )
    if brand.logo_url or brand.logo_bytes:
        src = (
            escape(brand.logo_url, quote=True)
            if brand.logo_url
            else f"cid:{brand.logo_cid}"
        )
        return (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
            f"<tr><td bgcolor=\"{brand.white}\" style=\"background:{brand.white};"
            "padding:20px 28px 16px;\">"
            f"<img src=\"{src}\" width=\"148\" height=\"36\" "
            f"alt=\"{escape(brand.product_name)}\" "
            "style=\"display:block;border:0;width:148px;height:36px;\" />"
            "</td></tr></table>"
        )
    return (
        f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">"
        f"<tr><td bgcolor=\"{brand.white}\" style=\"background:{brand.white};"
        "padding:20px 28px 16px;\">"
        f"<span style=\"font-size:18px;font-weight:700;color:{brand.green};\">"
        f"{escape(brand.product_name)}</span></td></tr></table>"
    )


def _shell(inner: str, *, brand: EmailBrand, preheader: str) -> str:
    header = _header_markup(brand)
    help_block = _help_section(brand)
    footer = _footer_section(brand)
    font = brand.font_stack
    width = brand.card_width
    faces = poppins_font_face_css()
    poppins_href = (
        "https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&amp;display=swap"
    )
    rules = (
        "html,body,table,td,th,p,a,h1,h2,h3,span,div{"
        f"font-family:{font} !important;"
        "}"
        "@media only screen and (max-width:680px){"
        ".ss-card{width:100%!important;max-width:100%!important;}"
        "}"
    )
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{escape(brand.product_name)}</title>"
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />"
        "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />"
        f"<link href=\"{poppins_href}\" rel=\"stylesheet\" type=\"text/css\" />"
        f"<style type=\"text/css\">{faces}{rules}</style>"
        "<!--[if mso]>"
        "<style type=\"text/css\">"
        "body,table,td,p,a,h1,h2,span{font-family:Arial,Helvetica,sans-serif !important;}"
        "</style>"
        "<![endif]--></head>"
        f"<body style=\"margin:0;padding:0;background:{brand.paper};"
        f"font-family:{font};color:{brand.ink};\">"
        f"<style type=\"text/css\">{faces}{rules}</style>"
        "<div style=\"display:none;max-height:0;overflow:hidden;opacity:0;\">"
        f"{escape(preheader)}</div>"
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        f"style=\"background:{brand.paper};font-family:{font};\">"
        "<tr><td align=\"center\" style=\"padding:32px 16px;"
        f"font-family:{font};\">"
        f"<table role=\"presentation\" class=\"ss-card\" width=\"{width}\" cellpadding=\"0\" "
        f"cellspacing=\"0\" style=\"width:{width}px;max-width:{width}px;"
        f"background:{brand.white};border-radius:{brand.radius};overflow:hidden;"
        f"border:1px solid {brand.line};font-family:{font};\">"
        f"<tr><td bgcolor=\"{brand.white}\" style=\"padding:0;line-height:0;"
        f"font-size:0;\">{header}</td></tr>"
        f"<tr><td bgcolor=\"{brand.green}\" height=\"3\" "
        f"style=\"background:{brand.green};height:3px;font-size:0;line-height:0;\">"
        "&nbsp;</td></tr>"
        f"<tr><td bgcolor=\"{brand.white}\" style=\"background:{brand.white};"
        f"padding:36px 44px 8px;font-family:{font};\">"
        f"{inner}</td></tr>"
        f"<tr><td bgcolor=\"{brand.white}\" style=\"background:{brand.white};"
        f"padding:20px 44px 12px;border-top:1px solid {brand.line};"
        f"font-family:{font};\">{help_block}</td></tr>"
        f"<tr><td bgcolor=\"{brand.surface}\" style=\"background:{brand.surface};"
        f"padding:24px 44px;border-top:1px solid {brand.line};font-family:{font};\">"
        f"{footer}</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def outbound_from_notification(
    *,
    recipient: str,
    subject: str | None,
    body: str,
    template_code: str | None,
    context: dict[str, Any] | None,
    settings: Any,
    notification_id: str | None = None,
    extra_attachments: tuple[EmailAttachment, ...] | list[EmailAttachment] = (),
) -> OutboundEmail:
    brand = brand_from_settings(settings)
    return render_outbound(
        recipient=recipient,
        subject=subject or brand.product_name,
        text=body,
        template_code=template_code,
        context=context,
        brand=brand,
        notification_id=notification_id,
        extra_attachments=extra_attachments,
    )
