from decimal import Decimal

from app.modules.notifications.enums import NotificationTemplate
from app.modules.notifications.templates import render_template
from app.modules.referrals.service import (
    generate_referral_code,
    max_discount,
    normalize_referral_code,
    referral_link,
)


def test_generated_codes_are_valid_and_distinct_from_agent_codes():
    for _ in range(200):
        code = generate_referral_code()
        assert normalize_referral_code(code) == code
        assert not code.isdigit()
        assert len(code) == 8


def test_normalize_accepts_spacing_and_case():
    assert normalize_referral_code(" ss-a2ky ng ") == "SSA2KYNG"


def test_normalize_rejects_agent_codes_and_ambiguous_characters():
    assert normalize_referral_code("123456") is None
    assert normalize_referral_code("SSO0I1LL") is None
    assert normalize_referral_code("") is None
    assert normalize_referral_code(None) is None


def test_discount_is_whole_shillings_and_leaves_one_shilling_to_pay():
    assert max_discount(Decimal("350"), Decimal("292")) == Decimal("291.00")
    assert max_discount(Decimal("50"), Decimal("1798")) == Decimal("50.00")
    assert max_discount(Decimal("50.75"), Decimal("1798")) == Decimal("50.00")
    assert max_discount(Decimal("0"), Decimal("1798")) == Decimal("0.00")
    assert max_discount(Decimal("100"), Decimal("1")) == Decimal("0.00")


def test_referral_link_uses_hash_key_r():
    assert referral_link("SSA2KYNG").endswith("/#r=SSA2KYNG")


def test_payment_email_carries_referral_note():
    _, body = render_template(
        NotificationTemplate.PAYMENT_RECEIVED.value,
        {
            "reference": "PAY-1",
            "amount": "1798",
            "currency": "KES",
            "policy_number": "POL-1",
            "receipt": "R1",
            "referral_note": "REFER A FRIEND AND EARN shs 50. Share this link: https://x.test/#r=SSA2KYNG",
        },
    )
    assert "REFER A FRIEND AND EARN shs 50" in body
    assert "https://x.test/#r=SSA2KYNG" in body


def test_payment_sms_carries_referral_share_link():
    link = "https://quote.starserveinsuranceagency.com/dashboard/#r=SSA2KYNG"
    _, body = render_template(
        NotificationTemplate.PAYMENT_RECEIVED.value,
        {
            "recipient_name": "Test",
            "reference": "PAY-1",
            "amount": "592.00",
            "currency": "KES",
            "policy_number": "POL-EEDCF1D6AF",
            "vehicle_registration": "BIT 3579",
            "receipt": "UJ8LE9MZYP",
            "referral_link": link,
            "referral_promo": "REFER A FRIEND AND EARN shs 50",
        },
        channel="SMS",
    )
    assert body.startswith("Dear Test, we have received your payment of KES 592.00")
    assert "POL-EEDCF1D6AF (BIT 3579)" in body
    assert "Receipt: UJ8LE9MZYP." in body
    assert "Your motor cover is now active." in body
    assert "REFER A FRIEND AND EARN shs 50" in body
    assert f"Share this link: {link}" in body
    assert body.endswith("\nFrom Star Serve")


def test_payment_sms_without_referral_note_still_renders():
    _, body = render_template(
        NotificationTemplate.PAYMENT_RECEIVED.value,
        {"reference": "PAY-1", "amount": "1", "currency": "KES", "policy_number": "P"},
    )
    assert "{referral_note}" not in body
    _, sms = render_template(
        NotificationTemplate.PAYMENT_RECEIVED.value,
        {"reference": "PAY-1", "amount": "1", "currency": "KES", "policy_number": "P"},
        channel="SMS",
    )
    assert "REFER A FRIEND" not in sms
    assert "Share this link" not in sms
