"""Customer referral codes and referral credit ledger.

Each person (tenant + national ID) gets one shareable code. A paid certificate
bought with someone's code credits that referrer a fixed amount (KES 50 by
default). Credits are never paid out; they come off the referrer's next premium.

Revision ID: 0040_customer_referrals
Revises: 0039_insurer_catalog
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0040_customer_referrals"
down_revision: str | None = "0039_insurer_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("customer_referral_codes", "customer_referral_credits")

_TENANT_PREDICATE = """
  current_setting('app.rls_bypass', true) = 'true'
  OR current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""


def upgrade() -> None:
    op.add_column(
        "commission_settings",
        sa.Column(
            "customer_referral_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("50.00"),
        ),
    )
    op.add_column(
        "commission_settings",
        sa.Column(
            "customer_referrals_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.create_table(
        "customer_referral_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_number", sa.String(32), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("holder_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "id_number", name="uq_customer_referral_codes_person"),
        sa.UniqueConstraint("code", name="uq_customer_referral_codes_code"),
    )
    op.create_index(
        "ix_customer_referral_codes_tenant_id", "customer_referral_codes", ["tenant_id"]
    )
    op.create_index(
        "ix_customer_referral_codes_customer_id", "customer_referral_codes", ["customer_id"]
    )

    op.create_table(
        "customer_referral_credits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_number", sa.String(32), nullable=False),
        sa.Column("referral_code", sa.String(16), nullable=False),
        sa.Column("entry_kind", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("buyer_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "tenant_id", "payment_id", "entry_kind", name="uq_customer_referral_credits_payment"
        ),
    )
    op.create_index(
        "ix_customer_referral_credits_account",
        "customer_referral_credits",
        ["tenant_id", "id_number", "occurred_at"],
    )
    op.create_index(
        "ix_customer_referral_credits_payment_id", "customer_referral_credits", ["payment_id"]
    )

    op.add_column("customers", sa.Column("referral_code", sa.String(16), nullable=True))
    op.add_column(
        "customers",
        sa.Column(
            "referred_by_intermediary_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "intermediaries.id",
                ondelete="SET NULL",
                name="fk_customers_referred_by_intermediary_id_intermediaries",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "customers", sa.Column("referred_by_agent_code", sa.String(16), nullable=True)
    )
    op.add_column(
        "customers", sa.Column("referred_by_agent_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "customers", sa.Column("referred_by_referral_code", sa.String(16), nullable=True)
    )
    op.add_column(
        "customers", sa.Column("referred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_customers_referral_code", "customers", ["referral_code"])
    op.create_index(
        "ix_customers_referred_by_intermediary_id", "customers", ["referred_by_intermediary_id"]
    )
    op.execute(
        """
        UPDATE customers c SET referral_code = r.code
        FROM customer_referral_codes r
        WHERE r.tenant_id = c.tenant_id AND r.id_number = c.id_number
        """
    )

    op.add_column("proposals", sa.Column("referral_code", sa.String(16), nullable=True))
    op.add_column("policies", sa.Column("referral_code", sa.String(16), nullable=True))
    op.add_column(
        "payments",
        sa.Column(
            "discount_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_access ON {table} "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )
        for role in ("PUBLIC", "anon", "authenticated", "authenticator"):
            op.execute(
                f"""
                DO $$
                BEGIN
                  BEGIN
                    EXECUTE 'REVOKE ALL ON TABLE {table} FROM {role}';
                  EXCEPTION WHEN undefined_object THEN
                    NULL;
                  END;
                END $$;
                """
            )


def downgrade() -> None:
    op.drop_column("payments", "discount_amount")
    op.drop_column("policies", "referral_code")
    op.drop_column("proposals", "referral_code")
    op.drop_index("ix_customers_referred_by_intermediary_id", table_name="customers")
    op.drop_index("ix_customers_referral_code", table_name="customers")
    for column in (
        "referred_at",
        "referred_by_referral_code",
        "referred_by_agent_name",
        "referred_by_agent_code",
        "referred_by_intermediary_id",
        "referral_code",
    ):
        op.drop_column("customers", column)
    op.drop_table("customer_referral_credits")
    op.drop_table("customer_referral_codes")
    op.drop_column("commission_settings", "customer_referrals_enabled")
    op.drop_column("commission_settings", "customer_referral_amount")
