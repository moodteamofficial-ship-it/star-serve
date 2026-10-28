"""Progressive login lockouts (email + device)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_login_lockouts"
down_revision: Union[str, None] = "0011_ref_geo_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_lockouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("device_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lockout_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_lock_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", "device_fingerprint", name="uq_login_lockouts_email_device"),
    )
    op.create_index("ix_login_lockouts_email", "login_lockouts", ["email"])
    op.create_index(
        "ix_login_lockouts_device_fingerprint", "login_lockouts", ["device_fingerprint"]
    )
    op.create_index("ix_login_lockouts_locked_until", "login_lockouts", ["locked_until"])

    # App-only writes — revoke from PUBLIC / anon-style roles if present
    op.execute("REVOKE ALL ON TABLE login_lockouts FROM PUBLIC")
    op.execute("ALTER TABLE login_lockouts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE login_lockouts FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS login_lockouts_app_all ON login_lockouts")
    op.execute(
        """
        CREATE POLICY login_lockouts_app_all ON login_lockouts
        FOR ALL
        USING (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (
          current_setting('app.rls_bypass', true) = 'true'
          OR current_setting('app.is_platform_admin', true) = 'true'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS login_lockouts_app_all ON login_lockouts")
    op.execute("ALTER TABLE login_lockouts DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_login_lockouts_locked_until", table_name="login_lockouts")
    op.drop_index("ix_login_lockouts_device_fingerprint", table_name="login_lockouts")
    op.drop_index("ix_login_lockouts_email", table_name="login_lockouts")
    op.drop_table("login_lockouts")
