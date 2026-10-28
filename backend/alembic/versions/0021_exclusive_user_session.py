"""One ACTIVE session per user — last device wins.

Existing extra live sessions are revoked (newest kept) before the unique
partial index is created. FORCE RLS requires a session bypass for the cleanup.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0021_exclusive_user_session"
down_revision: Union[str, None] = "0020_force_rls_tenant_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "uq_sessions_one_active_per_user"


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 row_number() OVER (
                   PARTITION BY user_id
                   ORDER BY created_at DESC, id DESC
                 ) AS rn
          FROM sessions
          WHERE revoked_at IS NULL
            AND deleted_at IS NULL
            AND status = 'ACTIVE'
        )
        UPDATE sessions AS s
        SET
          revoked_at = now(),
          status = 'REVOKED',
          updated_at = now()
        FROM ranked
        WHERE s.id = ranked.id
          AND ranked.rn > 1
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX}
        ON sessions (user_id)
        WHERE revoked_at IS NULL
          AND deleted_at IS NULL
          AND status = 'ACTIVE'
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
