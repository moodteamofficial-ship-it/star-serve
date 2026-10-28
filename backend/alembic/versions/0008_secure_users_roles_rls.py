"""Harden users/roles/sessions: primary role_id, FORCE RLS, block public + column tamper."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_secure_users_roles_rls"
down_revision: Union[str, None] = "0007_cert_storage_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_TABLES = (
    "users",
    "roles",
    "user_roles",
    "role_permissions",
    "sessions",
    "permissions",
)


def upgrade() -> None:
    # --- Primary role on users + session snapshot ---
    op.add_column(
        "users",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_role_id_roles",
        "users",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_users_role_id", "users", ["role_id"])

    op.add_column(
        "sessions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_role_id_roles",
        "sessions",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_sessions_role_id", "sessions", ["role_id"])

    # Environment label for audit / multi-env awareness (populated by backend APP_ENV)
    op.add_column(
        "sessions",
        sa.Column("app_env", sa.String(length=32), nullable=True),
    )

    # Backfill primary role from first assignment
    op.execute(
        """
        UPDATE users u
        SET role_id = sub.role_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, role_id
            FROM user_roles
            ORDER BY user_id, created_at ASC NULLS LAST
        ) AS sub
        WHERE u.id = sub.user_id AND u.role_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE sessions s
        SET role_id = u.role_id
        FROM users u
        WHERE s.user_id = u.id AND s.role_id IS NULL AND u.role_id IS NOT NULL
        """
    )

    # --- Block direct column tampering unless app.allow_auth_write=true ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION starserve_guard_user_auth_columns()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF current_setting('app.allow_auth_write', true) IS DISTINCT FROM 'true' THEN
            IF TG_OP = 'UPDATE' THEN
              IF NEW.password_hash IS DISTINCT FROM OLD.password_hash THEN
                RAISE EXCEPTION 'password_hash is not directly editable';
              END IF;
              IF NEW.role_id IS DISTINCT FROM OLD.role_id THEN
                RAISE EXCEPTION 'role_id is not directly editable';
              END IF;
              IF NEW.is_platform_admin IS DISTINCT FROM OLD.is_platform_admin THEN
                RAISE EXCEPTION 'is_platform_admin is not directly editable';
              END IF;
              IF NEW.status IS DISTINCT FROM OLD.status
                 AND current_setting('app.allow_status_write', true) IS DISTINCT FROM 'true' THEN
                RAISE EXCEPTION 'user status is not directly editable';
              END IF;
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_guard_user_auth_columns ON users")
    op.execute(
        """
        CREATE TRIGGER trg_guard_user_auth_columns
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION starserve_guard_user_auth_columns()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION starserve_guard_user_role_assign()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF current_setting('app.allow_auth_write', true) IS DISTINCT FROM 'true' THEN
            RAISE EXCEPTION 'user_roles may only be changed by the application auth path';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_guard_user_roles ON user_roles")
    op.execute(
        """
        CREATE TRIGGER trg_guard_user_roles
        BEFORE INSERT OR UPDATE OR DELETE ON user_roles
        FOR EACH ROW
        EXECUTE FUNCTION starserve_guard_user_role_assign()
        """
    )

    # --- RLS: enable on permissions / role_permissions; FORCE on auth tables ---
    op.execute("ALTER TABLE permissions ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS permissions_backend_only ON permissions")
    op.execute(
        """
        CREATE POLICY permissions_backend_only ON permissions
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
          OR NULLIF(current_setting('app.tenant_id', true), '') IS NOT NULL
        )
        """
    )

    op.execute("ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS role_permissions_via_tenant_role ON role_permissions")
    op.execute(
        """
        CREATE POLICY role_permissions_via_tenant_role ON role_permissions
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
          OR EXISTS (
            SELECT 1 FROM roles r
            WHERE r.id = role_permissions.role_id
              AND (
                r.tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
                OR r.tenant_id IS NULL
              )
          )
        )
        """
    )

    # Replace/augment tenant policies with bypass + user-scoped sessions
    for table in ("users", "roles", "user_roles", "sessions"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")

    op.execute(
        """
        CREATE POLICY tenant_isolation_users ON users
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
          OR (
            tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
            AND (
              id::text = NULLIF(current_setting('app.user_id', true), '')
              OR current_setting('app.can_manage_users', true) = 'true'
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_roles ON roles
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
          OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
          OR (
            id::text = NULLIF(current_setting('app.role_id', true), '')
            AND tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
          )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_user_roles ON user_roles
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
          OR (
            tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
            AND (
              user_id::text = NULLIF(current_setting('app.user_id', true), '')
              OR current_setting('app.can_manage_users', true) = 'true'
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_sessions ON sessions
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
          OR (
            tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
            AND user_id::text = NULLIF(current_setting('app.user_id', true), '')
          )
        )
        """
    )

    for table in AUTH_TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # Lock out Supabase PostgREST / public roles (no-op if roles do not exist locally)
    for role in ("PUBLIC", "anon", "authenticated", "authenticator"):
        for table in AUTH_TABLES:
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
    for table in AUTH_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS permissions_backend_only ON permissions")
    op.execute("DROP POLICY IF EXISTS role_permissions_via_tenant_role ON role_permissions")
    op.execute("ALTER TABLE permissions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE role_permissions DISABLE ROW LEVEL SECURITY")

    for table in ("users", "roles", "user_roles", "sessions"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
              current_setting('app.is_platform_admin', true) = 'true'
              OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
            )
            """
        )

    op.execute("DROP TRIGGER IF EXISTS trg_guard_user_roles ON user_roles")
    op.execute("DROP FUNCTION IF EXISTS starserve_guard_user_role_assign()")
    op.execute("DROP TRIGGER IF EXISTS trg_guard_user_auth_columns ON users")
    op.execute("DROP FUNCTION IF EXISTS starserve_guard_user_auth_columns()")

    op.drop_column("sessions", "app_env")
    op.drop_index("ix_sessions_role_id", table_name="sessions")
    op.drop_constraint("fk_sessions_role_id_roles", "sessions", type_="foreignkey")
    op.drop_column("sessions", "role_id")
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_constraint("fk_users_role_id_roles", "users", type_="foreignkey")
    op.drop_column("users", "role_id")
