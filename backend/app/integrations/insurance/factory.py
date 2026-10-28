"""Insurance provider factory — swap providers without changing business modules."""

from functools import lru_cache
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.integrations.insurance.catalog_stub import stub_makes, stub_products
from app.integrations.insurance.definite_assurance.client import DefiniteAssuranceClient
from app.integrations.insurance.definite_assurance.service import DefiniteAssuranceProvider
from app.integrations.insurance.ports import InsuranceProvider


class NullInsuranceProvider(InsuranceProvider):
    """Dev/offline stub when DA credentials are absent or UAT is unreachable.

    Returns deterministic clear checks, Definite-shaped catalog, and stub premiums
    so the quote wizard and Phase 4+ workflows work locally.
    """

    async def check_client(self, *, id_number: str) -> dict[str, Any] | None:
        return None

    async def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "external_ref": f"LOCAL-{payload.get('id_number')}",
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
            "id_number": payload.get("id_number"),
            "phone": payload.get("phone"),
            "kra_pin": payload.get("kra_pin"),
        }

    async def check_intermediary(self, *, identification: str) -> dict[str, Any] | None:
        return None

    async def register_intermediary(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "external_ref": f"LOCAL-INT-{payload.get('identification')}",
            "name": payload.get("name"),
            "identification": payload.get("identification"),
            "email": payload.get("email"),
            "phone": payload.get("phone"),
        }

    async def get_products(self) -> list[dict[str, Any]]:
        return stub_products()

    async def get_makes(self) -> list[dict[str, Any]]:
        return stub_makes()

    async def get_cancellation_reasons(self) -> list[dict[str, Any]]:
        return []

    async def calculate_premium(self, params: dict[str, Any]) -> dict[str, Any]:
        sum_insured = float(params.get("sum_insured") or 0)
        capacity = float(params.get("capacity") or 0)
        # Capacity-sensitive base for PSV / seating products; floor for TPO
        seating_component = max(capacity, 1.0) * 950.0
        value_component = sum_insured * 0.035 if sum_insured > 0 else 0.0
        basic = round(max(seating_component + value_component, 2500.0), 2)
        phcf = round(basic * 0.0025, 2)
        levy = round(basic * 0.002, 2)
        stamp = 40.0
        return {
            "basic_premium": basic,
            "phcf": phcf,
            "training_levy": levy,
            "stamp_duty": stamp,
            "gross_premium": round(basic + phcf + levy + stamp, 2),
        }

    async def check_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "CLEAR", "source": "LOCAL_STUB", "exists": False}

    async def check_double_insurance(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"hasDoubleInsurance": False, "status": "CLEAR", "source": "LOCAL_STUB"}

    async def check_wallet_balance(self, *, agent_code: str) -> dict[str, Any]:
        return {
            "agent_code": agent_code,
            "balance": 0.0,
            "currency": "KES",
            "source": "LOCAL_STUB",
        }

    async def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        oid = int(uuid4().hex[:6], 16) % 90000 + 10000
        note = oid + 50000
        amount = float(payload.get("SumInsured") or 0)
        # Prefer a seating-based stub amount if sum insured is zero
        if amount <= 0:
            capacity = float(payload.get("Capacity") or 4)
            amount = max(capacity * 950.0, 2500.0) + 40.0
        return {
            "success": True,
            "message": "Proposal created successfully",
            "proposalId": str(oid),
            "proposalDetails": {
                "OID": oid,
                "Narration": payload.get("Registration"),
                "AmountToPay": round(amount, 2),
                "InsuredItem": oid + 90000,
                "Note": note,
                "DocumentNumber": f"NW{note}",
            },
            "source": "LOCAL_STUB",
        }

    async def get_policy_details(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "OK", "source": "LOCAL_STUB", "params": params}

    async def initiate_provider_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "message": "Policy Approved. Proceed to Issue cert",
            "source": "LOCAL_STUB",
        }

    async def generate_certificate(self, payload: dict[str, Any]) -> dict[str, Any]:
        cert_no = f"C{uuid4().hex[:8].upper()}"
        return {
            "success": True,
            "certificateId": cert_no,
            "certNo": cert_no,
            # No downloadable URL — live DA returns Azure blob certURL after auth works
            "certURL": None,
            "message": "Local stub certificate (Definite UAT unavailable)",
            "source": "LOCAL_STUB",
        }

    async def cancel_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "CANCELLED", "source": "LOCAL_STUB"}


