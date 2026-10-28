"""Phase 6: notifications."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase6_notifications"
down_revision: Union[str, None] = "0004_phase5_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("related_resource", sa.String(64)),
        sa.Column("related_resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template_code", sa.String(64), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(256)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_message_id", sa.String(128)),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("job_id", sa.String(64)),
        sa.Column("idempotency_key", sa.String(128)),
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
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_notifications_tenant_idempotency"
        ),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_customer_id", "notifications", ["customer_id"])
    op.create_index(
        "ix_notifications_related_resource_id", "notifications", ["related_resource_id"]
    )
    op.create_index("ix_notifications_channel", "notifications", ["channel"])
    op.create_index("ix_notifications_template_code", "notifications", ["template_code"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index(
        "ix_notifications_provider_message_id", "notifications", ["provider_message_id"]
    )
    op.create_index("ix_notifications_job_id", "notifications", ["job_id"])

    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_notifications ON notifications
        USING (
          current_setting('app.is_platform_admin', true) = 'true'
          OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
        )
        """
    )


def downgrade() -> None:
    op.drop_table("notifications")
