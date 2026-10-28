"""Sales Agent role and agent login accounts.

Each intermediary can own one staff login (``intermediaries.user_id``). Those users
get the restricted ``sales_agent`` role: they see only their own sales, payments
and customers, and can open and track claims.

Revision ID: 0041_sales_agent_logins
Revises: 0040_customer_referrals
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0041_sales_agent_logins"
down_revision: str | None = "0040_customer_referrals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SALES_AGENT_PERMISSIONS = (
    "customer:read",
    "policy:read",
    "payment:read",
    "claim:create",
    "claim:read",
    "claim:update",
    "claim:document:upload",
    "claim:document:download",
)


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', true)")

    op.add_column(
        "intermediaries",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_intermediaries_user_id_users",
        "intermediaries",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_intermediaries_user_id",
        "intermediaries",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.execute(
        """
        INSERT INTO roles (id, tenant_id, code, name, is_system, status, created_at, updated_at)
        SELECT gen_random_uuid(), t.id, 'sales_agent', 'Sales Agent', true, 'ACTIVE', now(), now()
        FROM tenants t
        WHERE NOT EXISTS (
          SELECT 1 FROM roles r
          WHERE r.tenant_id = t.id AND r.code = 'sales_agent' AND r.deleted_at IS NULL
        )
        """
    )

    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
            SELECT gen_random_uuid(), r.id, p.id, now(), now()
            FROM roles r
            JOIN permissions p ON p.code = ANY(CAST(:codes AS varchar[]))
            WHERE r.code = 'sales_agent'
              AND r.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ),
        {"codes": list(SALES_AGENT_PERMISSIONS)},
    )


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', true)")
    op.drop_index("uq_intermediaries_user_id", table_name="intermediaries")
    op.drop_constraint("fk_intermediaries_user_id_users", "intermediaries", type_="foreignkey")
    op.drop_column("intermediaries", "user_id")
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id IN (
          SELECT r.id FROM roles r
          WHERE r.code = 'sales_agent'
            AND NOT EXISTS (SELECT 1 FROM users u WHERE u.role_id = r.id)
        )
        """
    )
    op.execute(
        """
        DELETE FROM roles r
        WHERE r.code = 'sales_agent'
          AND NOT EXISTS (SELECT 1 FROM users u WHERE u.role_id = r.id)
          AND NOT EXISTS (SELECT 1 FROM user_roles ur WHERE ur.role_id = r.id)
        """
    )
