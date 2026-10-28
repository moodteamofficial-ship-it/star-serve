"""Rename cert path column + append-only certificate file access log."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_certificate_file_access"
down_revision: Union[str, None] = "0015_issuance_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clearer name for the relative path under backend/data/certificates/
    op.alter_column(
        "certificates",
        "local_relative_path",
        new_column_name="local_file_path",
        existing_type=sa.String(length=512),
        existing_nullable=True,
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_certificates_local_relative_path "
        "RENAME TO ix_certificates_local_file_path"
    )

    op.add_column(
        "certificates",
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("last_accessed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "certificate_file_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("certificate_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        # STORED | VIEW | DOWNLOAD | OPEN_REMOTE | FETCH_FAILED
        sa.Column("access_kind", sa.String(length=32), nullable=False, index=True),
        # local | remote_provider | system
        sa.Column("source", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("result", sa.String(length=32), nullable=False, server_default="SUCCESS"),
        sa.Column("local_file_path", sa.String(length=512), nullable=True),
        sa.Column("provider_cert_url", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("certificate_file_accesses")
    op.drop_column("certificates", "access_count")
    op.drop_column("certificates", "last_accessed_by_user_id")
    op.drop_column("certificates", "last_accessed_at")
    op.execute(
        "ALTER INDEX IF EXISTS ix_certificates_local_file_path "
        "RENAME TO ix_certificates_local_relative_path"
    )
    op.alter_column(
        "certificates",
        "local_file_path",
        new_column_name="local_relative_path",
        existing_type=sa.String(length=512),
        existing_nullable=True,
    )
