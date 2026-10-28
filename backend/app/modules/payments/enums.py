"""Payment lifecycle enums."""

from enum import StrEnum

from app.modules.payments.settlement import AWAIT_CONFIRMATION_RAILS


class PaymentStatus(StrEnum):
    INITIATED = "INITIATED"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVERSED = "REVERSED"
    CANCELLED = "CANCELLED"


class PaymentMethod(StrEnum):
    """Canonical issuance rails plus legacy aliases kept for stored rows."""

    DEFINITE_WALLET = "DEFINITE_WALLET"
    DEFINITE_MPESA = "DEFINITE_MPESA"
    BIRDVIEW = "BIRDVIEW"
    # Legacy (mapped to Definite rails by settlement.resolve_settlement_plan)
    MPESA = "MPESA"
    WALLET = "WALLET"
    CARD = "CARD"
    BANK = "BANK"


# Rails that stay PENDING until payment is independently confirmed. Only one STK
# prompt is ever sent per payment, and reconcile is limited to these methods.
# MPESA is kept for rows written before the legacy alias was removed.
ASYNC_STK_METHODS: frozenset[str] = frozenset(
    AWAIT_CONFIRMATION_RAILS | {PaymentMethod.MPESA.value}
)

# failure_code for an STK the user abandoned in the wizard. Unlike other
# cancellations, a late signed success webhook for it is still applied.
USER_CANCELLED_PAYMENT = "USER_CANCELLED"

# A policy may have at most one of these at a time (DB unique + service lock).
ACTIVE_PAYMENT_ATTEMPT_STATUSES: frozenset[str] = frozenset(
    {PaymentStatus.INITIATED.value, PaymentStatus.PENDING.value}
)


class PaymentPurpose(StrEnum):
    POLICY_PREMIUM = "POLICY_PREMIUM"
    POLICY_EXTENSION = "POLICY_EXTENSION"
    WALLET_TOP_UP = "WALLET_TOP_UP"


class WalletTxnType(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    REVERSAL = "REVERSAL"


class CertificateStatus(StrEnum):
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"
    REVOKED = "REVOKED"
