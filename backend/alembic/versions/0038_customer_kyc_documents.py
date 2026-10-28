"""Add KYC document URL columns on customers (logbook + ID front/back)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_customer_kyc_documents"
down_revision: Union[str, None] = "0037_commission_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("logbook_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("id_front_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("id_back_url", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customers", "id_back_url")
    op.drop_column("customers", "id_front_url")
    op.drop_column("customers", "logbook_url")
