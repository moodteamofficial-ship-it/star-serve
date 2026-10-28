"""Add unique 6-digit agent_code on intermediaries."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_intermediary_agent_code"
down_revision: Union[str, None] = "0032_stored_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "intermediaries",
        sa.Column("agent_code", sa.String(length=6), nullable=True),
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM intermediaries WHERE agent_code IS NULL ORDER BY created_at, id")
    ).fetchall()
    used: set[str] = set()
    existing = conn.execute(
        sa.text("SELECT agent_code FROM intermediaries WHERE agent_code IS NOT NULL")
    ).fetchall()
    used.update(str(r[0]) for r in existing if r[0])

    n = 100_000
    for (row_id,) in rows:
        while True:
            code = f"{n:06d}"
            n = 100_000 if n >= 999_999 else n + 1
            if code not in used:
                used.add(code)
                break
        conn.execute(
            sa.text("UPDATE intermediaries SET agent_code = :code WHERE id = :id"),
            {"code": code, "id": row_id},
        )

    op.alter_column("intermediaries", "agent_code", nullable=False)
    op.create_index("ix_intermediaries_agent_code", "intermediaries", ["agent_code"])
    op.create_unique_constraint(
        "uq_intermediaries_tenant_agent_code",
        "intermediaries",
        ["tenant_id", "agent_code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_intermediaries_tenant_agent_code", "intermediaries", type_="unique")
    op.drop_index("ix_intermediaries_agent_code", table_name="intermediaries")
    op.drop_column("intermediaries", "agent_code")
