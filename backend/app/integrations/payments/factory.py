"""Payment provider factory."""

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.integrations.payments.birdview.provider import BirdViewProvider
from app.integrations.payments.definite_sync.provider import DefiniteSyncPaymentProvider
from app.integrations.payments.mpesa.provider import MpesaProvider
from app.integrations.payments.ports import PaymentProvider
from app.modules.payments.enums import PaymentMethod
from app.modules.payments.settlement import SettlementRail


@lru_cache
def _mpesa() -> MpesaProvider:
    return MpesaProvider(get_settings())


@lru_cache
def _birdview() -> BirdViewProvider:
    return BirdViewProvider(get_settings())


@lru_cache
def _definite_sync() -> DefiniteSyncPaymentProvider:
    return DefiniteSyncPaymentProvider()


def get_payment_provider(method: str) -> PaymentProvider:
    normalized = method.upper()
    if normalized == PaymentMethod.MPESA.value:
        return _mpesa()
    if normalized == SettlementRail.BIRDVIEW.value:
        return _birdview()
    if normalized in {
        SettlementRail.DEFINITE_WALLET.value,
        SettlementRail.DEFINITE_MPESA.value,
    }:
        return _definite_sync()
    if normalized == PaymentMethod.WALLET.value:
        raise ValidationAppError(
            "WALLET is not a payment rail; use DEFINITE_WALLET for insurer float settlement"
        )
    raise ValidationAppError(f"Unsupported payment method: {method}")


def reset_payment_providers() -> None:
    _mpesa.cache_clear()
    _birdview.cache_clear()
    _definite_sync.cache_clear()
