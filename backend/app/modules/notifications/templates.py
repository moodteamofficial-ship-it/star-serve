"""Built-in notification templates — body never trusts raw client HTML."""

from typing import Any

from app.core.exceptions import ValidationAppError
from app.modules.notifications.enums import NotificationTemplate

# GENERIC_ALERT is not in this map: the public API must not accept a client-supplied
# body. Domain events use the templates below; staff send() is limited to them too.
_CUSTOMER_TEMPLATES: dict[str, dict[str, str]] = {
    NotificationTemplate.PAYMENT_RECEIVED.value: {
        "subject": "Payment received — {reference}",
        "body": (
            "Payment {reference} of {amount} {currency} was received for policy "
            "{policy_number}. Receipt: {receipt}. {referral_note}"
        ),
    },
    NotificationTemplate.PAYMENT_FAILED.value: {
        "subject": "Payment not completed — {reference}",
        "body": (
            "Payment {reference} of {amount} {currency} for policy {policy_number} was not "
            "completed: {failure_reason}. No cover has been issued yet. Please try again."
        ),
    },
    NotificationTemplate.POLICY_ACTIVATED.value: {
        "subject": "Policy activated — {policy_number}",
        "body": (
            "Policy {policy_number} for vehicle {vehicle_registration} is now ACTIVE. "
            "Cover: {cover_start_date} to {cover_end_date}. {referral_note}"
        ),
    },
    NotificationTemplate.CERTIFICATE_READY.value: {
        "subject": "Certificate ready — {policy_number}",
        "body": (
            "Certificate {certificate_number} for policy {policy_number} is ready. "
            "External ref: {external_certificate_ref}."
        ),
    },
    NotificationTemplate.PROPOSAL_APPROVED.value: {
        "subject": "Proposal approved — {vehicle_registration}",
        "body": (
            "Proposal for {vehicle_registration} ({product_code}) was approved. "
            "Gross premium: {gross_premium}."
        ),
    },
    NotificationTemplate.CLAIM_RECEIVED.value: {
        "subject": "Claim received — {claim_number}",
        "body": "We have received claim {claim_number} for {vehicle_registration}.",
    },
    NotificationTemplate.CLAIM_UNDER_REVIEW.value: {
        "subject": "Claim under review — {claim_number}",
        "body": "Claim {claim_number} is now under review.",
    },
    NotificationTemplate.CLAIM_INFORMATION_REQUIRED.value: {
        "subject": "More information needed — {claim_number}",
        "body": "We need additional information to continue claim {claim_number}.",
    },
    NotificationTemplate.CLAIM_FOLLOWUP.value: {
        "subject": "Claim follow-up — {claim_number}",
        "body": (
            "There is a follow-up on claim {claim_number}: {followup_subject}. "
            "Due: {due_at}."
        ),
    },
    NotificationTemplate.CLAIM_VETTING_PASSED.value: {
        "subject": "Claim passed review — {claim_number}",
        "body": "Claim {claim_number} has passed internal review.",
    },
    NotificationTemplate.CLAIM_FORWARDED.value: {
        "subject": "Claim forwarded — {claim_number}",
        "body": "Claim {claim_number} has been forwarded to the insurer for decision.",
    },
    NotificationTemplate.CLAIM_APPROVED.value: {
        "subject": "Claim approved — {claim_number}",
        "body": "Claim {claim_number} has been approved.",
    },
    NotificationTemplate.CLAIM_REJECTED.value: {
        "subject": "Claim update — {claim_number}",
        "body": "Claim {claim_number} was not approved. Contact your agency for details.",
    },
    NotificationTemplate.CLAIM_PAYMENT_INITIATED.value: {
        "subject": "Payment started — {claim_number}",
        "body": "A payment of {amount} {currency} has been initiated for claim {claim_number}.",
    },
    NotificationTemplate.CLAIM_PAYMENT_COMPLETED.value: {
        "subject": "Payment completed — {claim_number}",
        "body": "Payment of {amount} {currency} for claim {claim_number} has been completed.",
    },
    NotificationTemplate.CLAIM_CLIENT_MESSAGE.value: {
        "subject": "Claim update — {claim_number}",
        "body": "There is a new update on claim {claim_number}. Please contact your agency.",
    },
}

