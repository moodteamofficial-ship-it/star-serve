"""Explicit tenant-wide branch capability.

Empty user_branches is no longer treated as all-tenant access. Roles that
already operate tenant-wide receive ``branch:all`` so legitimate workflows
keep working.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_branch_all_permission"
down_revision: Union[str, None] = "0022_guest_customer_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute(
        sa.text(
            """
            INSERT INTO permissions (id, code, description, category, created_at, updated_at)
            VALUES (
              gen_random_uuid(),
              'branch:all',
              'Access all branches in the tenant',
              'branch',
              now(),
              now()
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
            SELECT gen_random_uuid(), r.id, p.id, now(), now()
            FROM roles r
            CROSS JOIN permissions p
            WHERE p.code = 'branch:all'
              AND r.deleted_at IS NULL
              AND (
                r.code IN (
                  'agency_admin',
                  'finance_officer',
                  'auditor',
                  'underwriter'
                )
                OR EXISTS (
                  SELECT 1
                  FROM role_permissions rp
                  JOIN permissions existing ON existing.id = rp.permission_id
                  WHERE rp.role_id = r.id
                    AND existing.code IN (
                      'tenant:manage',
                      'branch:manage',
                      'role:manage',
                      'payment:reconcile',
                      'audit:read',
                      'reports:run',
                      'proposal:approve'
                    )
                )
              )
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions x
                WHERE x.role_id = r.id AND x.permission_id = p.id
              )
            """
        )
    )


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (
              SELECT id FROM permissions WHERE code = 'branch:all'
            )
            """
        )
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'branch:all'"))
