"""Professional claims workflow, authority, and append-only timeline."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_claims_management"
down_revision: Union[str, None] = "0026_notification_branch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_PREDICATE = """
  current_setting('app.rls_bypass', true) = 'true'
  OR current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""

CLAIM_TABLES = (
    "claims",
    "claim_assignments",
    "claim_vettings",
    "claim_external_reviews",
    "claim_amendments",
    "claim_approvals",
    "approval_policies",
    "segregation_policies",
    "claim_duty_actions",
    "claim_payments",
    "claim_followups",
    "claim_notes",
    "claim_documents",
    "claim_document_accesses",
    "claim_events",
    "claim_webhook_receipts",
)

PERMISSIONS = [
    ("claim:create", "Open a new claim"),
    ("claim:read", "Read accessible claims"),
    ("claim:update", "Edit unlocked claim fields"),
    ("claim:assign", "Assign a claim owner"),
    ("claim:vet", "Vet a submitted claim"),
    ("claim:request_information", "Request additional claim information"),
    ("claim:recommend_approval", "Recommend a claim for approval"),
    ("claim:approve", "Approve a vetted claim"),
    ("claim:reject", "Reject a claim"),
    ("claim:forward", "Forward a passed claim to Definite"),
    ("claim:view_sensitive", "View medical, identity, and risk fields"),
    ("claim:document:upload", "Upload claim documents"),
    ("claim:document:delete", "Remove claim documents"),
    ("claim:document:download", "Download claim documents"),
    ("claim:note:read", "Read internal claim notes"),
    ("claim:note:create", "Add internal claim notes"),
    ("claim:client:message", "Send a client claim message"),
    ("claim:followup:create", "Create claim follow-ups"),
    ("claim:followup:complete", "Complete claim follow-ups"),
    ("claim:payment:authorize", "Authorize a claim payment"),
    ("claim:payment:execute", "Execute an authorized claim payment"),
    ("claim:payment:read", "View claim payment details"),
    ("claim:payment:retry", "Retry a failed claim payment"),
    ("claim:close", "Close a settled claim"),
    ("claim:supervise", "See claims beyond personal assignment"),
    ("claim:override_workflow", "Privileged workflow override (audited)"),
    ("claim:override_assignment", "Act on a claim without assignment (audited)"),
    ("claim:override_approval_limit", "Override configured approval limits (audited)"),
    ("claim:override_sod", "Override segregation of duties (audited)"),
]


