"""Platform system configuration — DB as source of truth."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_system_configuration"
down_revision: Union[str, None] = "0013_user_preferred_app_env"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMISSION_ID = "b1000000-0000-4000-8000-0000000000c1"


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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

    op.execute(
        sa.text(
            """
            INSERT INTO system_settings (key, value, description, version)
            VALUES
              (
                'system.operational',
                '{"enabled": true, "reason": null, "disabled_at": null, "disabled_by": null}'::jsonb,
                'Master platform switch — when disabled, non-platform users cannot use the API.',
                1
              ),
              (
                'system.services',
                '{"quoting": true, "payments": true, "notifications": true, "issuance": true, "reports": true, "certificates": true}'::jsonb,
                'Per-capability service toggles enforced by the API.',
                1
              ),
              (
                'system.notification_channels',
                '{"SMS": {"enabled": true}, "EMAIL": {"enabled": true}, "WHATSAPP": {"enabled": true}, "PUSH": {"enabled": false}}'::jsonb,
                'Outbound notification channel allow-list.',
                1
              )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO permissions (id, code, description, category, created_at, updated_at)
            VALUES (
              CAST(:pid AS uuid),
              'platform:config:manage',
              'Manage platform system configuration',
              'platform',
              now(),
              now()
            )
            ON CONFLICT (code) DO NOTHING
            """
        ).bindparams(pid=_PERMISSION_ID)
    )

    # Grant to every platform_admin role (existing + future seeds via catalog).
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
            SELECT gen_random_uuid(), r.id, p.id, now(), now()
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.code = 'platform_admin'
              AND r.deleted_at IS NULL
              AND p.code = 'platform:config:manage'
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (
              SELECT id FROM permissions WHERE code = 'platform:config:manage'
            )
            """
        )
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'platform:config:manage'"))
    op.drop_table("system_settings")
