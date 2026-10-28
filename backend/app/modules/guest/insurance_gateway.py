"""Least-privilege insurer adapter for the guest quote plane.

The guest HTTP layer never receives a raw ``InsuranceProvider``. Staff-only
Definite methods are denied here so IssuanceService / CertificateService
cannot accidentally expose them when called from GuestService.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AuthorizationError
from app.core.security.provider_config import require_configured_definite_agent
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.payments.settlement import DefinitePaymentMethod

_GUEST_PROVIDER_DENIED = "Guest cannot invoke this insurer operation"
_HOLDER_KEYS = ("Client", "ClientOID", "PolicyHolder")


def _keep_numeric_oids(payload: dict[str, Any], *keys: str) -> None:
    """Keep only integer Definite OIDs so a name/ID cannot select a holder."""
    for key in keys:
        if key not in payload:
            continue
        try:
            payload[key] = int(str(payload[key]).strip())
        except (TypeError, ValueError):
            payload.pop(key, None)

_PREMIUM_KEYS = frozenset(
    {
        "sum_insured",
        "capacity",
        "tonnage",
        "cover_period",
        "product",
        "cover_option",
        "transaction_type",
    }
)
_CLIENT_KEYS = frozenset(
    {"first_name", "last_name", "other_names", "id_number", "kra_pin", "phone", "email"}
)
_PROPOSAL_KEYS = frozenset(
    {
        "Client",
        "ClientID",
        "ClientOID",
        "PolicyHolder",
        "agent",
        "CommencementDate",
        "PaymentInterval",
        "Product",
        "CoverOption",
        "Registration",
        "MakeCode",
        "ModelCode",
        "Make",
        "Model",
        "Capacity",
        "YOM",
        "SumInsured",
        "ChassisNumber",
        "EngineNumber",
        "EngineRating",
        "Tonnage",
        "Intermediary",
        "IRA",
        "IRANumber",
    }
)
_SETTLE_KEYS = frozenset(
    {
        "InsuredItem",
        "insured_item",
        "Proposal",
        "proposal",
        "PhoneNumber",
        "phone",
        "PaymentMethod",
        "MpesaTransaction",
        "receipt",
        "reference",
        "AmountPaid",
        "amount",
        "note",
        "Narration",
        "DocumentNumber",
        "document_number",
        "noteOID",
        "NoteOID",
        "note_oid",
        "PolicyHolder",
        "Client",
        "ClientOID",
    }
)
_CERT_KEYS = frozenset(
    {
        "proposal",
        "policyId",
        "NoteOID",
        "noteOID",
        "PolicyHolder",
        "Client",
        "ClientOID",
    }
)
_GUEST_SETTLE_METHODS = frozenset(
    {int(DefinitePaymentMethod.MPESA_STK), int(DefinitePaymentMethod.WALLET)}
)


class GuestInsuranceGateway(InsuranceProvider):
    """Drop-in provider that forwards only guest-journey Definite calls."""

    def __init__(self, inner: InsuranceProvider) -> None:
        self._inner = inner

    def _deny(self) -> None:
        raise AuthorizationError(_GUEST_PROVIDER_DENIED)

    async def check_client(self, *, id_number: str) -> dict[str, Any] | None:
        return await self._inner.check_client(id_number=str(id_number).strip())

    async def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._inner.create_client(
            {key: payload[key] for key in _CLIENT_KEYS if key in payload}
        )

    async def check_intermediary(self, *, identification: str) -> dict[str, Any] | None:
        self._deny()

    async def register_intermediary(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._deny()

    async def get_products(self) -> list[dict[str, Any]]:
        return await self._inner.get_products()

    async def get_makes(self) -> list[dict[str, Any]]:
        return await self._inner.get_makes()

    async def get_cancellation_reasons(self) -> list[dict[str, Any]]:
        self._deny()

    async def calculate_premium(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._inner.calculate_premium(
            {key: params[key] for key in _PREMIUM_KEYS if key in params}
        )

    async def check_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        registration = params.get("registration") or params.get("Registration")
        return await self._inner.check_policy({"registration": registration})

    async def check_double_insurance(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._inner.check_double_insurance(
            {
                "chasis": params.get("chasis") or params.get("chassis"),
                "reg": params.get("reg") or params.get("registration"),
            }
        )

    async def check_wallet_balance(self, *, agent_code: str) -> dict[str, Any]:
        self._deny()

    async def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = {key: payload[key] for key in _PROPOSAL_KEYS if key in payload}
        # Bind the createClient OID IssuanceService loaded from the guest-owned
        # customer row. Drop non-numeric values so a name/ID cannot select a holder.
        _keep_numeric_oids(cleaned, *_HOLDER_KEYS)
        cleaned["agent"] = require_configured_definite_agent()
        return await self._inner.create_proposal(cleaned)

    async def get_policy_details(self, params: dict[str, Any]) -> dict[str, Any]:
        self._deny()

    async def initiate_provider_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Approve a note already stored on a guest-owned policy.

        Identifiers must already be server-derived. Guests cannot declare
        already-paid or credit settlement.
        """
        settings = get_settings()
        cleaned = {key: payload[key] for key in _SETTLE_KEYS if key in payload}
        raw_method = cleaned.get("PaymentMethod")
        method = int(
            DefinitePaymentMethod.WALLET if raw_method is None else raw_method
        )
        if method not in _GUEST_SETTLE_METHODS:
            raise AuthorizationError(_GUEST_PROVIDER_DENIED)
        cleaned["PaymentMethod"] = method
        cleaned["APIUser"] = settings.definite_assurance_username
        _keep_numeric_oids(cleaned, *_HOLDER_KEYS)
        return await self._inner.initiate_provider_payment(cleaned)

    async def generate_certificate(self, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = {key: payload[key] for key in _CERT_KEYS if key in payload}
        _keep_numeric_oids(cleaned, *_HOLDER_KEYS)
        return await self._inner.generate_certificate(cleaned)

    async def cancel_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._deny()
