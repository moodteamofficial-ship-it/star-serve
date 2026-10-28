"""Telecom-standard USSD navigation — context-aware, not global string match."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.modules.ussd.enums import UssdFieldType, UssdScreenType


class NavCommand(StrEnum):
    NONE = "NONE"
    BACK = "BACK"
    HOME = "HOME"
    REPEAT = "REPEAT"


@dataclass(frozen=True, slots=True)
class NavPolicy:
    back: str = "0"
    home: str = "00"
    repeat: str | None = "99"


def classify_navigation(
    raw: str | None,
    *,
    policy: NavPolicy,
    screen_type: str,
    expected_field_type: str | None = None,
    at_root: bool = False,
) -> NavCommand:
    """Reserve 0 / 00 / 99 only when they cannot be valid field values."""
    text = (raw or "").strip()
    if not text:
        return NavCommand.NONE

    # Data-entry screens: never treat a legitimate value as navigation.
    if screen_type in {UssdScreenType.INPUT.value, UssdScreenType.CONFIRM.value}:
        # Paginated workflow menus use 99 for "More" — do not steal it as REPEAT.
        if expected_field_type == UssdFieldType.MENU_CHOICE.value:
            if text == policy.home:
                return NavCommand.HOME
            if text == policy.back:
                return NavCommand.BACK
            return NavCommand.NONE
        if expected_field_type in {
            UssdFieldType.PHONE.value,
            UssdFieldType.ID_NUMBER.value,
            UssdFieldType.VEHICLE_REG.value,
            UssdFieldType.CLAIM_REF.value,
            UssdFieldType.POLICY_REF.value,
            UssdFieldType.NUMBER.value,
            UssdFieldType.DATE.value,
            UssdFieldType.AMOUNT.value,
            UssdFieldType.TEXT.value,
        }:
            # Explicit nav only when the entire input equals the command and
            # cannot be a valid value for that field type.
            if text == policy.home:
                return NavCommand.HOME
            if text == policy.back and not _looks_like_field_value(text, expected_field_type):
                return NavCommand.BACK
            if policy.repeat and text == policy.repeat:
                return NavCommand.REPEAT
            return NavCommand.NONE

    if text == policy.home:
        return NavCommand.HOME
    if text == policy.back:
        # At root, BACK redisplays the main menu (documented fallback).
        return NavCommand.HOME if at_root else NavCommand.BACK
    if policy.repeat and text == policy.repeat:
        return NavCommand.REPEAT
    return NavCommand.NONE


def _looks_like_field_value(text: str, field_type: str | None) -> bool:
    if field_type == UssdFieldType.PHONE.value:
        # Kenyan mobiles often start with 0 — never steal those as BACK.
        return text.startswith("0") and len(text) >= 9
    if field_type in {UssdFieldType.NUMBER.value, UssdFieldType.AMOUNT.value, UssdFieldType.DATE.value}:
        return text.isdigit() or text.replace(".", "", 1).isdigit()
    if field_type == UssdFieldType.ID_NUMBER.value:
        return len(text) >= 5
    return False
