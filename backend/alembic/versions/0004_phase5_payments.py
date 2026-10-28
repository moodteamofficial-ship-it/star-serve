"""Phase 5: payments, wallets, certificates."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase5_payments"
down_revision: Union[str, None] = "0003_phase4_proposals_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True)),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_checkout_id", sa.String(128)),
        sa.Column("provider_receipt", sa.String(128)),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("job_id", sa.String(64)),
        sa.Column("idempotency_key", sa.String(128)),
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
        sa.UniqueConstraint("tenant_id", "reference", name="uq_payments_tenant_reference"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_policy_id", "payments", ["policy_id"])
    op.create_index("ix_payments_proposal_id", "payments", ["proposal_id"])
    op.create_index("ix_payments_reference", "payments", ["reference"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_provider_checkout_id", "payments", ["provider_checkout_id"])
    op.create_index("ix_payments_job_id", "payments", ["job_id"])
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"])

    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column(
            "available_balance",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "ledger_balance",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("tenant_id", name="uq_wallets_tenant"),
    )
    op.create_index("ix_wallets_tenant_id", "wallets", ["tenant_id"])

    op.create_table(
        "wallet_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("txn_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.UniqueConstraint(
            "tenant_id", "reference", name="uq_wallet_transactions_tenant_reference"
        ),
    )
    op.create_index("ix_wallet_transactions_tenant_id", "wallet_transactions", ["tenant_id"])
    op.create_index("ix_wallet_transactions_wallet_id", "wallet_transactions", ["wallet_id"])
    op.create_index("ix_wallet_transactions_payment_id", "wallet_transactions", ["payment_id"])

    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("certificate_number", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_certificate_ref", sa.String(128)),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("download_url_expires_at", sa.DateTime(timezone=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("failure_message", sa.Text()),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.UniqueConstraint(
            "tenant_id", "certificate_number", name="uq_certificates_tenant_number"
        ),
    )
    op.create_index("ix_certificates_tenant_id", "certificates", ["tenant_id"])
    op.create_index("ix_certificates_policy_id", "certificates", ["policy_id"])
    op.create_index("ix_certificates_payment_id", "certificates", ["payment_id"])
    op.create_index("ix_certificates_customer_id", "certificates", ["customer_id"])
    op.create_index("ix_certificates_certificate_number", "certificates", ["certificate_number"])
    op.create_index("ix_certificates_status", "certificates", ["status"])
    op.create_index("ix_certificates_job_id", "certificates", ["job_id"])

    for table in ("payments", "wallets", "wallet_transactions", "certificates"):
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
    op.drop_table("certificates")
    op.drop_table("wallet_transactions")
    op.drop_table("wallets")
    op.drop_table("payments")
