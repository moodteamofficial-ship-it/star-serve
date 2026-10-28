"""Payment API schemas — client must never send amount or success flags."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentInitiateRequest(BaseModel):
    policy_id: UUID
    # Default onto the customer-funded rail that stays PENDING until confirmed.
    # An omitted or unknown method must never settle a payment on its own.
    method: str = Field(default="BIRDVIEW", max_length=32)
    phone: str | None = Field(default=None, max_length=32)
    # Intentionally no amount — server loads policy.gross_premium

    model_config = {"extra": "forbid"}


class PaymentReceiptConfirmRequest(BaseModel):
    """Reconcile a missing STK callback using the M-Pesa SMS receipt."""

    receipt: str = Field(min_length=8, max_length=32)

    model_config = {"extra": "forbid"}


class PaymentPublic(BaseModel):
    id: str
    customer_id: str | None
    policy_id: str | None
    proposal_id: str | None
    reference: str
    purpose: str
    method: str
    currency: str
    amount: Decimal
    discount_amount: Decimal = Decimal("0")
    status: str
    phone: str | None
    provider: str
    provider_receipt: str | None
    failure_code: str | None
    failure_message: str | None
    paid_at: datetime | None
    version: int
    job_id: str | None
    created_at: datetime
    updated_at: datetime
    intermediary_id: str | None = None
    intermediary_name: str | None = None
    agent_code: str | None = None
    commission_beneficiary: str | None = None

    model_config = {"extra": "forbid"}


class WalletTopUpRequest(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(default="KES", max_length=8)
    description: str = Field(min_length=8, max_length=500)

    model_config = {"extra": "forbid"}


class WalletPublic(BaseModel):
    id: str
    currency: str
    available_balance: Decimal
    ledger_balance: Decimal
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}


class WalletTxnPublic(BaseModel):
    id: str
    reference: str
    txn_type: str
    amount: Decimal
    balance_after: Decimal
    description: str | None
    payment_id: str | None
    created_at: datetime

    model_config = {"extra": "forbid"}


class CertificatePublic(BaseModel):
    id: str
    policy_id: str
    payment_id: str | None
    customer_id: str | None
    customer_name: str | None = None
    vehicle_registration: str | None = None
    certificate_number: str
    status: str
    external_certificate_ref: str | None
    file_available: bool = False
    local_copy_available: bool = False
    local_stored_at: datetime | None = None
    content_sha256: str | None = None
    file_size_bytes: int | None = None
    access_count: int = 0
    last_accessed_at: datetime | None = None
    last_accessed_by_user_id: str | None = None
    download_url_expires_at: datetime | None = None
    generated_at: datetime | None
    failure_message: str | None
    job_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}
