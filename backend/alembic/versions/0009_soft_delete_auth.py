"""Soft-delete columns for users/roles/sessions — never hard-delete auth rows."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_soft_delete_auth"
down_revision: Union[str, None] = "0008_secure_users_roles_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_SOFT_DELETE_TABLES = ("users", "roles", "sessions", "user_roles")


def upgrade() -> None:
    # --- users ---
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_foreign_key(
        "fk_users_deleted_by_users",
        "users",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Allow re-using email after soft-delete
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_users_tenant_email_active
        ON users (tenant_id, email)
        WHERE deleted_at IS NULL
        """
    )

    # --- roles ---
    op.add_column(
        "roles",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
    )
    op.add_column("roles", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "roles",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_roles_status", "roles", ["status"])
    op.create_index("ix_roles_deleted_at", "roles", ["deleted_at"])
    op.create_foreign_key(
        "fk_roles_deleted_by_users",
        "roles",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("uq_roles_tenant_code", "roles", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_roles_tenant_code_active
        ON roles (tenant_id, code)
        WHERE deleted_at IS NULL
        """
    )

    # --- sessions (revoke via status; keep row forever) ---
    op.add_column(
        "sessions",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
    )
    op.add_column("sessions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_sessions_status", "sessions", ["status"])
    op.create_index("ix_sessions_deleted_at", "sessions", ["deleted_at"])

    # --- user_roles ---
    op.add_column(
        "user_roles",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
    )
    op.add_column("user_roles", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_roles",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_user_roles_status", "user_roles", ["status"])
    op.create_index("ix_user_roles_deleted_at", "user_roles", ["deleted_at"])
    op.drop_constraint("uq_user_roles_user_role_branch", "user_roles", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_user_roles_active
        ON user_roles (user_id, role_id, COALESCE(branch_id, '00000000-0000-0000-0000-000000000000'::uuid))
        WHERE deleted_at IS NULL
        """
    )

    # --- customers: deleted_by for audit parity ---
    op.add_column(
        "customers",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_customers_deleted_by_users",
        "customers",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # Hard DELETE is forbidden — soft-delete only (status + deleted_at + deleted_by)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION starserve_forbid_hard_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION
            'Hard DELETE is forbidden on %. Soft-delete by setting status, deleted_at, and deleted_by.',
            TG_TABLE_NAME;
        END;
        $$;
        """
    )
    for table in AUTH_SOFT_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_forbid_hard_delete_{table} ON {table}")
        op.execute(
            f"""
            CREATE TRIGGER trg_forbid_hard_delete_{table}
            BEFORE DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION starserve_forbid_hard_delete()
            """
        )

    # user_roles write gate: allow soft-delete updates; still block hard delete via trigger above
    op.execute(
        """
        CREATE OR REPLACE FUNCTION starserve_guard_user_role_assign()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Hard DELETE is forbidden on user_roles — soft-delete instead';
          END IF;
          IF current_setting('app.allow_auth_write', true) IS DISTINCT FROM 'true' THEN
            RAISE EXCEPTION 'user_roles may only be changed by the application auth path';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )


def downgrade() -> None:
    for table in AUTH_SOFT_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_forbid_hard_delete_{table} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS starserve_forbid_hard_delete()")

    op.drop_constraint("fk_customers_deleted_by_users", "customers", type_="foreignkey")
    op.drop_column("customers", "deleted_by")

    op.execute("DROP INDEX IF EXISTS uq_user_roles_active")
    op.create_unique_constraint(
        "uq_user_roles_user_role_branch",
        "user_roles",
        ["user_id", "role_id", "branch_id"],
    )
    op.drop_index("ix_user_roles_deleted_at", table_name="user_roles")
    op.drop_index("ix_user_roles_status", table_name="user_roles")
    op.drop_column("user_roles", "deleted_by")
    op.drop_column("user_roles", "deleted_at")
    op.drop_column("user_roles", "status")

    op.drop_index("ix_sessions_deleted_at", table_name="sessions")
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_column("sessions", "deleted_by")
    op.drop_column("sessions", "deleted_at")
    op.drop_column("sessions", "status")

    op.execute("DROP INDEX IF EXISTS uq_roles_tenant_code_active")
    op.create_unique_constraint("uq_roles_tenant_code", "roles", ["tenant_id", "code"])
    op.drop_constraint("fk_roles_deleted_by_users", "roles", type_="foreignkey")
    op.drop_index("ix_roles_deleted_at", table_name="roles")
    op.drop_index("ix_roles_status", table_name="roles")
    op.drop_column("roles", "deleted_by")
    op.drop_column("roles", "deleted_at")
    op.drop_column("roles", "status")

    op.execute("DROP INDEX IF EXISTS uq_users_tenant_email_active")
    op.create_unique_constraint("uq_users_tenant_email", "users", ["tenant_id", "email"])
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
