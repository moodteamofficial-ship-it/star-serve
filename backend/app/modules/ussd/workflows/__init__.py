"""Registered USSD workflow handlers — no arbitrary code from the database."""

from app.modules.ussd.enums import UssdWorkflowAction, REGISTERED_WORKFLOWS
from app.modules.ussd.workflows.follow_up_claim import FollowUpClaimWorkflow
from app.modules.ussd.workflows.motor_quote import MotorQuoteWorkflow
from app.modules.ussd.workflows.report_claim import ReportClaimWorkflow

_HANDLERS = {
    UssdWorkflowAction.MOTOR_QUOTE.value: MotorQuoteWorkflow(),
    UssdWorkflowAction.REPORT_CLAIM.value: ReportClaimWorkflow(),
    UssdWorkflowAction.FOLLOW_UP_CLAIM.value: FollowUpClaimWorkflow(),
}


def get_workflow(action: str | None):
    if not action or action == UssdWorkflowAction.NONE.value:
        return None
    if action not in REGISTERED_WORKFLOWS:
        return None
    return _HANDLERS.get(action)


__all__ = ["get_workflow", "REGISTERED_WORKFLOWS"]
