"""MOTOR_QUOTE helpers — DB labels, char-safe pages, referral confirm."""

import pytest

from app.core.exceptions import ValidationAppError
from app.modules.ussd.workflows.motor_quote import (
    _MAX_PAGE,
    _USSD_MAX_CHARS,
    _clip_label,
    _fit_menu_page,
    _resolve_shown_choice,
    split_full_name,
)


def test_split_full_name_two_parts():
    assert split_full_name("Jane Doe") == ("Jane", "Doe")


def test_split_full_name_middle_names():
    assert split_full_name("  Jane  Marie  Doe  ") == ("Jane", "Marie Doe")


def test_split_full_name_requires_last():
    with pytest.raises(ValidationAppError):
        split_full_name("Jane")


def test_format_product_label_strips_cover_suffix():
    from app.modules.ussd.workflows.motor_quote import _format_product_label

    assert _format_product_label("MOTOR PSV - BUSES(TPO ONLY)") == "Motor PSV"
    assert _format_product_label("TUK TUK PSV - PORTAL") == "Tuk Tuk PSV"
    assert _format_product_label("PRIVATE HIRE - TPO") == "Private Hire"


def test_visible_cover_options_hides_monthly_sibling():
    from app.modules.ussd.workflows.motor_quote import _visible_cover_options

    covers = [
        {"id": "1", "name": "TPO"},
        {"id": "2", "name": "TPO MONTHLY"},
        {"id": "3", "name": "COMPREHENSIVE"},
    ]
    visible = _visible_cover_options(covers)
    assert [c["id"] for c in visible] == ["1", "3"]


def test_priced_cover_option_uses_monthly_sibling():
    from app.modules.ussd.workflows.motor_quote import _priced_cover_option

    covers = [
        {"id": "3535", "name": "TPO"},
        {"id": "3536", "name": "TPO MONTHLY"},
    ]
    priced = _priced_cover_option(covers, "3535", "Monthly")
    assert priced["id"] == "3536"
    annual = _priced_cover_option(covers, "3535", "Annually")
    assert annual["id"] == "3535"


def test_clip_label_uses_db_text_not_invented_compact():
    name = "MOTOR PSV - BUSES(TPO ONLY)"
    assert _clip_label(name, 40) == name
    # Hard trim of the stored Definite string — no LEFT-RIGHT rewrite.
    assert _clip_label(name, 18) == name[:18].rstrip()
    assert _clip_label(name, 18).startswith("MOTOR PSV")


def test_fit_menu_page_shows_nine_when_budget_allows():
    items = [{"name": f"Make{i:02d}"} for i in range(20)]
    chunk, message, has_more = _fit_menu_page(
        "Select make", items, 0, label_fn=lambda i: i["name"]
    )
    assert len(chunk) == _MAX_PAGE
    assert has_more is True
    assert "99 More" in message
    assert len(message) <= _USSD_MAX_CHARS
    for n in range(1, 10):
        assert f"{n}. " in message


def test_fit_menu_page_keeps_db_cover_text():
    items = [{"name": n} for n in [
        "PRIVATE HIRE - PORTAL",
        "MOTOR PSV - BUSES(TPO ONLY)",
        "TUK TUK PSV - PORTAL",
        "MOTOR PRIVATE - PORTAL",
        "MOTOR COMMERCIAL - TPO",
        "MATATU PSV - TPO",
        "MOTOR CYCLE - TPO",
        "MOTOR CYCLE - COMPREHENSIVE",
        "EXTRA PRODUCT - TPO",
        "ANOTHER - TPO",
    ]]
    chunk, message, has_more = _fit_menu_page(
        "Select product", items, 0, label_fn=lambda i: i["name"]
    )
    assert has_more is True
    assert len(message) <= _USSD_MAX_CHARS
    assert len(chunk) >= 5
    # Stored Definite cover/class text should remain visible (clipped, not rewritten).
    assert (
        "BUSES(" in message
        or "PRIVATE HIRE" in message
        or "PORT" in message
        or "TPO" in message
    )
    assert "MOTOR PSV-TPO" not in message


def test_fit_menu_page_more_advances_by_shown():
    items = [{"name": f"Item{i:02d}"} for i in range(15)]
    chunk1, _, _ = _fit_menu_page(
        "Select make", items, 0, label_fn=lambda i: i["name"]
    )
    offset = len(chunk1)
    chunk2, message2, has_more2 = _fit_menu_page(
        "Select make", items, offset, label_fn=lambda i: i["name"]
    )
    assert chunk2[0]["name"] == items[offset]["name"]
    assert len(message2) <= _USSD_MAX_CHARS
    assert has_more2 is (offset + len(chunk2) < len(items))


def test_resolve_shown_choice():
    items = [f"i{n}" for n in range(12)]
    assert _resolve_shown_choice(items, 0, 9, "1") == "i0"
    assert _resolve_shown_choice(items, 0, 9, "9") == "i8"
    assert _resolve_shown_choice(items, 9, 3, "1") == "i9"
    assert _resolve_shown_choice(items, 0, 9, "99") is None
    assert _resolve_shown_choice(items, 0, 7, "8") is None


def test_confirm_shows_total_only_keeps_pay_options():
    from app.modules.ussd.workflows.motor_quote import MotorQuoteWorkflow, _USSD_MAX_CHARS

    text = MotorQuoteWorkflow()._confirm_text(
        {
            "product": {"cover_option_name": "TPO"},
            "cover_period": "Monthly",
            "vehicle_make": {"name": "BMW"},
            "vehicle_model": {"name": "7 SERIES"},
            "vehicle_registration": "KBG TEST",
            "premium_basic": "4000.0",
            "premium_phcf": "10.0",
            "premium_training": "8.0",
            "premium_stamp": "40.0",
            "gross_premium": "4058.0",
            "referral_cost": "50.00",
            "amount_due": "4108.00",
        }
    )
    # Breakdown / vehicle details stay off the handset screen.
    assert "Basic:" not in text
    assert "PHCF" not in text
    assert "Gross:" not in text
    assert "Referral" not in text
    assert "BMW" not in text
    assert "KBG TEST" not in text
    assert "TPO Monthly" in text
    assert "Total: KES 4108" in text
    assert "1. Pay via M-Pesa" in text
    assert "2. Cancel" in text
    # Fit with nav footer on one Birdview screen (no gateway More page).
    from app.modules.ussd.workflows.motor_quote import _nav

    assert len(_nav(text)) <= _USSD_MAX_CHARS


def test_confirm_formats_whole_kes_without_decimals():
    from app.modules.ussd.workflows.motor_quote import MotorQuoteWorkflow

    text = MotorQuoteWorkflow()._confirm_text(
        {
            "product": {"cover_option_name": "TPO"},
            "cover_period": "Annually",
            "amount_due": "5200.00",
        }
    )
    assert "Total: KES 5200" in text
    assert "5200.00" not in text
