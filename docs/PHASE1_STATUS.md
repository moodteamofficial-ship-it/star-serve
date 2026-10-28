# Phase 1 — Implementation Status

## Completed

- Architecture package (`docs/ARCHITECTURE.md` + threat model + Cloud Run notes)
- Modular backend skeleton (FastAPI)
- Config via environment / Secret Manager-ready settings
- Structured logging + `request_id` / `job_id` / `correlation_id`
- Standard API envelopes + centralized exception mapping
- Security middleware: headers, CORS allowlist, CSRF (cookie auth), rate limit
- SQLAlchemy 2.x models: tenants, org hierarchy, users, sessions, RBAC, audit, jobs, idempotency
- Alembic migration `0001_phase1_foundation` with RLS policies enabled
- `TenantAwareRepository` + `TenantDatabaseResolver` (SHARED / DEDICATED hook)
- Auth: Argon2id, RS256 JWT access, rotating refresh sessions, lockout, audit events
- Tenant APIs: create (platform), me, status change
- Job APIs: get, events, cancel, safe retry gate
- Health `/health` + readiness `/ready`
- InsuranceProvider port (no Definite Assurance yet — Phase 3)
- React shell: cookie auth client, CSRF header, permission-filtered nav, dashboard
- Docker Compose + Cloud Run service skeleton + CI workflow
- Unit/security tests for passwords, context, audit scrub, job tenancy

## Intentionally deferred

- Definite Assurance client (Phase 3)
- Proposals / policies (Phase 4)
- Payments / wallet / certificates (Phase 5)
- Notifications (Phase 6)
- Full platform admin UI + dedicated DB provisioning (Phase 7)
- Production FORCE RLS + separate DB roles (documented; implement with infra)

Phase 2 status: see [`PHASE2_STATUS.md`](PHASE2_STATUS.md).

## Local bootstrap

```bash
cd v1.0
cp .env.example .env
docker compose up -d postgres redis
cd backend && source .venv/bin/activate
export JWT_PRIVATE_KEY_PATH=./secrets/dev_jwt_private.pem
export JWT_PUBLIC_KEY_PATH=./secrets/dev_jwt_public.pem
alembic upgrade head
python scripts/seed_phase1.py
uvicorn app.main:app --reload --port 8000
```

Frontend: `cd frontend && npm install && npm run dev`

Seed users (change immediately):

- `admin@starserve.local` / `11111111`
- `admin@agency-a.local` / `11111111`
- `admin@agency-b.local` / `11111111`
