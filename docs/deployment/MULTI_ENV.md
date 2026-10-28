# Multi-environment & data planes

## Goals

- Isolate **staging**, **live**, and **backup** data completely — separate databases, never a shared-table flag
- Support **Supabase**, **Google Cloud SQL**, or local Postgres without rewriting app code
- Keep **all secrets server-side** (Secret Manager / `.env`) — never in Vite or API payloads
- Let each user switch planes from the SPA (profile → **Data** switcher)

## How a Google-style engineer isolates this

| Approach | Use? | Why |
|----------|------|-----|
| Separate DB / project per plane | **Yes** | Physical isolation; one bug cannot read/write the other plane |
| Separate API process per plane | **Yes** | Each process binds one `DATABASE_URL`; sessions stamped with `app_env` |
| Separate Postgres schema in one DB | Weak | Shared roles/backups/ops mistakes still cross planes |
| `is_staging` / `environment` column on rows | **No** | One missing `WHERE` = live data leak or corruption |

Star Serve uses **separate databases + separate API deployments**. The frontend only changes which **public API host** it calls.

```
SPA  ──Data: Staging──►  api-staging (APP_ENV=development|staging)  →  starserve_staging DB
     ──Data: Live─────►  api-live    (APP_ENV=production)           →  starserve_live DB
     ──Data: Backup──►  api-backup  (APP_ENV=backup)               →  starserve_backup DB
```

Product mapping:

| UI | `APP_ENV` | `data_plane` (meta) | Database |
|----|-----------|---------------------|----------|
| Staging (dev) | `development` | `staging` | staging DSN |
| Staging | `staging` | `staging` | staging DSN |
| Live | `production` | `live` | production DSN |
| Backup | `backup` | `backup` | restored / archival DSN |

**Backup** is a separate database restored from a live snapshot (or continuous replica). Treat it as read-mostly for incident review — not a place to write new policies.

### User preference vs session binding

| Field | Table | Meaning |
|-------|-------|---------|
| `preferred_app_env` | `users` | User's chosen target plane — updated by env switcher (`PATCH /auth/preferred-env`); frontend syncs `localStorage` from `/me` |
| `app_env` | `sessions` | **This API deployment** at login time (`APP_ENV` from server) — used to reject cross-host session reuse |

Sessions always stamp `app_env` from the server process, not from the frontend toggle alone. To get `production` in sessions, authenticate against the Live API (`APP_ENV=production`).

`GET /api/v1/meta/runtime` returns `app_env` + `data_plane` labels only — never DSNs.

## Security model (non-negotiable)

| Layer | Holds secrets? | Role |
|-------|----------------|------|
| Browser / Vite (`VITE_*`) | **No** | Public API HTTPS URLs only |
| FastAPI process | **Yes** | `DATABASE_URL`, JWT PEMs, Redis, provider keys |
| `GET /api/v1/meta/runtime` | **No** | Labels only (`app_env`, `data_plane`, provider name, public Supabase project ref) |

The frontend **Data** toggle only changes which API host the SPA calls. Each API deployment already has its own `DATABASE_URL`. Switching never downloads a DSN.

## How to switch databases

Set `DB_PROVIDER` to `auto` (default), `supabase`, `cloud_sql`, `local`, or `generic`.

### Supabase (current default project)

- Project ref: `wbasegyvtchdmkfkyoei`
- Prefer the **transaction pooler** (`:6543` / `*.pooler.supabase.com`) from Cloud Run
- Set `DB_SSL_MODE=require` and `DB_NULL_POOL=true` in Cloud Run
- Create **separate databases or projects** per plane (do not share one schema for staging + live + backup)

```bash
# Example (password from Supabase dashboard — store in Secret Manager)
DATABASE_URL=postgresql+asyncpg://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
DB_PROVIDER=supabase
SUPABASE_PROJECT_REF=wbasegyvtchdmkfkyoei
```

### Google Cloud SQL

```bash
DB_PROVIDER=cloud_sql
DATABASE_URL=postgresql+asyncpg://starserve:SECRET@CLOUD_SQL_PRIVATE_IP:5432/starserve_prod
DB_SSL_MODE=require
```

Use the Cloud SQL Auth Proxy / Python Connector in production networking; never open the instance to `0.0.0.0/0`.

