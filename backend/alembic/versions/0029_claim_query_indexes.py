"""Composite indexes for claim desk filters and guest duplicate checks."""

from typing import Sequence, Union

from alembic import op

revision: str = "0029_claim_query_indexes"
down_revision: Union[str, None] = "0028_guest_claim_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.create_index(
        "ix_claims_tenant_status_updated",
        "claims",
        ["tenant_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_claims_tenant_assignee_updated",
        "claims",
        ["tenant_id", "assigned_to_user_id", "updated_at"],
    )
    op.create_index(
        "ix_claims_tenant_policy_status",
        "claims",
        ["tenant_id", "policy_id", "status"],
    )
    op.create_index(
        "ix_claims_guest_intake",
        "claims",
        ["tenant_id", "channel", "assigned_to_user_id", "status"],
    )
    op.create_index(
        "ix_claim_vettings_claim_current",
        "claim_vettings",
        ["claim_id", "is_current"],
    )
    op.create_index(
        "ix_claim_followups_claim_status",
        "claim_followups",
        ["claim_id", "status"],
    )
    op.create_index(
        "ix_claim_notes_claim_visibility_created",
        "claim_notes",
        ["claim_id", "visibility", "created_at"],
    )
    op.create_index(
        "ix_claim_assignments_claim_ended",
        "claim_assignments",
        ["claim_id", "ended_at"],
    )


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.drop_index("ix_claim_assignments_claim_ended", table_name="claim_assignments")
    op.drop_index("ix_claim_notes_claim_visibility_created", table_name="claim_notes")
    op.drop_index("ix_claim_followups_claim_status", table_name="claim_followups")
    op.drop_index("ix_claim_vettings_claim_current", table_name="claim_vettings")
    op.drop_index("ix_claims_guest_intake", table_name="claims")
    op.drop_index("ix_claims_tenant_policy_status", table_name="claims")
    op.drop_index("ix_claims_tenant_assignee_updated", table_name="claims")
    op.drop_index("ix_claims_tenant_status_updated", table_name="claims")
