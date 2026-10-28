"""USSD config validation and workflow registry."""

import pytest

from app.core.exceptions import ValidationAppError
from app.modules.ussd.enums import REGISTERED_WORKFLOWS, UssdWorkflowAction
from app.modules.ussd.seed import default_menu_definition
from app.modules.ussd.service import UssdAdminService
from app.modules.ussd.workflows import get_workflow


def test_registered_workflows_are_bound():
    assert UssdWorkflowAction.MOTOR_QUOTE.value in REGISTERED_WORKFLOWS
    assert get_workflow("MOTOR_QUOTE") is not None
    assert get_workflow("REPORT_CLAIM") is not None
    assert get_workflow("FOLLOW_UP_CLAIM") is not None
    assert get_workflow("NONE") is None
    assert get_workflow("DROP_TABLE") is None


def test_validate_definition_rejects_unknown_workflow():
    service = UssdAdminService(session=None, ctx=None)  # type: ignore[arg-type]
    definition = default_menu_definition()
    definition["screens"]["main"]["options"][0]["workflow_action"] = "EXEC_SHELL"
    with pytest.raises(ValidationAppError):
        service._validate_definition(definition, "main")


def test_validate_definition_rejects_hyphen_in_label():
    service = UssdAdminService(session=None, ctx=None)  # type: ignore[arg-type]
    definition = default_menu_definition()
    definition["screens"]["main"]["options"][0]["label"] = "Motor-Insurance"
    with pytest.raises(ValidationAppError):
        service._validate_definition(definition, "main")


def test_validate_definition_accepts_default_menu():
    service = UssdAdminService(session=None, ctx=None)  # type: ignore[arg-type]
    service._validate_definition(default_menu_definition(), "main")
