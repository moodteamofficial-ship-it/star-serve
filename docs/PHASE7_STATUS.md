# Phase 7 — Reports, Platform/Tenant Admin, Dedicated DB Path

## Completed

- **Reports**: tenant-scoped aggregates (`POLICIES_SUMMARY`, `PAYMENTS_SUMMARY`, `CUSTOMERS_SUMMARY`, `NOTIFICATIONS_SUMMARY`, `AUDIT_ACTIVITY`) with `report_runs` + RLS + `REPORT_GENERATION` jobs
- **Audit read API**: list/filter/get events (`audit:read`) — append-only; secrets scrubbed at write
- **Tenant settings**: `GET/PATCH /tenants/me` branding & contact; tenants cannot change DB mode via settings
- **Platform admin**: list/get tenants, status changes, coarse `/platform/metrics` (no PII)
- **Dedicated DB path**:
  - Unified `DatabaseMode` on resolver
  - `register_tenant_dedicated_dsn` + startup bootstrap
  - `POST /tenants/{id}/database-mode` (platform only; DSN never returned in API)
- Frontend: Reports, Audit, Settings, Platform pages
- Migration `0006_phase7_reports_admin`

## APIs

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/reports/types` | `reports:read` |
| GET | `/api/v1/reports` | `reports:read` |
| GET | `/api/v1/reports/{id}` | `reports:read` |
| POST | `/api/v1/reports` | `reports:read` |
| GET | `/api/v1/audit/events` | `audit:read` |
| GET | `/api/v1/audit/events/{id}` | `audit:read` |
| GET | `/api/v1/tenants` | `platform:tenant:manage` |
| GET | `/api/v1/tenants/{id}` | `platform:tenant:manage` |
| GET | `/api/v1/tenants/me` | authenticated |
| GET | `/api/v1/tenants/me/settings` | `tenant:manage` \| `settings:manage` |
| PATCH | `/api/v1/tenants/me` | `tenant:manage` \| `settings:manage` |
| POST | `/api/v1/tenants/{id}/status` | `platform:tenant:manage` |
| POST | `/api/v1/tenants/{id}/database-mode` | `platform:tenant:manage` |
| GET | `/api/v1/platform/metrics` | `platform:metrics:read` |

## Apply migration & permissions

```bash
cd backend
alembic upgrade head
python scripts/seed_phase7.py
```

## Dedicated database notes

1. Platform sets `database_mode=DEDICATED_DATABASE` + PostgreSQL DSN.
2. Engine is registered in-process (`TenantDatabaseResolver`).
3. Schema must be migrated against the dedicated URL separately (same Alembic revisions).
4. Moving a tenant is configuration + data migration — repository APIs stay unchanged.

## Enterprise readiness gate

- Tenant isolation on reports/audit (scoped queries + RLS)
- Platform metrics contain counts only
- DSN never exposed in JSON responses
- Mass assignment blocked on settings (`extra: forbid`)

## Next

Post-v1.0 hardening: ARQ workers for heavy report exports, object storage for report files, full per-request dedicated session routing in `get_db`.
