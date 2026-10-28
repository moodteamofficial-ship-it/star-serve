"""Re-home platform-tenant intermediaries onto the guest agency."""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0035_rehome_platform_agents"
down_revision: Union[str, None] = "0034_agent_commissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guest quotes run on the first non-platform insurance agency. Agents created
    # while staff were on the platform tenant were invisible to that guest session.
    op.execute(
        text(
            """
            WITH agency AS (
              SELECT id
              FROM tenants
              WHERE COALESCE(is_platform, false) = false
                AND status = 'ACTIVE'
              ORDER BY created_at ASC, id ASC
              LIMIT 1
            ),
            agency_branch AS (
              SELECT b.id
              FROM branches b
              JOIN agency a ON a.id = b.tenant_id
              WHERE b.deleted_at IS NULL
                AND b.status = 'ACTIVE'
              ORDER BY b.created_at ASC
              LIMIT 1
            )
            UPDATE intermediaries i
            SET
              tenant_id = (SELECT id FROM agency),
              branch_id = COALESCE(
                (SELECT id FROM agency_branch),
                i.branch_id
              )
            WHERE i.deleted_at IS NULL
              AND i.tenant_id IN (
                SELECT id FROM tenants WHERE COALESCE(is_platform, false) = true
              )
              AND EXISTS (SELECT 1 FROM agency)
            """
        )
    )


def downgrade() -> None:
    # Irreversible data move — platform tenant id is not recoverable per-row.
    pass
