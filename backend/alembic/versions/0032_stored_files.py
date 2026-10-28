"""Registry for PDFs stored under backend/data (relative paths only)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_stored_files"
down_revision: Union[str, None] = "0031_notification_priority"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_PREDICATE = """
  current_setting('app.rls_bypass', true) = 'true'
  OR current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""


def _ts() -> tuple[sa.Column, sa.Column]:
    return (
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


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
        USING ({_TENANT_PREDICATE})
        """
    )
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    created, updated = _ts()
    op.create_table(
        "stored_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("kind", sa.String(length=32), nullable=False, index=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("relative_path", sa.String(length=512), nullable=False),
        sa.Column("storage", sa.String(length=32), nullable=False, server_default="email-pdfs"),
        sa.Column("filename", sa.String(length=128), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=64),
            nullable=False,
            server_default="application/pdf",
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("created_by_label", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="staff"),
        sa.Column("generate_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_viewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_downloaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["last_generated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["last_viewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["last_downloaded_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "kind",
            "resource_id",
            name="uq_stored_files_tenant_kind_resource",
        ),
    )
    created, updated = _ts()
    op.create_table(
        "stored_file_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("stored_file_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("actor_label", sa.String(length=255), nullable=True),
        sa.Column("access_kind", sa.String(length=32), nullable=False, index=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="staff"),
        sa.Column("relative_path", sa.String(length=512), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True, index=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        created,
        updated,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    _rls("stored_files")
    _rls("stored_file_accesses")
    _backfill_existing_mail_pdfs()


def _backfill_existing_mail_pdfs() -> None:
    """Register PDFs already sitting in data/email-pdfs."""
    import hashlib
    import re
    from pathlib import Path
    from uuid import UUID

    from app.core.config import get_settings

    settings = get_settings()
    root = Path(settings.email_pdf_storage_dir).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    if not root.is_dir():
        return
    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    conn = op.get_bind()
    for tenant_dir in root.iterdir():
        if not tenant_dir.is_dir() or not uuid_re.match(tenant_dir.name):
            continue
        try:
            tenant_id = UUID(tenant_dir.name)
        except ValueError:
            continue
        for kind_dir in tenant_dir.iterdir():
            if not kind_dir.is_dir() or kind_dir.name not in {"claim", "certificate"}:
                continue
            for pdf in kind_dir.glob("*.pdf"):
                if not uuid_re.match(pdf.stem):
                    continue
                try:
                    content = pdf.read_bytes()
                except OSError:
                    continue
                if not content.startswith(b"%PDF"):
                    continue
                name_path = pdf.with_suffix(".filename")
                filename = f"{pdf.stem}.pdf"
                if name_path.is_file():
                    try:
                        filename = name_path.read_text(encoding="utf-8").strip() or filename
                    except OSError:
                        pass
                relative = f"{tenant_dir.name.lower()}/{kind_dir.name}/{pdf.stem.lower()}.pdf"
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO stored_files (
                          id, tenant_id, kind, resource_id, relative_path, storage,
                          filename, content_type, content_sha256, file_size_bytes,
                          source, generate_count, created_at, updated_at, last_generated_at
                        )
                        SELECT
                          gen_random_uuid(),
                          CAST(:tenant_id AS uuid),
                          CAST(:kind AS varchar),
                          CAST(:resource_id AS uuid),
                          CAST(:relative_path AS varchar),
                          'email-pdfs',
                          CAST(:filename AS varchar),
                          'application/pdf',
                          CAST(:sha AS varchar),
                          CAST(:size AS integer),
                          'backfill', 1, now(), now(), now()
                        WHERE EXISTS (
                          SELECT 1 FROM tenants WHERE id = CAST(:tenant_id AS uuid)
                        )
                          AND NOT EXISTS (
                            SELECT 1 FROM stored_files
                            WHERE tenant_id = CAST(:tenant_id AS uuid)
                              AND kind = CAST(:kind AS varchar)
                              AND resource_id = CAST(:resource_id AS uuid)
                          )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "kind": kind_dir.name,
                        "resource_id": UUID(pdf.stem),
                        "relative_path": relative,
                        "filename": filename[:128],
                        "sha": hashlib.sha256(content).hexdigest(),
                        "size": len(content),
                    },
                )


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.drop_table("stored_file_accesses")
    op.drop_table("stored_files")
