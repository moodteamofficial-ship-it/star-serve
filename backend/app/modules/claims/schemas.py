"""Claim API schemas — extra fields are rejected (no mass assignment)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ClaimCreateRequest(BaseModel):
    policy_id: UUID
    claim_type: str = Field(default="MOTOR", max_length=32)
    incident_date: date | None = None
    incident_time: str | None = Field(default=None, max_length=16)
    incident_location: str | None = Field(default=None, max_length=255)
    incident_description: str | None = Field(default=None, max_length=4000)
    police_abstract_number: str | None = Field(default=None, max_length=64)
    driver_name: str | None = Field(default=None, max_length=255)
    driver_license_number: str | None = Field(default=None, max_length=64)
    damage_description: str | None = Field(default=None, max_length=4000)
    injury_summary: str | None = Field(default=None, max_length=2000)
    claimed_amount: Decimal = Field(ge=0)
    beneficiary_type: str = Field(default="CLIENT", max_length=32)
    beneficiary_reference: str | None = Field(default=None, max_length=128)

    model_config = {"extra": "forbid"}


class ClaimUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    incident_date: date | None = None
    incident_time: str | None = Field(default=None, max_length=16)
    incident_location: str | None = Field(default=None, max_length=255)
    incident_description: str | None = Field(default=None, max_length=4000)
    police_abstract_number: str | None = Field(default=None, max_length=64)
    driver_name: str | None = Field(default=None, max_length=255)
    driver_license_number: str | None = Field(default=None, max_length=64)
    damage_description: str | None = Field(default=None, max_length=4000)
    injury_summary: str | None = Field(default=None, max_length=2000)
    claimed_amount: Decimal | None = Field(default=None, ge=0)
    beneficiary_type: str | None = Field(default=None, max_length=32)
    beneficiary_reference: str | None = Field(default=None, max_length=128)

    model_config = {"extra": "forbid"}


class ClaimHandoffTask(BaseModel):
    """Optional task created while assigning or starting assessment."""

    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=4000)
    followup_type: str = Field(default="INTERNAL_REVIEW", max_length=48)

    model_config = {"extra": "forbid"}


class ClaimAssignRequest(BaseModel):
    version: int = Field(ge=1)
    assigned_to_user_id: UUID
    reason: str = Field(default="MANUAL", max_length=32)
    note: str | None = Field(default=None, max_length=512)
    task: ClaimHandoffTask | None = None

    model_config = {"extra": "forbid"}


class ClaimStartVettingRequest(BaseModel):
    version: int = Field(ge=1)
    task: ClaimHandoffTask | None = None

    model_config = {"extra": "forbid"}


class ClaimVetRequest(BaseModel):
    version: int = Field(ge=1)
    decision: str = Field(max_length=32)
    decision_reason: str = Field(min_length=3, max_length=2000)
    findings: dict[str, Any] = Field(default_factory=dict)
    required_documents: list[str] = Field(default_factory=list)
    checklist: dict[str, bool] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class ClaimReasonRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)

    model_config = {"extra": "forbid"}


class ClaimVersionRequest(BaseModel):
    version: int = Field(ge=1)

    model_config = {"extra": "forbid"}


class ClaimApproveRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class ClaimNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class ClaimClientMessageRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class ClaimFollowupCreateRequest(BaseModel):
    followup_type: str = Field(default="OTHER", max_length=48)
    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=4000)
    requested_from: str | None = Field(default=None, max_length=128)
    due_at: datetime | None = None
    assigned_to_user_id: UUID | None = None

    model_config = {"extra": "forbid"}


class ClaimFollowupCompleteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)

    model_config = {"extra": "forbid"}


class ClaimAmendmentRequest(BaseModel):
    version: int = Field(ge=1)
    field_name: str = Field(pattern="^(claimed_amount|approved_amount|beneficiary_type|beneficiary_reference)$")
    proposed_value: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=3, max_length=2000)

    model_config = {"extra": "forbid"}


class ClaimAmendmentReviewRequest(BaseModel):
    version: int = Field(ge=1)
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    reason: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class ClaimInsurerDecisionRequest(BaseModel):
    version: int = Field(ge=1)
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    approved_amount: Decimal | None = Field(default=None, ge=0)
    beneficiary_type: str | None = Field(default=None, pattern="^(CLIENT|STAR_SERVE)$")
    reason: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class ClaimSettlementRequest(BaseModel):
    version: int = Field(ge=1)
    beneficiary_type: str | None = Field(default=None, pattern="^(CLIENT|STAR_SERVE)$")
    reference: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class ClaimPaymentAuthorizeRequest(BaseModel):
    version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=128)

    model_config = {"extra": "forbid"}


class ClaimPaymentExecuteRequest(BaseModel):
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)

    model_config = {"extra": "forbid"}


class ClaimCapabilities(BaseModel):
    can_view: bool = False
    can_edit: bool = False
    can_assign: bool = False
    can_vet: bool = False
    can_request_information: bool = False
    can_recommend_approval: bool = False
    can_approve: bool = False
    already_approved: bool = False
    can_reject: bool = False
    can_forward: bool = False
    can_record_insurer_decision: bool = False
    can_record_settlement: bool = False
    can_view_sensitive: bool = False
    can_upload_document: bool = False
    can_delete_document: bool = False
    can_download_document: bool = False
    can_view_notes: bool = False
    can_add_note: bool = False
    can_send_client_message: bool = False
    can_create_followup: bool = False
    can_complete_followup: bool = False
    can_authorize_payment: bool = False
    can_execute_payment: bool = False
    can_view_payment: bool = False
    can_retry_payment: bool = False
    can_close: bool = False
    can_amend: bool = False
    visible_sections: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ClaimListItem(BaseModel):
    id: str
    claim_number: str
    status: str
    claim_type: str
    policy_id: str
    customer_id: str
    customer_name: str | None = None
    agency_name: str | None = None
    vehicle_registration: str | None = None
    claimed_amount: Decimal
    approved_amount: Decimal | None
    currency: str
    assigned_to_user_id: str | None
    assigned_to_name: str | None = None
    channel: str = "STAFF"
    version: int
    created_at: datetime
    updated_at: datetime
    capabilities: ClaimCapabilities | None = None

    model_config = {"extra": "forbid"}


class ClaimEventPublic(BaseModel):
    id: str
    actor_type: str
    actor_display_name: str | None
    actor_role: str | None
    action: str
    summary: str
    previous_state: str | None
    new_state: str | None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}
