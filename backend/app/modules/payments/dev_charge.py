"""Non-production outbound charge amounts (STK / Definite AmountPaid).

Policy premium on the payment row stays authoritative; only the external
charge is reduced so UAT/dev never moves full premium cash.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings

# Strict test debit for phones and Definite wallet / already-paid outside production.
DEFAULT_DEV_CHARGE_KES = Decimal("1.00")


def resolve_outbound_charge_kes(settings: Settings, policy_amount: Decimal) -> Decimal:
    """Amount to send to BirdView / Definite / STK providers.

    - Production: always the full policy amount (test overrides are ignored).
    - Development/staging: **always 1.00 KES**. Env knobs cannot raise this —
      UAT wallet otherwise drains the outstanding note.
    """
    full = policy_amount.quantize(Decimal("0.01"))
    if settings.is_production:
        return full
    return DEFAULT_DEV_CHARGE_KES
