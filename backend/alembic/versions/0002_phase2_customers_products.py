"""Phase 2: customers, intermediaries, insurance reference data."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase2_customers_products"
down_revision: Union[str, None] = "0001_phase1_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("other_names", sa.String(128)),
        sa.Column("id_number", sa.String(32), nullable=False),
        sa.Column("kra_pin", sa.String(16)),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("date_of_birth", sa.Date()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_client_ref", sa.String(128)),
        sa.Column("notes", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("tenant_id", "id_number", name="uq_customers_tenant_id_number"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("ix_customers_id_number", "customers", ["id_number"])
    op.create_index("ix_customers_status", "customers", ["status"])
    op.create_index("ix_customers_branch_id", "customers", ["branch_id"])
    op.create_index("ix_customers_assigned_user_id", "customers", ["assigned_user_id"])

    op.create_table(
        "intermediaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("identification", sa.String(64), nullable=False),
        sa.Column("kra_pin", sa.String(16)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_intermediary_ref", sa.String(128)),
        sa.Column("notes", sa.Text()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
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
            "tenant_id",
            "identification",
            name="uq_intermediaries_tenant_identification",
        ),
    )
    op.create_index("ix_intermediaries_tenant_id", "intermediaries", ["tenant_id"])
    op.create_index("ix_intermediaries_identification", "intermediaries", ["identification"])
    op.create_index("ix_intermediaries_status", "intermediaries", ["status"])
    op.create_index("ix_intermediaries_branch_id", "intermediaries", ["branch_id"])

    op.create_table(
        "insurance_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "cover_options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("provider_code", sa.String(64)),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_insurance_products_tenant_code"),
    )
    op.create_index("ix_insurance_products_tenant_id", "insurance_products", ["tenant_id"])
    op.create_index("ix_insurance_products_code", "insurance_products", ["code"])

    op.create_table(
        "vehicle_makes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_code", sa.String(64)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_vehicle_makes_tenant_code"),
    )
    op.create_index("ix_vehicle_makes_tenant_id", "vehicle_makes", ["tenant_id"])
    op.create_index("ix_vehicle_makes_code", "vehicle_makes", ["code"])

    op.create_table(
        "cancellation_reasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("provider_code", sa.String(64)),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_cancellation_reasons_tenant_code"),
    )
    op.create_index("ix_cancellation_reasons_tenant_id", "cancellation_reasons", ["tenant_id"])

    for table in ("customers", "intermediaries"):
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

    # Reference tables: allow platform rows (NULL tenant) + own tenant rows
    for table in ("insurance_products", "vehicle_makes", "cancellation_reasons"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
              current_setting('app.is_platform_admin', true) = 'true'
              OR tenant_id IS NULL
              OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
            )
            """
        )


def downgrade() -> None:
    for table in (
        "cancellation_reasons",
        "vehicle_makes",
        "insurance_products",
        "intermediaries",
        "customers",
    ):
        op.drop_table(table)
