"""Insurer quote catalog mirrored locally (Definite products, covers, makes, models).

Insurer-wide reference data (not tenant-owned): the welcome/staff quote wizard
reads these tables and a background job refreshes them from the insurer.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039_insurer_catalog"
down_revision: str | None = "0038_customer_kyc_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "insurer_catalog_categories",
    "insurer_catalog_products",
    "insurer_catalog_cover_options",
    "insurer_vehicle_makes",
    "insurer_vehicle_models",
    "insurer_catalog_sync_state",
    "insurer_catalog_sync_runs",
)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "insurer_catalog_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_insurer_catalog_categories"),
        sa.UniqueConstraint(
            "provider_code", "name", name="uq_insurer_catalog_categories_provider_name"
        ),
    )

    op.create_table(
        "insurer_catalog_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_insurer_catalog_products"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["insurer_catalog_categories.id"],
            name="fk_insurer_catalog_products_category",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "provider_code",
            "external_id",
            name="uq_insurer_catalog_products_provider_external",
        ),
    )
    op.create_index(
        "ix_insurer_catalog_products_category_id",
        "insurer_catalog_products",
        ["category_id"],
    )
    op.create_index(
        "ix_insurer_catalog_products_listing",
        "insurer_catalog_products",
        ["provider_code", "is_active", "sort_order"],
    )

    op.create_table(
        "insurer_catalog_cover_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_insurer_catalog_cover_options"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["insurer_catalog_products.id"],
            name="fk_insurer_catalog_cover_options_product",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "product_id",
            "external_id",
            name="uq_insurer_catalog_cover_options_product_external",
        ),
    )
    op.create_index(
        "ix_insurer_catalog_cover_options_product_id",
        "insurer_catalog_cover_options",
        ["product_id"],
    )

    op.create_table(
        "insurer_vehicle_makes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_insurer_vehicle_makes"),
        sa.UniqueConstraint(
            "provider_code",
            "external_id",
            name="uq_insurer_vehicle_makes_provider_external",
        ),
    )
    op.create_index(
        "ix_insurer_vehicle_makes_listing",
        "insurer_vehicle_makes",
        ["provider_code", "is_active", "sort_order"],
    )

    op.create_table(
        "insurer_vehicle_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("make_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_insurer_vehicle_models"),
        sa.ForeignKeyConstraint(
            ["make_id"],
            ["insurer_vehicle_makes.id"],
            name="fk_insurer_vehicle_models_make",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "make_id", "external_id", name="uq_insurer_vehicle_models_make_external"
        ),
    )
    op.create_index(
        "ix_insurer_vehicle_models_make_id", "insurer_vehicle_models", ["make_id"]
    )

    op.create_table(
        "insurer_catalog_sync_state",
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("products_hash", sa.String(length=64), nullable=True),
        sa.Column("makes_hash", sa.String(length=64), nullable=True),
        sa.Column("product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("make_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("provider_code", name="pk_insurer_catalog_sync_state"),
    )

    op.create_table(
        "insurer_catalog_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("products_changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("makes_changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("make_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_insurer_catalog_sync_runs"),
    )
    op.create_index(
        "ix_insurer_catalog_sync_runs_provider_started",
        "insurer_catalog_sync_runs",
        ["provider_code", "started_at"],
    )

    # Same insurer catalog for every agency: readable by the app role regardless
    # of tenant context, never exposed to Supabase PostgREST roles.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY insurer_catalog_access_{table} ON {table} "
            "USING (true) WITH CHECK (true)"
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
    op.drop_index(
        "ix_insurer_catalog_sync_runs_provider_started", table_name="insurer_catalog_sync_runs"
    )
    op.drop_table("insurer_catalog_sync_runs")
    op.drop_table("insurer_catalog_sync_state")
    op.drop_index("ix_insurer_vehicle_models_make_id", table_name="insurer_vehicle_models")
    op.drop_table("insurer_vehicle_models")
    op.drop_index("ix_insurer_vehicle_makes_listing", table_name="insurer_vehicle_makes")
    op.drop_table("insurer_vehicle_makes")
    op.drop_index(
        "ix_insurer_catalog_cover_options_product_id",
        table_name="insurer_catalog_cover_options",
    )
    op.drop_table("insurer_catalog_cover_options")
    op.drop_index("ix_insurer_catalog_products_listing", table_name="insurer_catalog_products")
    op.drop_index(
        "ix_insurer_catalog_products_category_id", table_name="insurer_catalog_products"
    )
    op.drop_table("insurer_catalog_products")
    op.drop_table("insurer_catalog_categories")
