"""Widen certificate storage_key for long Azure SAS URLs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cert_storage_text"
down_revision: Union[str, None] = "0006_phase7_reports_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "certificates",
        "storage_key",
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "certificates",
        "storage_key",
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
