"""Marketing website CMS tables and permissions.

Revision ID: 0044_website_cms
Revises: 0043_ussd_event_key_width
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0044_website_cms"
down_revision: str | None = "0043_ussd_event_key_width"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    ("website:read", "website", "View website CMS and enquiries"),
    ("website:edit", "website", "Edit website drafts"),
    ("website:publish", "website", "Publish website content"),
    ("website:media", "website", "Manage website media library"),
    ("website:settings", "website", "Update website settings and navigation"),
)


def upgrade() -> None:
    op.create_table(
        "website_content_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "website_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("meta_title", sa.String(120), nullable=True),
        sa.Column("meta_description", sa.String(320), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "website_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("page_slug", sa.String(64), nullable=False),
        sa.Column("section_key", sa.String(64), nullable=False),
        sa.Column("section_type", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("layout_variant", sa.String(32), nullable=True),
        sa.Column("draft_content", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("published_content", postgresql.JSONB(), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("page_slug", "section_key", name="uq_website_sections_page_key"),
    )
    op.create_index("ix_website_sections_page_slug", "website_sections", ["page_slug"])

    op.create_table(
        "website_navigation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("location", sa.String(16), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("link_kind", sa.String(32), nullable=False),
        sa.Column("link_value", sa.String(512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_website_navigation_items_location", "website_navigation_items", ["location"])

    op.create_table(
        "website_enquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("cover_needed", sa.String(120), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="NEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "website_admin_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    conn = op.get_bind()
    for code, category, description in PERMISSIONS:
        exists = conn.execute(
            text("SELECT 1 FROM permissions WHERE code = CAST(:code AS varchar)"),
            {"code": code},
        ).scalar()
        if exists:
            continue
        conn.execute(
            text(
                """
                INSERT INTO permissions (id, code, category, description, created_at, updated_at)
                VALUES (
                  CAST(:id AS uuid),
                  CAST(:code AS varchar),
                  CAST(:category AS varchar),
                  CAST(:description AS text),
                  NOW(),
                  NOW()
                )
                """
            ),
            {
                "id": str(uuid4()),
                "code": code,
                "category": category,
                "description": description,
            },
        )

    rows = conn.execute(
        text(
            """
            SELECT r.id AS role_id, p.id AS permission_id
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.code IN ('platform_admin', 'agency_admin')
              AND p.code LIKE 'website:%'
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )
    ).mappings().all()
    for row in rows:
        conn.execute(
            text(
                """
                INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
                VALUES (CAST(:id AS uuid), CAST(:role_id AS uuid), CAST(:permission_id AS uuid), NOW(), NOW())
                """
            ),
            {
                "id": str(uuid4()),
                "role_id": str(row["role_id"]),
                "permission_id": str(row["permission_id"]),
            },
        )


def downgrade() -> None:
    for table in (
        "website_admin_audit",
        "website_enquiries",
        "website_navigation_items",
        "website_sections",
        "website_pages",
        "website_content_state",
    ):
        op.drop_table(table)
    conn = op.get_bind()
    for code, _, _ in PERMISSIONS:
        conn.execute(
            text(
                "DELETE FROM role_permissions WHERE permission_id IN "
                "(SELECT id FROM permissions WHERE code = CAST(:code AS varchar))"
            ),
            {"code": code},
        )
        conn.execute(
            text("DELETE FROM permissions WHERE code = CAST(:code AS varchar)"),
            {"code": code},
        )
