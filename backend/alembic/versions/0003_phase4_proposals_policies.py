"""Phase 4: proposals and policies."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase4_proposals_policies"
down_revision: Union[str, None] = "0002_phase2_customers_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intermediary_id", postgresql.UUID(as_uuid=True)),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("product_code", sa.String(64), nullable=False),
        sa.Column("cover_option", sa.String(128), nullable=False),
        sa.Column("cover_period", sa.String(64), nullable=False),
        sa.Column("transaction_type", sa.String(64), nullable=False),
        sa.Column("vehicle_registration", sa.String(32), nullable=False),
        sa.Column("vehicle_make", sa.String(64), nullable=False),
        sa.Column("vehicle_model", sa.String(128)),
        sa.Column("vehicle_year", sa.Integer()),
        sa.Column("sum_insured", sa.Numeric(14, 2), nullable=False),
        sa.Column("capacity", sa.Numeric(14, 2)),
        sa.Column("tonnage", sa.Numeric(14, 2)),
        sa.Column("basic_premium", sa.Numeric(14, 2)),
        sa.Column("phcf", sa.Numeric(14, 2)),
        sa.Column("training_levy", sa.Numeric(14, 2)),
        sa.Column("stamp_duty", sa.Numeric(14, 2)),
        sa.Column("gross_premium", sa.Numeric(14, 2)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_proposal_ref", sa.String(128)),
        sa.Column("double_insurance_clear", sa.Boolean(), nullable=True),
        sa.Column(
            "double_insurance_result",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "policy_check_result",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cover_start_date", sa.Date()),
        sa.Column("cover_end_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("job_id", sa.String(64)),
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
    op.create_index("ix_proposals_tenant_id", "proposals", ["tenant_id"])
    op.create_index("ix_proposals_customer_id", "proposals", ["customer_id"])
    op.create_index("ix_proposals_status", "proposals", ["status"])
    op.create_index("ix_proposals_vehicle_registration", "proposals", ["vehicle_registration"])
    op.create_index("ix_proposals_product_code", "proposals", ["product_code"])
    op.create_index("ix_proposals_job_id", "proposals", ["job_id"])
    # One open proposal per tenant+vehicle+product (excludes terminal statuses)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_proposals_open_vehicle_product
        ON proposals (tenant_id, vehicle_registration, product_code)
        WHERE status IN (
          'DRAFT', 'PREMIUM_CALCULATED', 'DOUBLE_INSURANCE_CHECKED',
          'SUBMITTED', 'APPROVED'
        )
        """
    )

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("intermediary_id", postgresql.UUID(as_uuid=True)),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("policy_number", sa.String(64), nullable=False),
        sa.Column("product_code", sa.String(64), nullable=False),
        sa.Column("cover_option", sa.String(128), nullable=False),
        sa.Column("vehicle_registration", sa.String(32), nullable=False),
        sa.Column("vehicle_make", sa.String(64)),
        sa.Column("vehicle_model", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("gross_premium", sa.Numeric(14, 2)),
        sa.Column("sum_insured", sa.Numeric(14, 2)),
        sa.Column("cover_start_date", sa.Date()),
        sa.Column("cover_end_date", sa.Date()),
        sa.Column("external_policy_ref", sa.String(128)),
        sa.Column("certificate_ref", sa.String(128)),
        sa.Column("cancellation_reason_code", sa.String(64)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "provider_payload_summary",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text()),
        sa.Column("job_id", sa.String(64)),
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
        sa.UniqueConstraint("tenant_id", "policy_number", name="uq_policies_tenant_policy_number"),
    )
    op.create_index("ix_policies_tenant_id", "policies", ["tenant_id"])
    op.create_index("ix_policies_customer_id", "policies", ["customer_id"])
    op.create_index("ix_policies_proposal_id", "policies", ["proposal_id"])
    op.create_index("ix_policies_status", "policies", ["status"])
    op.create_index("ix_policies_vehicle_registration", "policies", ["vehicle_registration"])
    op.create_index("ix_policies_policy_number", "policies", ["policy_number"])
    op.create_index("ix_policies_job_id", "policies", ["job_id"])

    for table in ("proposals", "policies"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
              current_setting('app.is_platform_admin', true) = 'true'
              OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
            )
            """
        )


def downgrade() -> None:
    op.drop_table("policies")
    op.drop_table("proposals")
