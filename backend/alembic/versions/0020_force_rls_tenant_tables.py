"""FORCE row-level security on tenant-scoped tables.

``ENABLE ROW LEVEL SECURITY`` does not apply to the table owner, and the
application connects as the owner. Every domain table therefore had tenant
policies that were never actually evaluated: isolation rested entirely on the
repository layer remembering to add a tenant predicate. ``FORCE`` makes the
policies apply to the owner too, so a query that forgets its tenant filter
returns nothing instead of the whole platform.

Auth tables (0008) and login_lockouts (0012) are already FORCE'd and keep their
own policies.

The policies are recreated first because the originals did not honour
``app.rls_bypass``, which the signed-webhook and login paths rely on to look a
row up before a tenant is known.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0020_force_rls_tenant_tables"
down_revision: Union[str, None] = "0019_guest_quote_channel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# tenant_id is NOT NULL on these: rows always belong to exactly one tenant.
TENANT_TABLES = (
    "branches",
    "departments",
    "teams",
    "user_branches",
    "user_teams",
    "jobs",
    "job_events",
    "idempotency_keys",
    "customers",
    "intermediaries",
    "proposals",
    "policies",
    "payments",
    "wallets",
    "wallet_transactions",
    "certificates",
    "notifications",
    "report_runs",
)

# Platform-owned reference rows carry tenant_id IS NULL and are readable by all.
REFERENCE_TABLES = (
    "insurance_products",
    "vehicle_makes",
    "cancellation_reasons",
)

_TENANT_PREDICATE = """
  current_setting('app.rls_bypass', true) = 'true'
  OR current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""

_REFERENCE_PREDICATE = """
  current_setting('app.rls_bypass', true) = 'true'
  OR current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id IS NULL
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""

_LEGACY_PREDICATE = """
  current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""

_LEGACY_REFERENCE_PREDICATE = """
  current_setting('app.is_platform_admin', true) = 'true'
  OR tenant_id IS NULL
  OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
"""


def _recreate(table: str, predicate: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
        USING ({predicate})
        """
    )


def upgrade() -> None:
    for table in TENANT_TABLES:
        _recreate(table, _TENANT_PREDICATE)
    for table in REFERENCE_TABLES:
        _recreate(table, _REFERENCE_PREDICATE)

    # audit_events is tenant-scoped for reads, but platform-level events (a failed
    # login for an unknown email) legitimately have no tenant. Allow writing those
    # without allowing anyone to read another tenant's trail.
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_audit_events ON audit_events")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_audit_events ON audit_events
        USING ({_TENANT_PREDICATE})
        """
    )
    op.execute("DROP POLICY IF EXISTS audit_events_platform_insert ON audit_events")
    op.execute(
        """
        CREATE POLICY audit_events_platform_insert ON audit_events
        FOR INSERT
        WITH CHECK (tenant_id IS NULL)
        """
    )

    for table in TENANT_TABLES + REFERENCE_TABLES + ("audit_events",):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # PostgREST / Supabase anon roles have no business touching domain tables.
        for role in ("PUBLIC", "anon", "authenticated", "authenticator"):
            op.execute(
                f"""
                DO $$
                BEGIN
                  BEGIN
                    EXECUTE 'REVOKE ALL ON TABLE {table} FROM {role}';
                  EXCEPTION WHEN undefined_object THEN
                    NULL;
                  END;
                END $$;
                """
            )


def downgrade() -> None:
    for table in TENANT_TABLES + REFERENCE_TABLES + ("audit_events",):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS audit_events_platform_insert ON audit_events")
    for table in TENANT_TABLES + ("audit_events",):
        _recreate(table, _LEGACY_PREDICATE)
    for table in REFERENCE_TABLES:
        _recreate(table, _LEGACY_REFERENCE_PREDICATE)
