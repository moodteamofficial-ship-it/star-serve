"""Bind guest-filed claims to the welcome-screen capability session."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_guest_claim_session"
down_revision: Union[str, None] = "0027_claims_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.add_column(
        "claims",
        sa.Column("guest_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_claims_guest_session_id", "claims", ["guest_session_id"])


def downgrade() -> None:
    op.drop_index("ix_claims_guest_session_id", table_name="claims")
    op.drop_column("claims", "guest_session_id")
