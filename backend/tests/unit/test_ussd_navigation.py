"""USSD navigation and menu seed — no database required."""

from app.modules.ussd.navigation import NavCommand, NavPolicy, classify_navigation
from app.modules.ussd.privacy import hash_msisdn, mask_msisdn, normalize_msisdn
from app.modules.ussd.seed import default_menu_definition, render_menu_text


def test_main_menu_has_three_active_options():
    definition = default_menu_definition()
    main = definition["screens"]["main"]
    options = [o for o in main["options"] if o.get("active")]
    assert [o["key"] for o in options] == ["1", "2", "3"]
    assert "Motor Insurance Cover" in options[0]["label"]
    assert "Report a Claim" in options[1]["label"]
    assert "Follow Up a Claim" in options[2]["label"]
    text = render_menu_text(main)
    assert "Welcome to StarServe Insurance" in text
    assert "1. Motor Insurance Cover" in text
    assert "0 Back" not in text
    assert "Main menu" not in text


def test_back_and_home_on_menu():
    policy = NavPolicy()
    assert classify_navigation("0", policy=policy, screen_type="MENU", at_root=False) == NavCommand.BACK
    assert classify_navigation("0", policy=policy, screen_type="MENU", at_root=True) == NavCommand.HOME
    assert classify_navigation("00", policy=policy, screen_type="MENU") == NavCommand.HOME
    assert classify_navigation("99", policy=policy, screen_type="MENU") == NavCommand.REPEAT
    assert classify_navigation("1", policy=policy, screen_type="MENU") == NavCommand.NONE


def test_phone_starting_with_zero_is_not_back():
    policy = NavPolicy()
    nav = classify_navigation(
        "0712345678",
        policy=policy,
        screen_type="INPUT",
        expected_field_type="PHONE",
    )
    assert nav == NavCommand.NONE


def test_home_still_works_on_input_screens():
    policy = NavPolicy()
    nav = classify_navigation(
        "00",
        policy=policy,
        screen_type="INPUT",
        expected_field_type="PHONE",
    )
    assert nav == NavCommand.HOME


def test_menu_choice_ninety_nine_is_not_repeat():
    """Paginated workflow lists use 99 for More — must reach the handler."""
    policy = NavPolicy(repeat="99")
    nav = classify_navigation(
        "99",
        policy=policy,
        screen_type="INPUT",
        expected_field_type="MENU_CHOICE",
    )
    assert nav == NavCommand.NONE
    assert (
        classify_navigation(
            "0",
            policy=policy,
            screen_type="INPUT",
            expected_field_type="MENU_CHOICE",
        )
        == NavCommand.BACK
    )


def test_msisdn_normalize_mask_hash():
    assert normalize_msisdn("0712345678") == "254712345678"
    assert mask_msisdn("0712345678").startswith("254")
    assert "***" not in hash_msisdn("0712345678")
    assert hash_msisdn("0712345678") == hash_msisdn("254712345678")
    assert len(hash_msisdn("0712345678")) == 64