def _ts() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
        USING ({_TENANT_PREDICATE})
        """
    )
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")

    created, updated = _ts()
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("claim_number", sa.String(32), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False, server_default="MOTOR"),
        sa.Column("status", sa.String(48), nullable=False, server_default="CLAIM_DRAFT"),
        sa.Column("channel", sa.String(16), nullable=False, server_default="STAFF"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("incident_date", sa.Date()),
        sa.Column("incident_time", sa.String(16)),
        sa.Column("incident_location", sa.String(255)),
        sa.Column("incident_description", sa.Text()),
        sa.Column("police_abstract_number", sa.String(64)),
        sa.Column("vehicle_registration", sa.String(32)),
        sa.Column("vehicle_make", sa.String(64)),
        sa.Column("vehicle_model", sa.String(128)),
        sa.Column("chassis_number", sa.String(64)),
        sa.Column("driver_name", sa.String(255)),
        sa.Column("driver_license_number", sa.String(64)),
        sa.Column("damage_description", sa.Text()),
        sa.Column("injury_summary", sa.Text()),
        sa.Column("medical_notes", sa.Text()),
        sa.Column("risk_assessment", sa.Text()),
        sa.Column("claimed_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("approved_amount", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("beneficiary_type", sa.String(32), nullable=False, server_default="CLIENT"),
        sa.Column("beneficiary_reference", sa.String(128)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("job_id", sa.String(64)),
        sa.Column("correlation_id", sa.String(64)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "claim_number", name="uq_claims_tenant_number"),
        sa.CheckConstraint("claimed_amount >= 0", name="claimed_amount_nonneg"),
        sa.CheckConstraint("approved_amount IS NULL OR approved_amount >= 0", name="approved_amount_nonneg"),
        sa.CheckConstraint("version >= 1", name="claim_version_positive"),
    )
    for col in (
        "tenant_id",
        "branch_id",
        "customer_id",
        "policy_id",
        "assigned_to_user_id",
        "claim_number",
        "status",
        "vehicle_registration",
        "job_id",
    ):
        op.create_index(f"ix_claims_{col}", "claims", [col])

    created, updated = _ts()
    op.create_table(
        "claim_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("note", sa.String(512)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_claim_assignments_claim_id", "claim_assignments", ["claim_id"])

    created, updated = _ts()
    op.create_table(
        "claim_vettings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("decision", sa.String(32)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("findings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("required_documents", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("checklist", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_claim_vettings_claim_id", "claim_vettings", ["claim_id"])

    created, updated = _ts()
    op.create_table(
        "claim_external_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="DEFINITE"),
        sa.Column("external_reference", sa.String(128), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("response_received_at", sa.DateTime(timezone=True)),
        sa.Column("decision", sa.String(32)),
        sa.Column("response_payload_reference", sa.String(128)),
        sa.Column("approved_amount", sa.Numeric(14, 2)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "tenant_id", "provider", "external_reference", name="uq_claim_external_reviews_ref"
        ),
    )
    op.create_index("ix_claim_external_reviews_ref", "claim_external_reviews", ["external_reference"])

    created, updated = _ts()
    op.create_table(
        "claim_amendments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("previous_value", sa.Text()),
        sa.Column("proposed_value", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="REQUESTED"),
        sa.Column("reason", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.Text()),
        sa.Column("amendment_id", postgresql.UUID(as_uuid=True)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["amendment_id"], ["claim_amendments.id"], ondelete="SET NULL"),
    )

    created, updated = _ts()
    op.create_table(
        "approval_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("minimum_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("maximum_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False, server_default="MOTOR"),
        sa.Column("requires_second_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("second_approval_above", sa.Numeric(14, 2)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
    )

    created, updated = _ts()
    op.create_table(
        "segregation_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_duty", sa.String(48), nullable=False),
        sa.Column("right_duty", sa.String(48), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "left_duty", "right_duty", name="uq_segregation_policies_pair"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_duty_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("duty", sa.String(48), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("claim_id", "duty", "user_id", name="uq_claim_duty_actions_user"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("beneficiary_type", sa.String(32), nullable=False, server_default="CLIENT"),
        sa.Column("beneficiary_reference", sa.String(128)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("payment_status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("authorized_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("executed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provider", sa.String(64)),
        sa.Column("provider_reference", sa.String(128)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("initiated_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("authorized_at", sa.DateTime(timezone=True)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_claim_payments_idempotency"),
        sa.CheckConstraint("amount > 0", name="claim_payment_amount_positive"),
    )
    op.create_index(
        "uq_claim_payments_active",
        "claim_payments",
        ["claim_id"],
        unique=True,
        postgresql_where=sa.text(
            "payment_status IN ('DRAFT', 'PENDING_AUTHORIZATION', 'AUTHORIZED', 'PROCESSING')"
        ),
    )

    created, updated = _ts()
    op.create_table(
        "claim_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("followup_type", sa.String(48), nullable=False, server_default="OTHER"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("requested_from", sa.String(128)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="INTERNAL"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(32), nullable=False, server_default="OTHER"),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(128), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_document_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("access_kind", sa.String(16), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_id", sa.String(64)),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["claim_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )

    created, updated = _ts()
    op.create_table(
        "claim_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_role", sa.String(64)),
        sa.Column("actor_display_name", sa.String(255)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(512), nullable=False),
        sa.Column("previous_state", sa.String(48)),
        sa.Column("new_state", sa.String(48)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_claim_events_claim_id", "claim_events", ["claim_id"])
    op.create_index("ix_claim_events_action", "claim_events", ["action"])

    created, updated = _ts()
    op.create_table(
        "claim_webhook_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("timestamp_header", sa.String(64)),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("external_reference", sa.String(128)),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True)),
        sa.Column("result", sa.String(32), nullable=False, server_default="ACCEPTED"),
        sa.Column("detail", sa.String(255)),
        created,
        updated,
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("provider", "nonce", name="uq_claim_webhook_receipts_nonce"),
    )

    op.execute(
        """
        CREATE FUNCTION prevent_claim_event_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'claim_events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_events_immutable
        BEFORE UPDATE OR DELETE ON claim_events
        FOR EACH ROW EXECUTE FUNCTION prevent_claim_event_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_document_accesses_immutable
        BEFORE UPDATE OR DELETE ON claim_document_accesses
        FOR EACH ROW EXECUTE FUNCTION prevent_claim_event_mutation()
        """
    )

    for table in CLAIM_TABLES:
        _rls(table)

    for code, description in PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (id, code, description, category, created_at, updated_at)
                VALUES (gen_random_uuid(), :code, :description, 'claim', now(), now())
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, description=description)
        )

    op.execute(
        """
        INSERT INTO roles (id, tenant_id, code, name, is_system, status, created_at, updated_at)
        SELECT gen_random_uuid(), t.id, v.code, v.name, true, 'ACTIVE', now(), now()
        FROM tenants t
        CROSS JOIN (
          VALUES
            ('claims_agent', 'Claims Agent'),
            ('claims_officer', 'Claims Officer'),
            ('senior_claims_officer', 'Senior Claims Officer'),
            ('claims_manager', 'Claims Manager'),
            ('finance_manager', 'Finance Manager'),
            ('payment_officer', 'Payment Officer')
        ) AS v(code, name)
        WHERE NOT EXISTS (
          SELECT 1 FROM roles r
          WHERE r.tenant_id = t.id AND r.code = v.code AND r.deleted_at IS NULL
        )
        """
    )

    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
        SELECT gen_random_uuid(), r.id, p.id, now(), now()
        FROM roles r
        JOIN permissions p ON p.category = 'claim'
        WHERE r.deleted_at IS NULL
          AND p.code NOT LIKE 'claim:override_%'
          AND (
            r.code = 'agency_admin'
            OR (r.code IN ('agent', 'claims_agent') AND p.code IN (
              'claim:create','claim:read','claim:update','claim:document:upload',
              'claim:document:download','claim:client:message','claim:followup:create'
            ))
            OR (r.code = 'claims_officer' AND p.code NOT IN (
              'claim:approve','claim:forward','claim:payment:authorize','claim:payment:execute',
              'claim:payment:retry','claim:close','claim:supervise','claim:assign',
              'claim:document:delete','claim:view_sensitive'
            ))
            OR (r.code = 'senior_claims_officer' AND p.code NOT IN (
              'claim:forward','claim:payment:authorize','claim:payment:execute',
              'claim:payment:retry','claim:close','claim:document:delete'
            ))
            OR (r.code = 'claims_manager' AND p.code NOT LIKE 'claim:payment:%')
            OR (r.code IN ('finance_officer', 'finance_manager') AND p.code IN (
              'claim:read','claim:supervise','claim:payment:read','claim:payment:authorize',
              'claim:payment:retry'
            ))
            OR (r.code = 'payment_officer' AND p.code IN (
              'claim:read','claim:supervise','claim:payment:read','claim:payment:execute'
            ))
            OR (r.code = 'auditor' AND p.code IN (
              'claim:read','claim:supervise','claim:note:read','claim:payment:read',
              'claim:document:download'
            ))
            OR (r.code = 'branch_manager' AND p.code IN (
              'claim:create','claim:read','claim:update','claim:assign','claim:vet',
              'claim:request_information','claim:document:upload','claim:document:download',
              'claim:note:read','claim:note:create','claim:client:message',
              'claim:followup:create','claim:supervise'
            ))
          )
          AND NOT EXISTS (
            SELECT 1 FROM role_permissions x
            WHERE x.role_id = r.id AND x.permission_id = p.id
          )
        """
    )

    op.execute(
        """
        INSERT INTO approval_policies (
          id, tenant_id, role_id, minimum_amount, maximum_amount, claim_type,
          requires_second_approval, second_approval_above, active, created_at, updated_at
        )
        SELECT gen_random_uuid(), r.tenant_id, r.id, v.min, v.max, 'MOTOR', v.dual, v.threshold, true, now(), now()
        FROM roles r
        JOIN (
          VALUES
            ('claims_officer', 0, 50000, false, NULL::numeric),
            ('senior_claims_officer', 0, 250000, false, NULL::numeric),
            ('claims_manager', 0, 1000000, true, 500000)
        ) AS v(code, min, max, dual, threshold) ON v.code = r.code
        WHERE r.tenant_id IS NOT NULL
          AND r.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM approval_policies p
            WHERE p.tenant_id = r.tenant_id AND p.role_id = r.id
          )
        """
    )

    op.execute(
        """
        INSERT INTO segregation_policies (
          id, tenant_id, left_duty, right_duty, allowed, active, created_at, updated_at
        )
        SELECT gen_random_uuid(), t.id, v.left_duty, v.right_duty, false, true, now(), now()
        FROM tenants t
        CROSS JOIN (
          VALUES
            ('VET', 'APPROVE'),
            ('VET', 'AUTHORIZE_PAYMENT'),
            ('VET', 'EXECUTE_PAYMENT'),
            ('APPROVE', 'AUTHORIZE_PAYMENT'),
            ('APPROVE', 'EXECUTE_PAYMENT'),
            ('AUTHORIZE_PAYMENT', 'EXECUTE_PAYMENT'),
            ('VET', 'MARK_PAYMENT_SUCCESS'),
            ('APPROVE', 'MARK_PAYMENT_SUCCESS'),
            ('AUTHORIZE_PAYMENT', 'MARK_PAYMENT_SUCCESS'),
            ('EXECUTE_PAYMENT', 'MARK_PAYMENT_SUCCESS')
        ) AS v(left_duty, right_duty)
        WHERE NOT EXISTS (
          SELECT 1 FROM segregation_policies s
          WHERE s.tenant_id = t.id AND s.left_duty = v.left_duty AND s.right_duty = v.right_duty
        )
        """
    )


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute("DROP TRIGGER IF EXISTS claim_events_immutable ON claim_events")
    op.execute("DROP TRIGGER IF EXISTS claim_document_accesses_immutable ON claim_document_accesses")
    op.execute("DROP FUNCTION IF EXISTS prevent_claim_event_mutation()")
    for table in reversed(CLAIM_TABLES):
        op.drop_table(table)
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE category = 'claim')")
    op.execute("DELETE FROM permissions WHERE category = 'claim'")
