"""Agent commission enums — bank-style ledger movements."""

from enum import StrEnum


class PayoutCadence(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class CommissionSourceEvent(StrEnum):
    CERTIFICATE_PAYMENT = "CERTIFICATE_PAYMENT"
    CLAIM_PAYMENT = "CLAIM_PAYMENT"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    PAYOUT = "PAYOUT"
    REVERSAL = "REVERSAL"


class CommissionEntryKind(StrEnum):
    ACCRUAL = "ACCRUAL"
    HOUSE = "HOUSE"
    PAYOUT = "PAYOUT"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class CommissionDirection(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