_TRANSACTIONAL_TEMPLATES: dict[str, dict[str, str]] = {
    NotificationTemplate.OTP_CODE.value: {
        "subject": "Your Star Serve verification code",
        "body": (
            "Your Star Serve code is {otp_code}. It expires in {otp_minutes} minutes. "
            "Do not share it."
        ),
    },
    NotificationTemplate.OTP_LOGIN.value: {
        "subject": "Your Star Serve sign-in code",
        "body": "Your Star Serve sign-in code is {otp_code}. It expires in {otp_minutes} minutes.",
    },
    NotificationTemplate.OTP_VERIFY.value: {
        "subject": "Confirm your Star Serve account",
        "body": (
            "Your Star Serve verification code is {otp_code}. "
            "It expires in {otp_minutes} minutes."
        ),
    },
    NotificationTemplate.ACCOUNT_UPDATED.value: {
        "subject": "Your Star Serve account was updated",
        "body": "Hello {recipient_name}, your Star Serve account was updated. {detail}",
    },
    NotificationTemplate.ACCOUNT_PASSWORD_CHANGED.value: {
        "subject": "Your Star Serve password was changed",
        "body": (
            "Hello {recipient_name}, the password on your Star Serve account was changed. "
            "If this was not you, contact your administrator."
        ),
    },
    NotificationTemplate.ACCOUNT_STATUS_CHANGED.value: {
        "subject": "Your Star Serve account status changed",
        "body": "Hello {recipient_name}, your Star Serve account status is now {status}.",
    },
    NotificationTemplate.ACCOUNT_SIGNED_IN.value: {
        "subject": "New sign-in to your Star Serve account",
        "body": (
            "Hello {recipient_name}, your Star Serve account was signed in at "
            "{sign_in_at} from {ip_address} ({device}). If this was not you, "
            "change your password and tell your administrator."
        ),
    },
    NotificationTemplate.CLAIM_PDF.value: {
        "subject": "Your claim PDF — {claim_number}",
        "body": (
            "A PDF copy of claim {claim_number} for {vehicle_registration} "
            "is attached to this email."
        ),
    },
    NotificationTemplate.CERTIFICATE_PDF.value: {
        "subject": "Your certificate PDF — {certificate_number}",
        "body": (
            "A PDF copy of certificate {certificate_number} for policy {policy_number} "
            "is attached to this email."
        ),
    },
    NotificationTemplate.AGENT_REGISTERED.value: {
        "subject": "Your Star Serve agent kit {agent_code}",
        "body": (
            "Hello {recipient_name}, welcome to Star Serve.\n\n"
            "Your agent code is {agent_code}.\n\n"
            "How to use your agent code:\n"
            "1. Share your personal link so customers get a quote under your code.\n"
            "2. Show or print your QR card so customers can scan it on their phone.\n"
            "3. You can also tell customers your agent code to enter when they buy cover.\n\n"
            "Your personal referral link:\n{agent_link}\n\n"
            "Your QR card is attached. Keep it handy when you meet customers. "
            "The link and QR go live once your account is approved."
        ),
    },
    NotificationTemplate.AGENT_APPROVED.value: {
        "subject": "Your Star Serve agent account is approved",
        "body": (
            "Hello {recipient_name}, your Star Serve agent account is approved. "
            "You can sign in with your email and password. "
            "Your agent code is {agent_code}. "
            "Share your personal link so customers quote under you: {agent_link}"
        ),
    },
    NotificationTemplate.CUSTOMER_REFERRAL_KIT.value: {
        "subject": "Your Star Serve referral kit {referral_code}",
        "body": (
            "Hello {recipient_name}, here is your Star Serve referral kit.\n\n"
            "Your referral code is {referral_code}.\n\n"
            "How to use your referral code:\n"
            "1. Share your personal link so a friend can get a quote.\n"
            "2. Show or print your QR card so they can scan it on their phone.\n"
            "3. You can also tell them your referral code to enter when they buy cover.\n\n"
            "Your personal referral link:\n{referral_link}\n\n"
            "Your QR card is attached. When a friend pays for cover, you earn credit "
            "off your next cover."
        ),
    },
}

_TEMPLATES: dict[str, dict[str, str]] = {**_CUSTOMER_TEMPLATES, **_TRANSACTIONAL_TEMPLATES}

_SENSITIVE_CONTEXT_KEYS = frozenset({"otp_code"})
_OTP_TEMPLATES = frozenset(
    {
        NotificationTemplate.OTP_CODE.value,
        NotificationTemplate.OTP_LOGIN.value,
        NotificationTemplate.OTP_VERIFY.value,
    }
)


def list_template_codes() -> list[str]:
    """Staff catalog — transactional OTP / account mail is not staff-sendable."""
    return sorted(_CUSTOMER_TEMPLATES.keys())


