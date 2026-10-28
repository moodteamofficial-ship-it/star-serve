"""Payment provider port — M-Pesa / Card / Bank / Wallet adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class PaymentInitResult:
    provider_checkout_id: str
    status: str  # PENDING / SUCCESS
    raw: dict[str, Any] = field(default_factory=dict)
    receipt: str | None = None


@dataclass(slots=True)
class WebhookVerificationResult:
    valid: bool
    reference: str | None = None
    checkout_id: str | None = None
    receipt: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    success: bool = False
    failure_code: str | None = None
    failure_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    # True when result_code / success is covered by a provider signature.
    outcome_authenticated: bool = False
    # Which field the provider proof actually bound. Only that field may be
    # used to look the payment up.
    identity_kind: str = "reference"


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    async def initiate(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        phone: str | None,
        metadata: dict[str, Any],
    ) -> PaymentInitResult:
        raise NotImplementedError

    @abstractmethod
    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookVerificationResult:
        raise NotImplementedError
