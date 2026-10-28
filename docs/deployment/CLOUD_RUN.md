# Star Serve — Deployment Architecture

## Targets

| Target | Notes |
|--------|-------|
| Local Homebrew / uvicorn | `APP_ENV=development` on `:8000` — current laptop workflow |
| Local Docker Compose | API, Postgres, Redis per data plane |
| Cloud Run **staging** | `APP_ENV=staging` — same behaviour as local/dev, HTTPS, Secret Manager |
| Cloud Run **production** | `APP_ENV=production` — hardened (no `/docs`, no placeholder secrets) |
| Supabase / Cloud SQL | `DATABASE_URL` only; never in `VITE_*` |

The SPA **Data** switcher only changes which **public API URL** is called. Each Cloud Run service already has its own server-side secrets.

See [MULTI_ENV.md](./MULTI_ENV.md).

## Production on Render (SPA + API)

See [RENDER.md](./RENDER.md). Images `web:render` and `api:render` in Artifact
Registry. Cloud Run production API/SPA are **rollback only** — do not use
`release.sh production` for normal cutovers.

## GCP project

| | |
|--|--|
| Project | `star-serve-508614` |
| Region | `europe-west1` (same continent as the Supabase pooler) |
| Artifact Registry | `europe-west1-docker.pkg.dev/star-serve-508614/starserve/{api,web}` |
| Staging API | `starserve-api-staging` |
| Staging web | `starserve-dashboard-staging` |
| Production API | `starserve-api` |

Credentials never go in the image, git, or Vite. Cloud Run mounts them from **Secret Manager** as env vars (`DATABASE_URL`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, provider passwords, …).

## One-time bootstrap (this machine)

```bash
# APIs, Artifact Registry, least-privilege runtime SAs
./scripts/gcp/bootstrap.sh

# Copy local .env + JWT PEMs into Secret Manager (values are never printed)
./scripts/gcp/sync-secrets.sh staging
./scripts/gcp/sync-secrets.sh production

# Build in Cloud Build (no local Docker), migrate, deploy
./scripts/gcp/release.sh staging
./scripts/gcp/release.sh production
```

### GitHub → Cloud Run (disabled by default)

Pushes to `main` **do not** deploy to Cloud Run. CI still runs lint, unit/security
tests, and frontend build on every push/PR (`ci.yml`).

Cloud Run deploy is **manual only** via Actions → **Deploy backend** →
`workflow_dispatch`, typing `deploy` to confirm. Keep repo secrets
`GCP_WIF_PROVIDER` and `GCP_DEPLOY_SA` if you want that emergency path; omit
them to block all GitHub→GCP deploys.

Primary production: **Render** ([RENDER.md](./RENDER.md)) — `./scripts/render/build-api.sh`,
`./scripts/gcp/build-frontend-render.sh`, then redeploy both Render services.
Cloud Run `release.sh` / `release-frontend.sh` are for staging or emergency rollback.

### Localhost vs deploy

