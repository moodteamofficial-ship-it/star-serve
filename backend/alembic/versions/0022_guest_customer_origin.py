"""Isolate guest quote customers from staff CRM identity.

Staff customers stay unique on (tenant_id, id_number). Guests get their own
row scoped to the guest session so an ID number cannot bind them to an
existing staff customer.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_guest_customer_origin"
down_revision: Union[str, None] = "0021_exclusive_user_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.add_column(
        "customers",
        sa.Column(
            "origin",
            sa.String(length=16),
            nullable=False,
            server_default="STAFF",
        ),
    )
    op.add_column(
        "customers",
        sa.Column("guest_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.drop_constraint("uq_customers_tenant_id_number", "customers", type_="unique")
    op.create_index(
        "uq_customers_staff_id_number",
        "customers",
        ["tenant_id", "id_number"],
        unique=True,
        postgresql_where=sa.text("origin = 'STAFF'"),
    )
    op.create_index(
        "uq_customers_guest_session_id_number",
        "customers",
        ["tenant_id", "guest_session_id", "id_number"],
        unique=True,
        postgresql_where=sa.text("origin = 'GUEST'"),
    )
    op.create_index("ix_customers_origin", "customers", ["origin"])
    op.create_index("ix_customers_guest_session_id", "customers", ["guest_session_id"])


def downgrade() -> None:
    op.execute("SELECT set_config('app.rls_bypass', 'true', false)")
    op.drop_index("ix_customers_guest_session_id", table_name="customers")
    op.drop_index("ix_customers_origin", table_name="customers")
    op.drop_index("uq_customers_guest_session_id_number", table_name="customers")
    op.drop_index("uq_customers_staff_id_number", table_name="customers")
    op.create_unique_constraint(
        "uq_customers_tenant_id_number", "customers", ["tenant_id", "id_number"]
    )
    op.drop_column("customers", "guest_session_id")
    op.drop_column("customers", "origin")
