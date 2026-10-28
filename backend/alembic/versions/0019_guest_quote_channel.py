"""Add channel column for staff vs guest-sourced quotes."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_guest_quote_channel"
down_revision: Union[str, None] = "0018_customer_avatar_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default="STAFF",
        ),
    )
    op.create_index("ix_proposals_channel", "proposals", ["channel"])
    op.add_column(
        "policies",
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default="STAFF",
        ),
    )
    op.create_index("ix_policies_channel", "policies", ["channel"])


def downgrade() -> None:
    op.drop_index("ix_policies_channel", table_name="policies")
    op.drop_column("policies", "channel")
    op.drop_index("ix_proposals_channel", table_name="proposals")
    op.drop_column("proposals", "channel")
