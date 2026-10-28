"""Proposal and policy lifecycle enums."""

from enum import StrEnum


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    PREMIUM_CALCULATED = "PREMIUM_CALCULATED"
    DOUBLE_INSURANCE_CHECKED = "DOUBLE_INSURANCE_CHECKED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    CONVERTED = "CONVERTED"
