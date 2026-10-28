"""Default published menu definition for StarServe USSD."""

from __future__ import annotations

from typing import Any

from app.modules.ussd.enums import UssdFieldType, UssdScreenType, UssdWorkflowAction

WELCOME = "Welcome to StarServe Insurance"


def default_menu_definition() -> dict[str, Any]:
    """Screens keyed by screen_key. Root is ``main``."""
    return {
        "screens": {
            "main": {
                "key": "main",
                "type": UssdScreenType.MENU.value,
                "title": WELCOME,
                "body": "",
                "options": [
                    {
                        "key": "1",
                        "label": "Motor Insurance Cover",
                        "sort_order": 1,
                        "active": True,
                        "destination_screen": None,
                        "workflow_action": UssdWorkflowAction.MOTOR_QUOTE.value,
                    },
                    {
                        "key": "2",
                        "label": "Report a Claim",
                        "sort_order": 2,
                        "active": True,
                        "destination_screen": None,
                        "workflow_action": UssdWorkflowAction.REPORT_CLAIM.value,
                    },
                    {
                        "key": "3",
                        "label": "Follow Up a Claim",
                        "sort_order": 3,
                        "active": True,
                        "destination_screen": None,
                        "workflow_action": UssdWorkflowAction.FOLLOW_UP_CLAIM.value,
                    },
                ],
                "footer": "",
            },
            "invalid_main": {
                "key": "invalid_main",
                "type": UssdScreenType.MESSAGE.value,
                "title": "Invalid option. Select 1, 2 or 3.",
                "body": "",
                "end_session": False,
            },
        },
        "field_defaults": {
            UssdFieldType.ID_NUMBER.value: {
                "min_length": 5,
                "max_length": 20,
                "pattern": r"^[A-Za-z0-9/\-]{5,20}$",
                "error": "Invalid ID number. Try again or press 0 to go back.",
            },
            UssdFieldType.PHONE.value: {
                "min_length": 9,
                "max_length": 15,
                "pattern": r"^[0-9+]{9,15}$",
                "error": "Invalid phone number. Try again or press 0 to go back.",
            },
            UssdFieldType.VEHICLE_REG.value: {
                "min_length": 3,
                "max_length": 12,
                "pattern": r"^[A-Za-z0-9 ]{3,12}$",
                "error": "Invalid registration. Try again or press 0 to go back.",
            },
            UssdFieldType.CLAIM_REF.value: {
                "min_length": 6,
                "max_length": 32,
                "pattern": r"^[A-Za-z0-9\-]{6,32}$",
                "error": "Invalid claim reference. Try again or press 0 to go back.",
            },
            UssdFieldType.POLICY_REF.value: {
                "min_length": 4,
                "max_length": 64,
                "error": "Invalid policy number. Try again or press 0 to go back.",
            },
            UssdFieldType.DATE.value: {
                "min_length": 8,
                "max_length": 10,
                "error": "Use date as DDMMYYYY. Try again or press 0 to go back.",
            },
            UssdFieldType.TEXT.value: {
                "min_length": 3,
                "max_length": 160,
                "error": "Invalid entry. Try again or press 0 to go back.",
            },
            UssdFieldType.AMOUNT.value: {
                "min_length": 1,
                "max_length": 12,
                "pattern": r"^[0-9]+(\.[0-9]{1,2})?$",
                "error": "Invalid amount. Try again or press 0 to go back.",
            },
        },
        "messages": {
            "session_timeout": "Session ended due to inactivity. Dial again to continue.",
            "too_many_errors": "Too many invalid attempts. Please dial again.",
            "technical_error": "Service temporarily unavailable. Please try again later.",
            "goodbye": "Thank you for using StarServe Insurance.",
        },
    }


def render_menu_text(screen: dict[str, Any], *, max_chars: int = 160) -> str:
    lines: list[str] = []
    title = (screen.get("title") or "").strip()
    body = (screen.get("body") or "").strip()
    if title:
        lines.append(title)
    if body:
        lines.append(body)
    options = sorted(
        [o for o in (screen.get("options") or []) if o.get("active", True)],
        key=lambda o: int(o.get("sort_order") or 0),
    )
    for opt in options:
        lines.append(f"{opt['key']}. {opt['label']}")
    footer = (screen.get("footer") or "").strip()
    if footer:
        lines.append(footer)
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text