def is_known_template(template_code: str) -> bool:
    return template_code.upper() in _TEMPLATES


def is_staff_template(template_code: str) -> bool:
    return template_code.upper() in _CUSTOMER_TEMPLATES


def is_otp_template(template_code: str) -> bool:
    return template_code.upper() in _OTP_TEMPLATES


def template_priority(template_code: str) -> int:
    code = template_code.upper()
    if code in _OTP_TEMPLATES:
        return 10
    if code.startswith("ACCOUNT_") or code in {
        NotificationTemplate.AGENT_REGISTERED.value,
        NotificationTemplate.AGENT_APPROVED.value,
        NotificationTemplate.CUSTOMER_REFERRAL_KIT.value,
    }:
        return 20
    if code in {
        NotificationTemplate.CLAIM_INFORMATION_REQUIRED.value,
        NotificationTemplate.CLAIM_FOLLOWUP.value,
    }:
        return 30
    if code.startswith("CLAIM_"):
        return 50
    if code.startswith("POLICY_") or code.startswith("PAYMENT_") or code.startswith("CERTIFICATE_"):
        return 60
    return 100


_ALLOWED_CONTEXT_KEYS = frozenset(
    {
        "reference",
        "amount",
        "currency",
        "policy_number",
        "receipt",
        "vehicle_registration",
        "cover_start_date",
        "cover_end_date",
        "certificate_number",
        "external_certificate_ref",
        "product_code",
        "gross_premium",
        "claim_number",
        "claim_id",
        "status",
        "recipient_name",
        "otp_code",
        "otp_minutes",
        "followup_subject",
        "due_at",
        "detail",
        "sign_in_at",
        "ip_address",
        "device",
        "agent_code",
        "agent_link",
        "referral_code",
        "referral_link",
        "referral_offer",
        "referral_promo",
        "referral_note",
        "referral_credit",
        "failure_reason",
    }
)
_MAX_CONTEXT_VALUE = 120
_MAX_BY_KEY = {
    "otp_code": 16,
    "otp_minutes": 4,
    "claim_id": 36,
    "agent_code": 16,
    "agent_link": 200,
    "referral_code": 16,
    "referral_link": 200,
    "referral_offer": 160,
    "referral_promo": 80,
    "referral_note": 320,
    "failure_reason": 80,
}


def sanitize_template_context(context: dict[str, Any] | None) -> dict[str, str]:
    """Keep only named placeholders. A free-form ``message`` is never accepted."""
    safe: dict[str, str] = {}
    for key, value in (context or {}).items():
        if key not in _ALLOWED_CONTEXT_KEYS:
            continue
        text = "" if value is None else str(value)
        cap = _MAX_BY_KEY.get(key, _MAX_CONTEXT_VALUE)
        safe[key] = text[:cap]
    return safe


def redact_sensitive_context(context: dict[str, Any] | None) -> dict[str, str]:
    safe = sanitize_template_context(context)
    for key in _SENSITIVE_CONTEXT_KEYS:
        if key in safe and safe[key]:
            safe[key] = "***"
    return safe


def redact_otp_from_body(body: str, context: dict[str, Any] | None) -> str:
    code = str((context or {}).get("otp_code") or "")
    if not code:
        return body
    return body.replace(code, "******")


SMS_FOOTER = "From Star Serve"
SMS_MAX_CHARS = 300


def _fit_sms(core: list[str], extras: list[str]) -> str:
    """Core sentences always; extras only while the SMS stays within SMS_MAX_CHARS."""
    footer = f"\n{SMS_FOOTER}"
    budget = SMS_MAX_CHARS - len(footer)
    text = " ".join(part.strip() for part in core if part and part.strip())
    text = " ".join(text.split())
    if len(text) > budget:
        text = text[: budget - 1].rstrip(" ,.;:") + "…"
    for extra in extras:
        candidate = f"{text} {extra}"
        if len(candidate) <= budget:
            text = candidate
    return text + footer


def _sms_money(c: dict[str, str]) -> str:
    return " ".join(part for part in (c.get("currency") or "KES", c.get("amount")) if part)


def _sms_cover_target(c: dict[str, str]) -> str:
    policy = c.get("policy_number") or ""
    vehicle = c.get("vehicle_registration") or ""
    if policy and vehicle:
        return f" for policy {policy} ({vehicle})"
    if policy:
        return f" for policy {policy}"
    if vehicle:
        return f" for vehicle {vehicle}"
    return ""


