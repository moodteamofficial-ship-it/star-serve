"""Customer origin — staff CRM vs guest-quote plane."""

from enum import StrEnum


class CustomerOrigin(StrEnum):
    STAFF = "STAFF"
    GUEST = "GUEST"
