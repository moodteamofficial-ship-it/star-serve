"""USSD platform: menus, sessions, events, provider settings, admin audit.

Revision ID: 0042_ussd_platform
Revises: 0041_sales_agent_logins
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0042_ussd_platform"
down_revision: str | None = "0041_sales_agent_logins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "ussd_menu_configs",
    "ussd_provider_settings",
    "ussd_sessions",
    "ussd_session_events",
    "ussd_idempotency_records",
    "ussd_admin_audit",
)

_TENANT_PREDICATE = """
  current_setting('app.rls_bypass', true) = 'true'
  OR current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""

PERMISSIONS = (
    ("ussd:read", "ussd", "View USSD overview, menus, and sessions"),
    ("ussd:manage", "ussd", "Edit and publish USSD menus, provider settings, simulator"),
    ("ussd:analytics", "ussd", "View USSD analytics and funnel reports"),
)


def upgrade() -> None:
    op.create_table(
        "ussd_menu_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("welcome_text", sa.String(320), nullable=False),
        sa.Column("root_screen_key", sa.String(64), nullable=False, server_default="main"),
        sa.Column("max_invalid_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("session_ttl_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("max_message_chars", sa.Integer(), nullable=False, server_default="182"),
        sa.Column("nav_back", sa.String(8), nullable=False, server_default="0"),
        sa.Column("nav_home", sa.String(8), nullable=False, server_default="00"),
        sa.Column("nav_repeat", sa.String(8), nullable=True),
        sa.Column("definition", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "version", name="uq_ussd_menu_configs_tenant_version"),
    )
    op.create_index("ix_ussd_menu_configs_tenant_id", "ussd_menu_configs", ["tenant_id"])
    op.create_index("ix_ussd_menu_configs_status", "ussd_menu_configs", ["status"])

    op.create_table(
        "ussd_provider_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_kind", sa.String(32), nullable=False),
        sa.Column("service_code", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "callback_path",
            sa.String(128),
            nullable=False,
            server_default="/api/v1/ussd/callback",
        ),
        sa.Column("auth_header_name", sa.String(64), nullable=True),
        sa.Column("auth_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("allowed_ips", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "protocol_options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "service_code", name="uq_ussd_provider_tenant_code"),
    )
    op.create_index("ix_ussd_provider_settings_tenant_id", "ussd_provider_settings", ["tenant_id"])

    op.create_table(
        "ussd_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ussd_menu_configs.id"),
            nullable=False,
        ),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("provider_kind", sa.String(32), nullable=False),
        sa.Column("provider_session_id", sa.String(128), nullable=False),
        sa.Column("service_code", sa.String(32), nullable=False, server_default=""),
        sa.Column("msisdn_hash", sa.String(64), nullable=False),
        sa.Column("msisdn_masked", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_screen_key", sa.String(64), nullable=False, server_default="main"),
        sa.Column("workflow_action", sa.String(64), nullable=True),
        sa.Column("workflow_step", sa.String(64), nullable=True),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("history", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("invalid_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.Column("last_input", sa.String(256), nullable=True),
        sa.Column("last_response_type", sa.String(16), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("guest_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "provider_session_id", name="uq_ussd_sessions_provider_sid"
        ),
    )
    op.create_index("ix_ussd_sessions_tenant_id", "ussd_sessions", ["tenant_id"])
    op.create_index("ix_ussd_sessions_status", "ussd_sessions", ["status"])
    op.create_index("ix_ussd_sessions_msisdn_hash", "ussd_sessions", ["msisdn_hash"])
    op.create_index("ix_ussd_sessions_expires_at", "ussd_sessions", ["expires_at"])
    op.create_index("ix_ussd_sessions_is_test", "ussd_sessions", ["is_test"])
    op.create_index("ix_ussd_sessions_config_id", "ussd_sessions", ["config_id"])
    op.create_index("ix_ussd_sessions_correlation_id", "ussd_sessions", ["correlation_id"])
    op.create_index("ix_ussd_sessions_provider_session_id", "ussd_sessions", ["provider_session_id"])

    op.create_table(
        "ussd_session_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ussd_sessions.id"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("workflow_action", sa.String(64), nullable=True),
        sa.Column("step_id", sa.String(64), nullable=True),
        sa.Column("screen_key", sa.String(64), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("error_category", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("provider_kind", sa.String(32), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("msisdn_hash", sa.String(64), nullable=True),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "event_key", name="uq_ussd_session_events_key"),
    )
    op.create_index("ix_ussd_session_events_tenant_id", "ussd_session_events", ["tenant_id"])
    op.create_index("ix_ussd_session_events_session_id", "ussd_session_events", ["session_id"])
    op.create_index("ix_ussd_session_events_event_type", "ussd_session_events", ["event_type"])
    op.create_index("ix_ussd_session_events_created_at", "ussd_session_events", ["created_at"])
    op.create_index("ix_ussd_session_events_workflow_action", "ussd_session_events", ["workflow_action"])
    op.create_index("ix_ussd_session_events_is_test", "ussd_session_events", ["is_test"])
    op.create_index("ix_ussd_session_events_msisdn_hash", "ussd_session_events", ["msisdn_hash"])

    op.create_table(
        "ussd_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_type", sa.String(16), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_ussd_idempotency_tenant_key"),
    )
    op.create_index("ix_ussd_idempotency_records_tenant_id", "ussd_idempotency_records", ["tenant_id"])

    op.create_table(
        "ussd_admin_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ussd_admin_audit_tenant_id", "ussd_admin_audit", ["tenant_id"])
    op.create_index("ix_ussd_admin_audit_action", "ussd_admin_audit", ["action"])
    op.create_index("ix_ussd_admin_audit_created_at", "ussd_admin_audit", ["created_at"])

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_access ON {table} "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
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
              AND p.code IN ('ussd:read', 'ussd:manage', 'ussd:analytics')
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
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_access ON {table}")
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
