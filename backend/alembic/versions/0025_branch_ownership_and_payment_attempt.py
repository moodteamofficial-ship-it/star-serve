"""Stamp branch ownership on payments/certificates; one active STK per policy.

Existing NULL branch_id rows are backfilled from the related customer/policy
when possible. Leftover NULL is not treated as tenant-wide by assigned-scope
queries — only ALL_TENANT principals can see those historical rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_branch_ownership_payment"
down_revision: Union[str, None] = "0024_revoke_agency_wildcard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")

    op.add_column(
        "payments",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_payments_branch_id", "payments", ["branch_id"])
    op.create_foreign_key(
        "fk_payments_branch_id",
        "payments",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "certificates",
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_certificates_branch_id", "certificates", ["branch_id"])
    op.create_foreign_key(
        "fk_certificates_branch_id",
        "certificates",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            """
            UPDATE proposals pr
            SET branch_id = c.branch_id
            FROM customers c
            WHERE pr.customer_id = c.id
              AND pr.branch_id IS NULL
              AND c.branch_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE policies pol
            SET branch_id = src.branch_id
            FROM (
                SELECT pol.id,
                       COALESCE(pr.branch_id, c.branch_id) AS branch_id
                FROM policies pol
                JOIN customers c ON c.id = pol.customer_id
                LEFT JOIN proposals pr ON pr.id = pol.proposal_id
                WHERE pol.branch_id IS NULL
                  AND COALESCE(pr.branch_id, c.branch_id) IS NOT NULL
            ) src
            WHERE pol.id = src.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE payments p
            SET branch_id = src.branch_id
            FROM (
                SELECT p.id,
                       COALESCE(pol.branch_id, c.branch_id) AS branch_id
                FROM payments p
                LEFT JOIN policies pol ON pol.id = p.policy_id
                LEFT JOIN customers c ON c.id = p.customer_id
                WHERE p.branch_id IS NULL
                  AND COALESCE(pol.branch_id, c.branch_id) IS NOT NULL
            ) src
            WHERE p.id = src.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE certificates cert
            SET branch_id = src.branch_id
            FROM (
                SELECT cert.id,
                       COALESCE(pol.branch_id, c.branch_id) AS branch_id
                FROM certificates cert
                LEFT JOIN policies pol ON pol.id = cert.policy_id
                LEFT JOIN customers c ON c.id = cert.customer_id
                WHERE cert.branch_id IS NULL
                  AND COALESCE(pol.branch_id, c.branch_id) IS NOT NULL
            ) src
            WHERE cert.id = src.id
            """
        )
    )

    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY policy_id
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                FROM payments
                WHERE policy_id IS NOT NULL
                  AND status IN ('PENDING', 'INITIATED')
            )
            UPDATE payments
            SET status = 'CANCELLED',
                failure_code = 'SUPERSEDED',
                failure_message = 'Superseded by a later payment attempt',
                version = version + 1
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """
        )
    )
    op.create_index(
        "uq_payments_one_active_per_policy",
        "payments",
        ["policy_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('PENDING', 'INITIATED') AND policy_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_one_active_per_policy", table_name="payments")
    op.drop_constraint("fk_certificates_branch_id", "certificates", type_="foreignkey")
    op.drop_index("ix_certificates_branch_id", table_name="certificates")
    op.drop_column("certificates", "branch_id")
    op.drop_constraint("fk_payments_branch_id", "payments", type_="foreignkey")
    op.drop_index("ix_payments_branch_id", table_name="payments")
    op.drop_column("payments", "branch_id")
