"""Add commission settings and bank-style commission ledger."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_agent_commissions"
down_revision: Union[str, None] = "0033_intermediary_agent_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commission_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="KES"),
        sa.Column("payout_cadence", sa.String(length=16), nullable=False, server_default="MONTHLY"),
        sa.Column(
            "certificate_rate_percent",
            sa.Numeric(7, 4),
            nullable=False,
            server_default="0.0000",
        ),
        sa.Column(
            "claim_rate_percent",
            sa.Numeric(7, 4),
            nullable=False,
            server_default="0.0000",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", name="uq_commission_settings_tenant"),
    )
    op.create_index("ix_commission_settings_tenant_id", "commission_settings", ["tenant_id"])

    op.create_table(
        "commission_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("intermediary_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("statement_ref", sa.String(length=64), nullable=False),
        sa.Column("entry_kind", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("source_event", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="KES"),
        sa.Column("agent_code_snapshot", sa.String(length=16), nullable=True),
        sa.Column("intermediary_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("base_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("rate_percent_snapshot", sa.Numeric(7, 4), nullable=True),
        sa.Column("settings_version", sa.Integer(), nullable=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("certificate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payout_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "statement_ref",
            name="uq_commission_ledger_tenant_statement_ref",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "payment_id",
            "entry_kind",
            name="uq_commission_ledger_payment_kind",
        ),
    )
    op.create_index(
        "ix_commission_ledger_entries_tenant_id", "commission_ledger_entries", ["tenant_id"]
    )
    op.create_index(
        "ix_commission_ledger_entries_intermediary_id",
        "commission_ledger_entries",
        ["intermediary_id"],
    )
    op.create_index(
        "ix_commission_ledger_entries_payment_id", "commission_ledger_entries", ["payment_id"]
    )
    op.create_index(
        "ix_commission_ledger_entries_policy_id", "commission_ledger_entries", ["policy_id"]
    )
    op.create_index(
        "ix_commission_ledger_entries_statement_ref",
        "commission_ledger_entries",
        ["statement_ref"],
    )
    op.create_index(
        "ix_commission_ledger_entries_entry_kind", "commission_ledger_entries", ["entry_kind"]
    )
    op.create_index(
        "ix_commission_ledger_entries_occurred_at",
        "commission_ledger_entries",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("commission_ledger_entries")
    op.drop_table("commission_settings")
