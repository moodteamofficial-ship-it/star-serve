"""DefiniteAssuranceProvider — InsuranceProvider adapter."""

from decimal import Decimal
from typing import Any

from app.integrations.insurance.definite_assurance.client import DefiniteAssuranceClient
from app.integrations.insurance.definite_assurance import mapper
from app.integrations.insurance.definite_assurance.schemas import (
    DAClientCreate,
    DAIntermediaryCreate,
    DAPremiumParams,
)
from app.integrations.insurance.ports import InsuranceProvider


class DefiniteAssuranceProvider(InsuranceProvider):
    def __init__(self, client: DefiniteAssuranceClient | None = None) -> None:
        self.client = client or DefiniteAssuranceClient()

    async def check_client(self, *, id_number: str) -> dict[str, Any] | None:
        from app.integrations.insurance.definite_assurance.exceptions import (
            DefiniteAssuranceError,
        )

        payload = await self.client.get("checkClient", params={"IDNumber": id_number})
        status = mapper.classify_client_lookup(payload)
        if status == "ABSENT":
            return None
        if status == "FOUND":
            return mapper.map_client(payload)
        raise DefiniteAssuranceError("Insurance provider returned an unreadable client lookup")

    async def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        email = str(payload.get("email") or "").strip().lower() or None
        body = DAClientCreate(
            firstName=payload["first_name"],
            lastName=payload["last_name"],
            otherNames=payload.get("other_names"),
            idNumber=payload["id_number"],
            pin=payload.get("kra_pin"),
            phone=payload["phone"],
            email=email,
        )
        result = await self.client.post("createClient", json_body=body.model_dump(exclude_none=True))
        mapped = mapper.map_client(result) or {}
        return mapped

    async def check_intermediary(self, *, identification: str) -> dict[str, Any] | None:
        payload = await self.client.get(
            "checkIntermediary", params={"identification": identification}
        )
        return mapper.map_intermediary(payload)

    async def register_intermediary(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = DAIntermediaryCreate(
            name=payload["name"],
            email=payload["email"],
            phone=payload["phone"],
            identification=payload["identification"],
            krapin=payload.get("kra_pin"),
        )
        result = await self.client.post(
            "registerIntermediary", json_body=body.model_dump(exclude_none=True)
        )
        return mapper.map_intermediary(result) or {}

    async def get_products(self) -> list[dict[str, Any]]:
        payload = await self.client.get("products")
        return mapper.map_products(payload)

    async def get_makes(self) -> list[dict[str, Any]]:
        payload = await self.client.get("makes")
        return mapper.map_makes(payload)

    async def get_cancellation_reasons(self) -> list[dict[str, Any]]:
        payload = await self.client.get("getCancellationReasons")
        return mapper.map_cancellation_reasons(payload)

    async def calculate_premium(self, params: dict[str, Any]) -> dict[str, Any]:
        from app.integrations.insurance.definite_assurance.exceptions import (
            DefiniteAssuranceError,
            DefiniteAssuranceValidationError,
        )

        period = definite_cover_period(str(params.get("cover_period") or ""))
        # Definite's calculatePremium halves "Monthly", but newProposal (and their portal)
        # bill the "Annually" figure for that cover option, so quote what is billed.
        priced_period = "Annually" if period == "Monthly" else period
        query = DAPremiumParams(
            sumInsured=params["sum_insured"],
            capacity=params.get("capacity"),
            tonnage=params.get("tonnage"),
            coverPeriod=priced_period,
            product=str(params["product"]),
            coverOption=str(params["cover_option"]),
            transactionType=str(params["transaction_type"]),
        )
        try:
            payload = await self.client.get(
                "calculatePremium",
                params=query.model_dump(exclude_none=True),
                retryable=False,
            )
        except DefiniteAssuranceError as exc:
            raise DefiniteAssuranceValidationError(
                "Definite could not price this cover for the selected period",
                details=[{"cover_period": period}],
            ) from exc
        mapped = mapper.map_premium(payload if isinstance(payload, dict) else {})
        if mapped.get("gross_premium") is None:
            raise DefiniteAssuranceValidationError(
                "Definite has no premium for this cover and period. Try another period.",
                details=[{"cover_period": period}],
            )
        mapped["cover_period_used"] = period
        return mapped

    async def check_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.client.get("checkPolicy", params=params, retryable=True)
        return payload if isinstance(payload, dict) else {"data": payload}

    async def check_double_insurance(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.client.get("checkDoubleInsurance", params=params, retryable=True)
        return payload if isinstance(payload, dict) else {"data": payload}

    async def check_wallet_balance(self, *, agent_code: str) -> dict[str, Any]:
        payload = await self.client.get(
            "checkWalletBalance",
            params={"agentCode": agent_code},
            retryable=True,
        )
        # Definite returns [{ "Balance": 6901.0156 }]
        rows = payload if isinstance(payload, list) else (
            payload.get("data") if isinstance(payload, dict) else None
        )
        balance = None
        if isinstance(rows, list) and rows:
            first = rows[0] if isinstance(rows[0], dict) else {}
            raw = first.get("Balance", first.get("balance"))
            if raw is not None:
                balance = float(raw)
        elif isinstance(payload, dict):
            raw = payload.get("Balance", payload.get("balance"))
            if raw is not None:
                balance = float(raw)
        return {
            "agent_code": agent_code,
            "balance": balance,
            "currency": "KES",
            "raw": payload,
        }

    async def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        # No PaymentInterval fallback: a proposal must bill the period that was quoted.
        result = await self.client.post("newProposal", json_body=payload)
        return result if isinstance(result, dict) else {"data": result}

    async def get_policy_details(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.client.get("getPolicyDetails", params=params, retryable=True)
        return payload if isinstance(payload, dict) else {"data": payload}

    async def initiate_provider_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Approve a Definite proposal note with exactly one initiatePayment POST.

        UAT's MSSQL layer treats JSON number AmountPaid as NULL and string as valid —
        sending int then retrying string caused **two STK prompts**. UAT always sends
        a string AmountPaid=1. LIVE (digitalapi) requires the real premium as an int —
        even when StarServe ``APP_ENV`` is staging.
        """
        from app.core.config import get_settings

        settings = get_settings()
        from app.core.exceptions import ValidationAppError

        phone_raw = payload.get("PhoneNumber") or payload.get("phone")
        if not phone_raw:
            if settings.is_production or not settings.definite_is_uat:
                raise ValidationAppError("Phone number is required for Definite settlement")
            phone_raw = settings.definite_assurance_test_phone
        phone = _normalize_da_phone(phone_raw)
        if (settings.is_production or not settings.definite_is_uat) and (
            not phone or phone == "254700000001"
        ):
            raise ValidationAppError("Phone number is required for Definite settlement")
        amount_raw = payload.get("AmountPaid") if payload.get("AmountPaid") is not None else payload.get("amount")
        try:
            amount_num = float(amount_raw or 0)
        except (TypeError, ValueError):
            amount_num = 0.0
        method_code = int(payload.get("PaymentMethod") or 1)
        # UAT only: AmountPaid=1. LIVE digitalapi rejects underpaid notes at
        # generateCertificate (often as ER001 / "try again later").
        if settings.definite_is_uat:
            from app.modules.payments.dev_charge import resolve_outbound_charge_kes

            amount_num = float(
                resolve_outbound_charge_kes(settings, Decimal(str(amount_num or 0)))
            )
            amount_int = 1
            amount_paid: int | str = str(amount_int)
        else:
            amount_int = int(round(amount_num))
            if amount_int < 1:
                raise ValidationAppError("Amount paid must be a positive premium")
            amount_paid = amount_int

        mpesa_txn = str(
            payload.get("MpesaTransaction")
            or payload.get("receipt")
            or payload.get("reference")
            or ""
        ).strip()[:20]
        body = {
            "InsuredItem": _as_int(payload.get("InsuredItem") or payload.get("insured_item")),
            "Proposal": _as_int(payload.get("Proposal") or payload.get("proposal")),
            "PhoneNumber": phone,
            "APIUser": payload.get("APIUser") or settings.definite_assurance_username,
            "PaymentMethod": method_code,
            "MpesaTransaction": mpesa_txn,
            "AmountPaid": amount_paid,
            "note": payload.get("note") or payload.get("Narration") or "",
            "DocumentNumber": payload.get("DocumentNumber") or payload.get("document_number") or "",
            "noteOID": _as_int(payload.get("noteOID") or payload.get("NoteOID") or payload.get("note_oid")),
        }
        holder = _as_int(
            payload.get("PolicyHolder") or payload.get("Client") or payload.get("ClientOID")
        )
        if holder is not None:
            body["PolicyHolder"] = holder
            body["Client"] = holder
            body["ClientOID"] = holder
        email = str(payload.get("email") or payload.get("Email") or "").strip().lower()
        if email:
            # LIVE may validate holder contact on settle even when createClient omitted it.
            body["email"] = email
            body["Email"] = email
        result = await self.client.post("initiatePayment", json_body=body)
        return result if isinstance(result, dict) else {"data": result}

    async def generate_certificate(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Definite expects proposal OID + NoteOID from newProposal / extension
        body = {
            "proposal": _as_int(payload.get("proposal") or payload.get("policyId")),
            "NoteOID": _as_int(payload.get("NoteOID") or payload.get("noteOID")),
        }
        if body["proposal"] is None or body["NoteOID"] is None:
            raise ValueError("generateCertificate requires proposal and NoteOID")
        holder = _as_int(
            payload.get("PolicyHolder") or payload.get("Client") or payload.get("ClientOID")
        )
        if holder is not None:
            body["PolicyHolder"] = holder
            body["Client"] = holder
            body["ClientOID"] = holder
        email = str(payload.get("email") or payload.get("Email") or "").strip().lower()
        if email:
            # LIVE returns "email is required" when the Definite client was created without one.
            # Forward the StarServe customer email so retries of paid policies can succeed.
            body["email"] = email
            body["Email"] = email
        result = await self.client.post("generateCertificate", json_body=body)
        return result if isinstance(result, dict) else {"data": result}

    async def cancel_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.post("cancelPolicy", json_body=payload)
        return result if isinstance(result, dict) else {"data": result}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_da_phone(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if digits.startswith("254"):
        return digits
    if len(digits) == 9:
        return "254" + digits
    return digits


def definite_cover_period(cover_period: str) -> str:
    """Definite only prices ``Monthly``, ``2installments`` and ``Annually`` (case-sensitive)."""
    from app.core.exceptions import ValidationAppError

    normalized = cover_period.strip().lower().replace(" ", "").replace("-", "")
    if normalized in {"monthly", "month"}:
        return "Monthly"
    if normalized in {"2installments", "twoinstallments", "semiannual", "semi"}:
        return "2installments"
    if normalized in {"annually", "annual", "yearly", "year"}:
        return "Annually"
    raise ValidationAppError("Choose a cover period: Monthly, Semi-annual or Annual")
