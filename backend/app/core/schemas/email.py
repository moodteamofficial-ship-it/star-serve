"""Email field that accepts reserved TLDs used in local seeds (.local, .test).

Pydantic EmailStr / email-validator rejects special-use domains, which breaks
dev logins like admin@agency-a.local.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 255 or not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address")
    local, _, domain = email.partition("@")
    if not local or not domain or ".." in email:
        raise ValueError("Invalid email address")
    return email


AppEmail = Annotated[str, AfterValidator(_normalize_email)]
