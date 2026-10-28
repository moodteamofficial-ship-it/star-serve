"""Persist full quote/provider/certificate issuance fields + local cert paths."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_issuance_persistence"
down_revision: Union[str, None] = "0014_system_configuration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "provider_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "customers",
        sa.Column("last_issuance_job_id", sa.String(length=64), nullable=True),
    )

    op.add_column("proposals", sa.Column("chassis_number", sa.String(length=64), nullable=True))
    op.add_column("proposals", sa.Column("engine_number", sa.String(length=64), nullable=True))
    op.add_column("proposals", sa.Column("engine_rating", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("make_code", sa.String(length=32), nullable=True))
    op.add_column("proposals", sa.Column("model_code", sa.String(length=32), nullable=True))
    op.add_column("proposals", sa.Column("agent_code", sa.String(length=64), nullable=True))
    op.add_column(
        "proposals", sa.Column("intermediary_name", sa.String(length=255), nullable=True)
    )
    op.add_column("proposals", sa.Column("ira_number", sa.String(length=64), nullable=True))
    op.add_column(
        "proposals", sa.Column("provider_note_oid", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "proposals", sa.Column("provider_insured_item", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "proposals",
        sa.Column("provider_document_number", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("provider_amount_to_pay", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "provider_request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "provider_response_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("proposals", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.add_column("proposals", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index("ix_proposals_chassis_number", "proposals", ["chassis_number"])
    op.create_index("ix_proposals_provider_note_oid", "proposals", ["provider_note_oid"])
    op.create_index(
        "ix_proposals_provider_document_number", "proposals", ["provider_document_number"]
    )

    op.add_column("policies", sa.Column("chassis_number", sa.String(length=64), nullable=True))
    op.add_column("policies", sa.Column("engine_number", sa.String(length=64), nullable=True))
    op.add_column("policies", sa.Column("engine_rating", sa.Integer(), nullable=True))
    op.add_column("policies", sa.Column("make_code", sa.String(length=32), nullable=True))
    op.add_column("policies", sa.Column("model_code", sa.String(length=32), nullable=True))
    op.add_column("policies", sa.Column("agent_code", sa.String(length=64), nullable=True))
    op.add_column(
        "policies", sa.Column("intermediary_name", sa.String(length=255), nullable=True)
    )
    op.add_column("policies", sa.Column("ira_number", sa.String(length=64), nullable=True))
    op.add_column(
        "policies", sa.Column("provider_note_oid", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "policies", sa.Column("provider_insured_item", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "policies",
        sa.Column("provider_document_number", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "policies",
        sa.Column("provider_amount_to_pay", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "policies", sa.Column("provider_payment_txn", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "policies",
        sa.Column("provider_commencement_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "policies",
        sa.Column("provider_expiry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("policies", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.add_column("policies", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index("ix_policies_chassis_number", "policies", ["chassis_number"])
    op.create_index("ix_policies_provider_note_oid", "policies", ["provider_note_oid"])
    op.create_index(
        "ix_policies_provider_document_number", "policies", ["provider_document_number"]
    )
    op.create_index("ix_policies_provider_payment_txn", "policies", ["provider_payment_txn"])

    op.add_column(
        "certificates",
        sa.Column("provider_cert_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("local_relative_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("local_stored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "certificates", sa.Column("correlation_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "certificates", sa.Column("request_id", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "ix_certificates_local_relative_path", "certificates", ["local_relative_path"]
    )


def downgrade() -> None:
    op.drop_index("ix_certificates_local_relative_path", table_name="certificates")
    op.drop_column("certificates", "request_id")
    op.drop_column("certificates", "correlation_id")
    op.drop_column("certificates", "file_size_bytes")
    op.drop_column("certificates", "content_sha256")
    op.drop_column("certificates", "local_stored_at")
    op.drop_column("certificates", "local_relative_path")
    op.drop_column("certificates", "provider_cert_url")

    op.drop_index("ix_policies_provider_payment_txn", table_name="policies")
    op.drop_index("ix_policies_provider_document_number", table_name="policies")
    op.drop_index("ix_policies_provider_note_oid", table_name="policies")
    op.drop_index("ix_policies_chassis_number", table_name="policies")
    for col in (
        "request_id",
        "correlation_id",
        "provider_expiry_at",
        "provider_commencement_at",
        "provider_payment_txn",
        "provider_amount_to_pay",
        "provider_document_number",
        "provider_insured_item",
        "provider_note_oid",
        "ira_number",
        "intermediary_name",
        "agent_code",
        "model_code",
        "make_code",
        "engine_rating",
        "engine_number",
        "chassis_number",
    ):
        op.drop_column("policies", col)

    op.drop_index("ix_proposals_provider_document_number", table_name="proposals")
    op.drop_index("ix_proposals_provider_note_oid", table_name="proposals")
    op.drop_index("ix_proposals_chassis_number", table_name="proposals")
    for col in (
        "request_id",
        "correlation_id",
        "provider_response_payload",
        "provider_request_payload",
        "provider_amount_to_pay",
        "provider_document_number",
        "provider_insured_item",
        "provider_note_oid",
        "ira_number",
        "intermediary_name",
        "agent_code",
        "model_code",
        "make_code",
        "engine_rating",
        "engine_number",
        "chassis_number",
    ):
        op.drop_column("proposals", col)

    op.drop_column("customers", "last_issuance_job_id")
    op.drop_column("customers", "provider_payload")
