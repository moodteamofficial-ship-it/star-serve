"""Remove ``*:*`` from every role that is not platform_admin.

The wildcard is a platform principal right. A tenant role_permissions row
must not survive as a super-admin grant.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_revoke_agency_wildcard"
down_revision: Union[str, None] = "0023_branch_all_permission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND p.code = '*:*'
              AND r.code <> 'platform_admin'
            """
        )
    )


def downgrade() -> None:
    return