| Where | API |
|-------|-----|
| `npm run dev` + Data **Dev** (default) | Local uvicorn `:8000` via `/api` |
| Data **Staging** / **Live** | Cloud Run (optional compare) |
| [quote…/dashboard](https://quote.starserveinsuranceagency.com/dashboard/) | Render SPA nginx → Render API |

```bash
# Terminal 1 — local API
cd v1.0 && ./scripts/dev-backend.sh --migrate

# Terminal 2 — local SPA
cd v1.0/frontend && npm run dev
```

Deployed SPA builds do not use Vite proxies; Render keeps `API_UPSTREAM` → live API.

## Frontend (SPA) on Cloud Run (optional / rollback)

| | |
|--|--|
| Staging service | `starserve-dashboard-staging` |
| Production service | `starserve-dashboard` (when released) |
| Artifact image | `…/starserve/web` |

```
Browser → starserve-dashboard-staging (nginx + Vite dist)
            ├── /*               static SPA (client-side routes)
            └── /api/*, /health  reverse-proxy → starserve-api-staging
```

Same-origin `/api/v1` keeps auth cookies first-party on the SPA host (same pattern as the local Vite proxy).

```bash
# Build + deploy SPA; updates API CORS_ORIGINS + EMAIL_APP_URL automatically
./scripts/gcp/release-frontend.sh staging

# Redeploy an existing image
./scripts/gcp/deploy-frontend.sh staging \
  europe-west1-docker.pkg.dev/star-serve-508614/starserve/web:staging
```

Frontend build-args are public `VITE_*` paths only (`/api/v1`). Secrets stay on the API service via Secret Manager — never in the SPA image or browser bundle.

## Switching environments in the SPA

After a deploy, `frontend/.env.cloud` is updated with public URLs only:

```env
VITE_API_URL_DEVELOPMENT=http://localhost:8000/api/v1
VITE_API_URL_STAGING=/api/v1
VITE_API_URL_PRODUCTION=/prod-api/v1
```

Copy those into `frontend/.env.local` (or merge) and restart Vite. The profile **Data** control then targets:

| UI | Process | Typical host |
|----|---------|--------------|
| Dev | local uvicorn | `localhost:8000` |
| Staging | Cloud Run staging | `*.run.app` (dev-like: UAT Definite, test STK amount, `/docs`) |
| Live | Cloud Run production | `*.run.app` (hardened) |

Local `APP_DEBUG`, `COOKIE_SECURE=false`, and `COOKIE_SAMESITE=lax` are unchanged. Cloud Run always uses HTTPS cookies (`COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`) so the local SPA can call it cross-site.

`ALLOW_INSECURE_PRODUCTION` is **never** set on Cloud Run.

## Cloud Run Recommendations (cost-aware)

| Setting | Production | Staging / Dev |
|---------|------------|---------------|
| Memory | 512Mi (scale to 1Gi if needed) | 512Mi |
| CPU | 1 | 1 |
| Concurrency | 40–80 | 20–40 |
| Min instances | 1 (latency) or 0 (cheapest) | **1** (guest sessions + STK wait) |
| Max instances | Cap to regional CPU quota (this project: **20**) | 5–10 |
| Request timeout | 180s (pay + certificate) | 180s |
| Startup probe | `/health` | `/health` |
| Startup CPU boost | On | On |
| CPU throttling | On (saves idle cost) | On |
| `DB_NULL_POOL` | `true` with transaction pooler | `true` |

Skeletons: `infra/cloud-run/service.yaml`, `infra/cloud-run/service.staging.yaml`.
Release path: `infra/gcp/cloudbuild.yaml` + `scripts/gcp/*.sh`.

Migrations run as a **Cloud Run Job** (`starserve-migrate-<env>`), not on every API instance boot.

## Secrets (Google Secret Manager)

Mount at runtime only — never bake into the image or `VITE_*` vars:

`DATABASE_URL`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`,
`ENCRYPTION_KEY`, `CSRF_SECRET`, provider credentials.

Runtime service accounts can **access** their env’s secrets only. They cannot deploy or read the other plane’s secrets.

Redis is optional: if `REDIS_URL` is unset, guest sessions reconstruct from the signed cookie (device + IP hashes in the JWT) so Cloud Run scale-out does not drop a quote mid-payment. In-memory rate limits still remain per instance. Add Memorystore later if you need shared rate limits across instances.

Cloud Run disk is ephemeral (`data/certificates`, email PDFs). On Cloud Run set
`STORAGE_BACKEND=gcs` with private bucket `gs://star_serve/{env}/…`. Postgres keeps
relative object keys only; downloads stay on authenticated API routes. Local
`STORAGE_BACKEND=local` still uses `backend/data/` for development.

## Object storage (GCS)

| | |
|--|--|
| Bucket | `gs://star_serve` (non-public, uniform access) |
| Layout | `{staging\|production}/certificates\|email-pdfs\|claims/documents\|avatars/…` |
| Dedup | Default `skip_identical` — same key + sha256 is a no-op; avatars use `overwrite` |
| Access | Cloud Run runtime SA `roles/storage.objectAdmin` only |
| Browser | Never gets raw `gs://` URLs — API streams after authz |

```bash
# One-time IAM (also in bootstrap.sh when the bucket exists)
gcloud storage buckets add-iam-policy-binding gs://star_serve \
  --member="serviceAccount:starserve-api-staging@star-serve-508614.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Optional: seed from local laptop data/
gcloud storage rsync --recursive backend/data/certificates \
  gs://star_serve/staging/certificates
gcloud storage rsync --recursive backend/data/email-pdfs \
  gs://star_serve/staging/email-pdfs
gcloud storage rsync --recursive backend/data/claims/documents \
  gs://star_serve/staging/claims/documents
```

## Network

Postgres and Redis private only. Egress controlled for provider allowlists.
Prefer Supabase pooler or Cloud SQL private IP from Cloud Run VPC connector.
BirdView / M-Pesa callback bases are set to the Cloud Run URL on deploy.
