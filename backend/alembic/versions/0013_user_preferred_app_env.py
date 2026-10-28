"""Persist per-user preferred API environment (data plane target)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_user_preferred_app_env"
down_revision: Union[str, None] = "0012_login_lockouts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "preferred_app_env",
            sa.String(length=32),
            nullable=False,
            server_default="development",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferred_app_env")
