"""Abandoning an STK in the wizard must allow a fresh prompt without losing money."""

import inspect


def test_cancel_marks_only_active_attempt_as_user_cancelled() -> None:
    from app.modules.insurance.issuance_service import IssuanceService

    source = inspect.getsource(IssuanceService.cancel_pending_payment)
    assert "find_active_attempt_for_policy" in source
    assert "sync_definite_stk_confirmation" in source
    assert "USER_CANCELLED_PAYMENT" in source


def test_late_success_on_user_cancelled_prompt_still_settles() -> None:
    from app.modules.payments.service import PaymentService

    source = inspect.getsource(PaymentService.apply_webhook)
    assert "late_success_after_user_cancel" in source
    assert "USER_CANCELLED_PAYMENT" in source
    # Only a signed success may reopen a cancelled row, never a failure.
    assert "verified.success\n            and payment.status == PaymentStatus.CANCELLED.value" in source


def test_pay_prefers_any_settled_payment_before_new_prompt() -> None:
    from app.modules.insurance.issuance_service import IssuanceService

    source = inspect.getsource(IssuanceService.pay)
    assert source.index("find_success_for_policy") < source.index("payments.initiate(")