class ResilientInsuranceProvider(InsuranceProvider):
    """Prefer live Definite Assurance; fall back to stubs on auth/transport failure."""

    def __init__(self, primary: InsuranceProvider, fallback: InsuranceProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    async def check_client(self, *, id_number: str) -> dict[str, Any] | None:
        # Identity gate — never treat a provider error as "new person".
        return await self.primary.check_client(id_number=id_number)

    async def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Mutating call — do not invent a local client when DA rejects
        return await self.primary.create_client(payload)

    async def check_intermediary(self, *, identification: str) -> dict[str, Any] | None:
        try:
            return await self.primary.check_intermediary(identification=identification)
        except Exception:
            return await self.fallback.check_intermediary(identification=identification)

    async def register_intermediary(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.primary.register_intermediary(payload)

    async def get_products(self) -> list[dict[str, Any]]:
        from app.core.config import get_settings

        try:
            rows = await self.primary.get_products()
            if rows:
                return rows
            if get_settings().is_production:
                raise RuntimeError("Insurance provider returned an empty product catalog")
        except Exception:
            if get_settings().is_production:
                raise
        return await self.fallback.get_products()

    async def get_makes(self) -> list[dict[str, Any]]:
        from app.core.config import get_settings

        try:
            rows = await self.primary.get_makes()
            if rows:
                return rows
            if get_settings().is_production:
                raise RuntimeError("Insurance provider returned an empty makes catalog")
        except Exception:
            if get_settings().is_production:
                raise
        return await self.fallback.get_makes()

    async def get_cancellation_reasons(self) -> list[dict[str, Any]]:
        try:
            rows = await self.primary.get_cancellation_reasons()
            if rows:
                return rows
        except Exception:
            pass
        return await self.fallback.get_cancellation_reasons()

    async def calculate_premium(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self.primary.calculate_premium(params)
            if result.get("gross_premium") is not None:
                return result
        except Exception:
            pass
        return await self.fallback.calculate_premium(params)

    async def check_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.primary.check_policy(params)
        except Exception:
            if self._must_enforce_safety_checks():
                raise
            return await self.fallback.check_policy(params)

    async def check_double_insurance(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.primary.check_double_insurance(params)
        except Exception:
            if self._must_enforce_safety_checks():
                raise
            return await self.fallback.check_double_insurance(params)

    @staticmethod
    def _must_enforce_safety_checks() -> bool:
        from app.modules.insurance.policy_rules import should_enforce_double_insurance

        return should_enforce_double_insurance()

    async def check_wallet_balance(self, *, agent_code: str) -> dict[str, Any]:
        try:
            return await self.primary.check_wallet_balance(agent_code=agent_code)
        except Exception:
            return await self.fallback.check_wallet_balance(agent_code=agent_code)

    async def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.primary.create_proposal(payload)

    async def get_policy_details(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.primary.get_policy_details(params)
        except Exception:
            return await self.fallback.get_policy_details(params)

    async def initiate_provider_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.primary.initiate_provider_payment(payload)

    async def generate_certificate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.primary.generate_certificate(payload)

    async def cancel_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.primary.cancel_policy(payload)


@lru_cache
def get_insurance_provider() -> InsuranceProvider:
    settings = get_settings()
    stub = NullInsuranceProvider()
    if not settings.definite_assurance_username:
        return stub
    return ResilientInsuranceProvider(
        DefiniteAssuranceProvider(DefiniteAssuranceClient(settings)),
        stub,
    )


def reset_insurance_provider() -> None:
    get_insurance_provider.cache_clear()
