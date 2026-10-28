"""Add customers.avatar_url for profile photos."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_customer_avatar_url"
down_revision: Union[str, None] = "0017_domain_foreign_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customers", "avatar_url")
