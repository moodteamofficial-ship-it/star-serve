"""Reference catalogs: countries, currencies — and wire FKs from users/branches."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_ref_geo_fk"
down_revision: Union[str, None] = "0010_user_profile_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Stable UUIDs so seeds / docs can reference Kenya consistently
KENYA_ID = "a1000000-0000-4000-8000-000000000404"
UGANDA_ID = "a1000000-0000-4000-8000-000000000800"
TANZANIA_ID = "a1000000-0000-4000-8000-000000000834"
USA_ID = "a1000000-0000-4000-8000-000000000840"
UK_ID = "a1000000-0000-4000-8000-000000000826"


def upgrade() -> None:
    # --- currencies (ISO 4217) ---
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=8), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=True),
        sa.Column("decimal_places", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
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

    # --- countries ---
    op.create_table(
        "countries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("iso2", sa.String(length=2), nullable=False),
        sa.Column("iso3", sa.String(length=3), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("phone_code", sa.String(length=8), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_countries_currency_code",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("iso2", name="uq_countries_iso2"),
    )
    op.create_index("ix_countries_status", "countries", ["status"])
    op.create_index("ix_countries_currency_code", "countries", ["currency_code"])

    # Seed core currencies / countries (East Africa + common)
    currencies = [
        ("KES", "Kenyan Shilling", "KSh", 2),
        ("UGX", "Ugandan Shilling", "USh", 0),
        ("TZS", "Tanzanian Shilling", "TSh", 2),
        ("USD", "US Dollar", "$", 2),
        ("GBP", "British Pound", "£", 2),
        ("EUR", "Euro", "€", 2),
    ]
    for code, name, symbol, decimals in currencies:
        op.execute(
            sa.text(
                "INSERT INTO currencies (code, name, symbol, decimal_places, status) "
                "VALUES (:code, :name, :symbol, :decimals, 'ACTIVE')"
            ).bindparams(code=code, name=name, symbol=symbol, decimals=decimals)
        )

    countries = [
        (KENYA_ID, "KE", "KEN", "Kenya", "+254", "KES"),
        (UGANDA_ID, "UG", "UGA", "Uganda", "+256", "UGX"),
        (TANZANIA_ID, "TZ", "TZA", "Tanzania", "+255", "TZS"),
        (USA_ID, "US", "USA", "United States", "+1", "USD"),
        (UK_ID, "GB", "GBR", "United Kingdom", "+44", "GBP"),
    ]
    for cid, iso2, iso3, name, phone, currency in countries:
        op.execute(
            sa.text(
                "INSERT INTO countries (id, iso2, iso3, name, phone_code, currency_code, status) "
                "VALUES (CAST(:id AS uuid), :iso2, :iso3, :name, :phone, :currency, 'ACTIVE')"
            ).bindparams(
                id=cid, iso2=iso2, iso3=iso3, name=name, phone=phone, currency=currency
            )
        )

    # --- enrich branches for geo / country / soft-delete ---
    op.add_column("branches", sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("branches", sa.Column("country_code", sa.String(length=8), nullable=True))
    op.add_column("branches", sa.Column("phone", sa.String(length=64), nullable=True))
    op.add_column("branches", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("branches", sa.Column("address_line", sa.String(length=512), nullable=True))
    op.add_column("branches", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("branches", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("branches", sa.Column("lng", sa.Numeric(10, 7), nullable=True))
    op.add_column("branches", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "branches",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_branches_country_id", "branches", ["country_id"])
    op.create_foreign_key(
        "fk_branches_country_id",
        "branches",
        "countries",
        ["country_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_branches_tenant_id",
        "branches",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # --- wire users FKs to catalogs ---
    op.create_foreign_key(
        "fk_users_country_id",
        "users",
        "countries",
        ["country_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_users_currency",
        "users",
        "currencies",
        ["currency"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_users_tenant_id",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Missing org FKs
    op.create_foreign_key(
        "fk_departments_branch_id",
        "departments",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_departments_tenant_id",
        "departments",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_teams_branch_id",
        "teams",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_user_branches_branch_id",
        "user_branches",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_branches_user_id",
        "user_branches",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_roles_branch_id",
        "user_roles",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Soft-delete forbid on reference catalogs
    for table in ("countries", "currencies", "branches"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_forbid_hard_delete_{table} ON {table}")
        op.execute(
            f"""
            CREATE TRIGGER trg_forbid_hard_delete_{table}
            BEFORE DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION starserve_forbid_hard_delete()
            """
        )

    # Backfill users without currency already have default KES from 0010
    op.execute(
        sa.text(
            "UPDATE users SET country_id = CAST(:kid AS uuid), country_code = 'KE', "
            "phone_country_code = COALESCE(phone_country_code, '+254'), currency = COALESCE(currency, 'KES') "
            "WHERE country_id IS NULL AND deleted_at IS NULL"
        ).bindparams(kid=KENYA_ID)
    )


def downgrade() -> None:
    for table in ("countries", "currencies", "branches"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_forbid_hard_delete_{table} ON {table}")

    op.drop_constraint("fk_user_roles_branch_id", "user_roles", type_="foreignkey")
    op.drop_constraint("fk_user_branches_user_id", "user_branches", type_="foreignkey")
    op.drop_constraint("fk_user_branches_branch_id", "user_branches", type_="foreignkey")
    op.drop_constraint("fk_teams_branch_id", "teams", type_="foreignkey")
    op.drop_constraint("fk_departments_tenant_id", "departments", type_="foreignkey")
    op.drop_constraint("fk_departments_branch_id", "departments", type_="foreignkey")
    op.drop_constraint("fk_users_tenant_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_currency", "users", type_="foreignkey")
    op.drop_constraint("fk_users_country_id", "users", type_="foreignkey")

    op.drop_constraint("fk_branches_tenant_id", "branches", type_="foreignkey")
    op.drop_constraint("fk_branches_country_id", "branches", type_="foreignkey")
    op.drop_index("ix_branches_country_id", table_name="branches")
    for col in (
        "deleted_by",
        "deleted_at",
        "lng",
        "lat",
        "city",
        "address_line",
        "email",
        "phone",
        "country_code",
        "country_id",
    ):
        op.drop_column("branches", col)

    op.drop_index("ix_countries_currency_code", table_name="countries")
    op.drop_index("ix_countries_status", table_name="countries")
    op.drop_table("countries")
    op.drop_table("currencies")
