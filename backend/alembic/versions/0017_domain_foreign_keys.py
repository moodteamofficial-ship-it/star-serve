"""Add foreign keys for domain UUID references (customers → certificates)."""

from typing import Sequence, Union

from alembic import op

revision: str = "0017_domain_foreign_keys"
down_revision: Union[str, None] = "0016_certificate_file_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Required ownership → RESTRICT; optional / actor / denorm → SET NULL.
# Append-only audit_events intentionally omitted (forensic independence).
# String job_key soft-refs (*.job_id as String) intentionally omitted.

_FKS: list[tuple[str, str, str, list[str], list[str], str]] = [
    # (name, source_table, referent_table, local_cols, remote_cols, ondelete)
    ("fk_customers_tenant_id", "customers", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
    ("fk_customers_branch_id", "customers", "branches", ["branch_id"], ["id"], "SET NULL"),
    (
        "fk_customers_assigned_user_id",
        "customers",
        "users",
        ["assigned_user_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_customers_created_by_user_id",
        "customers",
        "users",
        ["created_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_customers_deleted_by_users", "customers", "users", ["deleted_by"], ["id"], "SET NULL"),
    ("fk_proposals_tenant_id", "proposals", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
    ("fk_proposals_customer_id", "proposals", "customers", ["customer_id"], ["id"], "RESTRICT"),
    (
        "fk_proposals_intermediary_id",
        "proposals",
        "intermediaries",
        ["intermediary_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_proposals_branch_id", "proposals", "branches", ["branch_id"], ["id"], "SET NULL"),
    (
        "fk_proposals_created_by_user_id",
        "proposals",
        "users",
        ["created_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_proposals_approved_by_user_id",
        "proposals",
        "users",
        ["approved_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_policies_tenant_id", "policies", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
    ("fk_policies_customer_id", "policies", "customers", ["customer_id"], ["id"], "RESTRICT"),
    ("fk_policies_proposal_id", "policies", "proposals", ["proposal_id"], ["id"], "SET NULL"),
    (
        "fk_policies_intermediary_id",
        "policies",
        "intermediaries",
        ["intermediary_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_policies_branch_id", "policies", "branches", ["branch_id"], ["id"], "SET NULL"),
    (
        "fk_policies_created_by_user_id",
        "policies",
        "users",
        ["created_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_policies_cancelled_by_user_id",
        "policies",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_payments_tenant_id", "payments", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
    ("fk_payments_customer_id", "payments", "customers", ["customer_id"], ["id"], "SET NULL"),
    ("fk_payments_policy_id", "payments", "policies", ["policy_id"], ["id"], "SET NULL"),
    ("fk_payments_proposal_id", "payments", "proposals", ["proposal_id"], ["id"], "SET NULL"),
    (
        "fk_payments_initiated_by_user_id",
        "payments",
        "users",
        ["initiated_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_certificates_tenant_id", "certificates", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
    ("fk_certificates_policy_id", "certificates", "policies", ["policy_id"], ["id"], "RESTRICT"),
    ("fk_certificates_payment_id", "certificates", "payments", ["payment_id"], ["id"], "SET NULL"),
    (
        "fk_certificates_customer_id",
        "certificates",
        "customers",
        ["customer_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_certificates_generated_by_user_id",
        "certificates",
        "users",
        ["generated_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_certificates_last_accessed_by_user_id",
        "certificates",
        "users",
        ["last_accessed_by_user_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_certificate_file_accesses_tenant_id",
        "certificate_file_accesses",
        "tenants",
        ["tenant_id"],
        ["id"],
        "RESTRICT",
    ),
    (
        "fk_certificate_file_accesses_certificate_id",
        "certificate_file_accesses",
        "certificates",
        ["certificate_id"],
        ["id"],
        "RESTRICT",
    ),
    (
        "fk_certificate_file_accesses_policy_id",
        "certificate_file_accesses",
        "policies",
        ["policy_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_certificate_file_accesses_customer_id",
        "certificate_file_accesses",
        "customers",
        ["customer_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "fk_certificate_file_accesses_user_id",
        "certificate_file_accesses",
        "users",
        ["user_id"],
        ["id"],
        "SET NULL",
    ),
    ("fk_jobs_tenant_id", "jobs", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
    ("fk_jobs_user_id", "jobs", "users", ["user_id"], ["id"], "SET NULL"),
    ("fk_jobs_parent_job_id", "jobs", "jobs", ["parent_job_id"], ["id"], "SET NULL"),
    ("fk_job_events_job_id", "job_events", "jobs", ["job_id"], ["id"], "RESTRICT"),
    ("fk_job_events_tenant_id", "job_events", "tenants", ["tenant_id"], ["id"], "RESTRICT"),
]


def upgrade() -> None:
    for name, source, referent, local_cols, remote_cols, ondelete in _FKS:
        op.create_foreign_key(
            name,
            source,
            referent,
            local_cols,
            remote_cols,
            ondelete=ondelete,
        )


def downgrade() -> None:
    for name, source, *_rest in reversed(_FKS):
        op.drop_constraint(name, source, type_="foreignkey")
