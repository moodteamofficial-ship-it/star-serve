"""Ensure commission permissions exist and are granted to platform admins."""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
from sqlalchemy import text

revision: str = "0037_commission_permissions"
down_revision: Union[str, None] = "0036_ops_visibility_commissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMS = (
    ("commission:read", "commission", "Read commission settings and ledger"),
    ("commission:manage", "commission", "Manage commission rates and settings"),
    ("commission:payout", "commission", "Record commission payouts"),
)


def upgrade() -> None:
    conn = op.get_bind()
    for code, category, description in _PERMS:
        exists = conn.execute(
            text("SELECT 1 FROM permissions WHERE code = CAST(:code AS varchar)"),
            {"code": code},
        ).scalar()
        if exists:
            continue
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, code, category, description, created_at, updated_at)
                VALUES (
                  CAST(:id AS uuid),
                  CAST(:code AS varchar),
                  CAST(:category AS varchar),
                  CAST(:description AS text),
                  NOW(),
                  NOW()
                )
                """
            ),
            {
                "id": str(uuid4()),
                "code": code,
                "category": category,
                "description": description,
            },
        )

    # Attach read/manage/payout to platform_admin and finance roles.
    rows = conn.execute(
        text(
            """
            SELECT r.id AS role_id, p.id AS permission_id
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.code IN ('platform_admin', 'agency_admin', 'finance_officer', 'finance_manager')
              AND p.code IN ('commission:read', 'commission:manage', 'commission:payout')
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )
    ).mappings().all()
    for row in rows:
        conn.execute(
            text(
                """
                INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
                VALUES (CAST(:id AS uuid), CAST(:role_id AS uuid), CAST(:permission_id AS uuid), NOW(), NOW())
                """
            ),
            {
                "id": str(uuid4()),
                "role_id": str(row["role_id"]),
                "permission_id": str(row["permission_id"]),
            },
        )


def downgrade() -> None:
    pass
