"""Queue index for the email dispatcher (SKIP LOCKED + priority)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_notification_priority"
down_revision: Union[str, None] = "0030_user_update_permission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute(
        """
        ALTER TABLE notifications
        ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_notifications_dispatch
        ON notifications (priority, created_at)
        WHERE status = 'QUEUED' AND channel = 'EMAIL'
        """
    )


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute("DROP INDEX IF EXISTS ix_notifications_dispatch")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS priority")