def _sms_referral_share(c: dict[str, str]) -> str:
    """Short share block — only when a referral link was generated for the customer."""
    link = (c.get("referral_link") or "").strip()
    if not link:
        return ""
    promo = (c.get("referral_promo") or "").strip() or "REFER A FRIEND AND EARN shs 50"
    return f"{promo}. Share this link: {link}"


def _sms_payment_received(c: dict[str, str]) -> str:
    name = c.get("recipient_name") or "Customer"
    receipt = c.get("receipt") or c.get("reference") or ""
    core = [
        f"Dear {name}, we have received your payment of {_sms_money(c)}{_sms_cover_target(c)}.",
        f"Receipt: {receipt}." if receipt else "",
        "Your motor cover is now active.",
    ]
    # Referral share first so it wins the SMS budget over courtesy lines.
    extras = [
        part
        for part in (
            _sms_referral_share(c),
            "Thank you for choosing us.",
            "For any assistance, please contact your agent.",
        )
        if part
    ]
    return _fit_sms(core, extras)


def _sms_payment_failed(c: dict[str, str]) -> str:
    name = c.get("recipient_name") or "Customer"
    reason = c.get("failure_reason") or "the payment could not be completed"
    core = [
        f"Dear {name}, your payment of {_sms_money(c)}{_sms_cover_target(c)} "
        f"was not completed ({reason}).",
        "No cover has been issued yet.",
        "Please retry the payment or contact your agent for assistance.",
    ]
    return _fit_sms(core, ["Thank you for choosing us."])


def _sms_agent_registered(c: dict[str, str]) -> str:
    name = (c.get("recipient_name") or "Agent").strip() or "Agent"
    code = (c.get("agent_code") or "").strip()
    link = (c.get("agent_link") or "").strip()
    core = [
        f"Dear {name}, welcome to Star Serve.",
        f"Your agent code is {code}." if code else "",
        "Share your link so customers quote under you." if link else "",
        link,
    ]
    return _fit_sms(core, ["Show your QR from email when you meet customers."])


def _sms_agent_approved(c: dict[str, str]) -> str:
    name = (c.get("recipient_name") or "Agent").strip() or "Agent"
    code = (c.get("agent_code") or "").strip()
    link = (c.get("agent_link") or "").strip()
    core = [
        f"Dear {name}, your Star Serve agent account is approved.",
        f"Agent code {code}." if code else "",
        "Sign in with your email and password.",
        f"Share: {link}" if link else "",
    ]
    return _fit_sms(core, [])


def _sms_customer_referral_kit(c: dict[str, str]) -> str:
    name = (c.get("recipient_name") or "Customer").strip() or "Customer"
    code = (c.get("referral_code") or "").strip()
    link = (c.get("referral_link") or "").strip()
    core = [
        f"Dear {name}, here is your Star Serve referral kit.",
        f"Your referral code is {code}." if code else "",
        "Share your link so a friend can quote and you earn credit." if link else "",
        link,
    ]
    return _fit_sms(core, ["Your QR card is in the email if you have one on file."])


_SMS_BUILDERS = {
    NotificationTemplate.PAYMENT_RECEIVED.value: _sms_payment_received,
    NotificationTemplate.PAYMENT_FAILED.value: _sms_payment_failed,
    NotificationTemplate.AGENT_REGISTERED.value: _sms_agent_registered,
    NotificationTemplate.AGENT_APPROVED.value: _sms_agent_approved,
    NotificationTemplate.CUSTOMER_REFERRAL_KIT.value: _sms_customer_referral_kit,
}

_SHORT_BODY_CHANNELS = frozenset({"SMS", "WHATSAPP"})


def render_template(
    template_code: str, context: dict[str, Any], *, channel: str | None = None
) -> tuple[str, str]:
    code = template_code.upper()
    if code == NotificationTemplate.GENERIC_ALERT.value:
        raise ValidationAppError("That notification template is not available")
    tmpl = _TEMPLATES.get(code)
    if tmpl is None:
        raise ValidationAppError(f"Unknown notification template: {template_code}")
    safe = sanitize_template_context(context)

    def _fmt(pattern: str) -> str:
        try:
            return pattern.format_map(_SafeDict(safe))
        except Exception as exc:
            raise ValidationAppError("Failed to render notification template") from exc

    short = _SMS_BUILDERS.get(code) if (channel or "").upper() in _SHORT_BODY_CHANNELS else None
    if short is not None:
        return _fmt(tmpl["subject"]), short(safe)
    return _fmt(tmpl["subject"]), _fmt(tmpl["body"])


class _SafeDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""
