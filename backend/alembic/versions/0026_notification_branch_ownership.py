"""Stamp branch ownership on notifications so assigned agents cannot read
another branch's recipient PII or payment SMS bodies (SS-2026-08).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_notification_branch"
down_revision: Union[str, None] = "0025_branch_ownership_payment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")

    op.add_column(
        "notifications",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_notifications_branch_id", "notifications", ["branch_id"])
    op.create_foreign_key(
        "fk_notifications_branch_id",
        "notifications",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            """
            UPDATE notifications n
            SET branch_id = c.branch_id
            FROM customers c
            WHERE n.customer_id = c.id
              AND n.branch_id IS NULL
              AND c.branch_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE notifications n
            SET branch_id = p.branch_id
            FROM payments p
            WHERE n.related_resource = 'payment'
              AND n.related_resource_id = p.id
              AND n.branch_id IS NULL
              AND p.branch_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE notifications n
            SET branch_id = pol.branch_id
            FROM policies pol
            WHERE n.related_resource = 'policy'
              AND n.related_resource_id = pol.id
              AND n.branch_id IS NULL
              AND pol.branch_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_notifications_branch_id", "notifications", type_="foreignkey")
    op.drop_index("ix_notifications_branch_id", table_name="notifications")
    op.drop_column("notifications", "branch_id")
