"""Widen ussd_session_events.event_key for long event type prefixes.

Revision ID: 0043_ussd_event_key_width
Revises: 0042_ussd_platform
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_ussd_event_key_width"
down_revision: str | None = "0042_ussd_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "ussd_session_events",
        "event_key",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "ussd_session_events",
        "event_key",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
