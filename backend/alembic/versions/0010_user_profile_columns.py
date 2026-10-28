"""Add user profile / OTP / geo / branch columns."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_user_profile_columns"
down_revision: Union[str, None] = "0009_soft_delete_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("country_code", sa.String(length=8), nullable=True))
    op.add_column("users", sa.Column("phone_country_code", sa.String(length=8), nullable=True))
    op.add_column("users", sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="KES"),
    )
    op.add_column("users", sa.Column("gender", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("users", sa.Column("lng", sa.Numeric(10, 7), nullable=True))
    # OTP — store hash only; never return via API
    op.add_column("users", sa.Column("otp_hash", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("otp_channel", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("locale", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(length=512), nullable=True))

    op.create_index("ix_users_country_code", "users", ["country_code"])
    op.create_index("ix_users_country_id", "users", ["country_id"])
    op.create_index("ix_users_branch_id", "users", ["branch_id"])
    op.create_index("ix_users_currency", "users", ["currency"])

    # FK to branches when present (shared DB); SET NULL so soft-delete of branch is safe later
    op.create_foreign_key(
        "fk_users_branch_id_branches",
        "users",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_branch_id_branches", "users", type_="foreignkey")
    op.drop_index("ix_users_currency", table_name="users")
    op.drop_index("ix_users_branch_id", table_name="users")
    op.drop_index("ix_users_country_id", table_name="users")
    op.drop_index("ix_users_country_code", table_name="users")
    for col in (
        "avatar_url",
        "locale",
        "timezone",
        "otp_channel",
        "otp_attempts",
        "otp_expires_at",
        "otp_hash",
        "lng",
        "lat",
        "branch_id",
        "gender",
        "currency",
        "country_id",
        "phone_country_code",
        "country_code",
    ):
        op.drop_column("users", col)
