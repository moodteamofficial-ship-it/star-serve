"""Policy lifecycle enums."""

from enum import StrEnum


class PolicyStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    PENDING_CERTIFICATE = "PENDING_CERTIFICATE"
