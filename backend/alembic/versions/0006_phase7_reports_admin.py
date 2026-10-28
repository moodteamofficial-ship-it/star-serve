"""Phase 7: report runs (+ enterprise readiness tables if needed)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase7_reports_admin"
down_revision: Union[str, None] = "0005_phase6_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result_summary",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("export_uri", sa.String(512)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("job_id", sa.String(64)),
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
    )
    op.create_index("ix_report_runs_tenant_id", "report_runs", ["tenant_id"])
    op.create_index("ix_report_runs_report_type", "report_runs", ["report_type"])
    op.create_index("ix_report_runs_status", "report_runs", ["status"])
    op.create_index("ix_report_runs_job_id", "report_runs", ["job_id"])

    op.execute("ALTER TABLE report_runs ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_report_runs ON report_runs
        USING (
          current_setting('app.is_platform_admin', true) = 'true'
          OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
        )
        """
    )


def downgrade() -> None:
    op.drop_table("report_runs")
