"""Insurance provider port — provider-agnostic contract."""

from abc import ABC, abstractmethod
from typing import Any


class InsuranceProvider(ABC):
    """Star Serve business code depends only on this interface."""

    @abstractmethod
    async def check_client(self, *, id_number: str) -> dict[str, Any] | None:
        """Return normalized client dict if found, else None."""

    @abstractmethod
    async def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def check_intermediary(self, *, identification: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def register_intermediary(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_products(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_makes(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_cancellation_reasons(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def calculate_premium(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def check_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def check_double_insurance(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def check_wallet_balance(self, *, agent_code: str) -> dict[str, Any]:
        """Return provider wallet/float balance for an agent code."""

    @abstractmethod
    async def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_policy_details(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def initiate_provider_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Approve the proposal note with the insurer (Definite initiatePayment)."""

    @abstractmethod
    async def generate_certificate(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def cancel_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