### Local data planes (docker compose)

```bash
docker compose up -d postgres redis api-staging api-live api-backup
# Migrate each plane:
DATABASE_URL=postgresql+asyncpg://starserve:starserve@localhost:5432/starserve_staging alembic upgrade head
DATABASE_URL=postgresql+asyncpg://starserve:starserve@localhost:5432/starserve_live alembic upgrade head
DATABASE_URL=postgresql+asyncpg://starserve:starserve@localhost:5432/starserve_backup alembic upgrade head
```

| Service | Port | DB |
|---------|------|-----|
| `api-staging` | 8000 | `starserve_staging` |
| `api-live` | 8001 | `starserve_live` |
| `api-backup` | 8002 | `starserve_backup` |

Point the SPA:

```env
VITE_API_URL_DEVELOPMENT=http://localhost:8000/api/v1
VITE_API_URL_STAGING=http://localhost:8000/api/v1
VITE_API_URL_PRODUCTION=http://localhost:8001/api/v1
VITE_API_URL_BACKUP=http://localhost:8002/api/v1
```

`api-live` sets `ALLOW_INSECURE_PRODUCTION=true` for **local docker only**. Never set that on Cloud Run.

If Postgres was created before these DBs existed: `docker compose down -v` once so init recreates `starserve_staging`, `starserve_live`, and `starserve_backup`.

## Isolating environments (Cloud Run)

### Recommended (production-safe)

Deploy **four Cloud Run services** (or revisions with different secrets):

| Service | `APP_ENV` | `data_plane` | Secret `DATABASE_URL` |
|---------|-----------|--------------|------------------------|
| `starserve-api-dev` | `development` | staging | Dev / staging Supabase DB |
| `starserve-api-staging` | `staging` | staging | Staging Supabase DB |
| `starserve-api` | `production` | live | Production Supabase / Cloud SQL |
| `starserve-api-backup` | `backup` | backup | Restored / archival DB |

Point the SPA at them with public URLs only:

```env
VITE_API_URL_DEVELOPMENT=https://…-dev.run.app/api/v1
VITE_API_URL_STAGING=https://…-staging.run.app/api/v1
VITE_API_URL_PRODUCTION=https://…run.app/api/v1
VITE_API_URL_BACKUP=https://…-backup.run.app/api/v1
```

The profile **Data** selector stores the choice in `localStorage` (per browser / user machine) and reloads. Sessions do not cross hosts.

### Single process (local / CI)

Optionally set env-specific DSNs; `APP_ENV` selects one at boot:

```env
APP_ENV=staging
DATABASE_URL_DEVELOPMENT=…
DATABASE_URL_STAGING=…
DATABASE_URL_PRODUCTION=…
DATABASE_URL_BACKUP=…
```

## Cloud Run cost + 500k-user readiness

| Lever | Why |
|-------|-----|
| Staging `minScale: 0` | Pay ~$0 when idle |
| Prod `minScale: 1`, `512Mi`, CPU throttling on | Lower idle cost with acceptable warm latency |
| Supabase/Cloud SQL **transaction pooler** + `DB_NULL_POOL=true` | Avoid `instances × pool_size` connection storms |
| `containerConcurrency: 40–80` | More RPS per instance → fewer billable instances |
| Redis rate limits + RLS + tenant scoping | Protect DB under burst traffic |
| Long work → jobs (not request thread) | Keep 60s request timeout; scale workers separately |

Rough capacity sketch: with concurrency 80 and 20 max instances (this project's current Cloud Run CPU quota in `europe-west1`) you can absorb thousands of concurrent HTTP requests; the pooler and Postgres IOPS become the real ceilings—not Cloud Run itself. Request a quota increase before raising `maxScale`.

## What never goes over the API

- `DATABASE_URL` / passwords
- JWT private keys / PEMs
- `ENCRYPTION_KEY`, `CSRF_SECRET`
- M-Pesa / SMS / email provider secrets
- Supabase **service role** key (if used later, backend-only)

Production refuses to boot with placeholder `CSRF_SECRET`, `ENCRYPTION_KEY`, or local default DSNs (unless `ALLOW_INSECURE_PRODUCTION` is explicitly set for local dual-plane docker).
