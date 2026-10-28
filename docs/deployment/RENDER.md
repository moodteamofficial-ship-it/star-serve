# Deploy Star Serve on Render (SPA + API)

**Primary production path:** frontend and backend as separate Render web
services. You do **not** need Cloud Run or GCP billing for the API if you use
**local Docker + Docker Hub/GHCR** or **Render Git builds** (see below).

| Service | Typical deploy | Health |
|---------|----------------|--------|
| SPA (`starserve-dashboard`) | Git `frontend/` (Docker) on `moodteamofficial-ship-it/star-serve` | `/ready` |
| API (`starserve-api`) | Git `backend/` or Docker Hub / GHCR | `/health` |

Do **not** use GAR `web:render` on Render — GCP billing blocks image pulls. Same-origin `/api/v1` is proxied by nginx to `API_UPSTREAM`.

## Full stack on Render (frontend + backend)

| Component | Render service | Role |
|-----------|----------------|------|
| SPA | `starserve-dashboard` | quote domain, `/dashboard`, proxies `/api/v1` |
| API | `starserve-api` | `https://starserve-api.onrender.com` |

Dashboard env (set by `./scripts/render/apply-dashboard-render.sh`):

- `API_UPSTREAM=starserve-api.onrender.com` (host only)
- `SPA_BASE_PATH=/dashboard`

The browser always calls **same-origin** `/api/v1`; nginx forwards to the API service (same as the old Cloud Run setup).

**Deploy the API** (pick one):

```bash
export RENDER_API_KEY=rnd_...   # never commit

# A) Docker Hub — after: docker login
export DOCKERHUB_USER=your-dockerhub-user
./scripts/render/build-api-local.sh
./scripts/render/migrate-local.sh
./scripts/render/deploy-render-all.sh

# B) GitHub — push this repo (v1.0) to GitHub, connect Render to the repo
export RENDER_GIT_REPO=https://github.com/YOURORG/starserve-v1
./scripts/render/deploy-render-all.sh git
```

**Not the same as “Connections”:** Account Settings → **Connections** lists OAuth apps
that call the Render API. Git deploys use **Git Deployment Credentials** (Account
Settings → **Account Security** → **Git Deployment Credentials** → Add → GitHub) and
the [Render GitHub App](https://github.com/apps/render) must include your repo under
**Repository access** (configure at [github.com/apps/render/installations](https://github.com/apps/render/installations/new)).

Then mount GCS secret file on **starserve-api** and confirm `curl https://starserve-api.onrender.com/health` → 200 and sign-in works.

### Manual Web Service + one command (recommended)

In Render UI, create **Web Service** only (no env typing):

| UI field | Value |
|----------|--------|
| Name | `starserve-api` |
| Public Git URL | `https://github.com/moodteamofficial-ship-it/star-serve` |
| Root directory | `backend` |
| Health check | `/health` |
| Docker context | `.` |
| Dockerfile | `./Dockerfile` |

Leave **Environment** empty. After **Create**, on your machine:

```bash
export RENDER_API_KEY=rnd_...   # never commit
cd v1.0
./scripts/render/sync-api-after-create.sh
```

That applies health/Docker fixes, all plain + secret vars from `.env`, and triggers a redeploy.
Add **Secret File** `gcs-sa.json` once in the dashboard (GCS service account JSON).

Optional: repo root [`render.yaml`](../../render.yaml) Blueprint lists non-secret defaults.

## Path A — No GCP (recommended)

Build and migrate on your machine; Render pulls from Docker Hub or builds from Git.

```bash
cd v1.0
chmod +x scripts/render/*.sh

./scripts/render/build-api-local.sh
./scripts/render/migrate-local.sh

docker login
DOCKER_IMAGE=docker.io/YOURUSER/starserve-api:latest ./scripts/render/publish-api-image.sh

export RENDER_API_KEY=rnd_...   # never commit
RENDER_API_IMAGE=docker.io/YOURUSER/starserve-api:latest ./scripts/render/apply-production.sh
```

**Git instead of a registry** (Render builds `v1.0/backend/Dockerfile` on each deploy):

```bash
export RENDER_API_KEY=rnd_...
RENDER_API_REPO=https://github.com/YOURORG/StarServe ./scripts/render/apply-production.sh
```

Blueprint: [`render-from-git.yaml`](../../render-from-git.yaml).

Still mount GCS credentials on the API service for certificates/PDFs (`GOOGLE_APPLICATION_CREDENTIALS`) — that is storage only, not Cloud Run.

**SPA image wired to Render API** (same-origin `/api/v1` → `starserve-api.onrender.com`):

```bash
./scripts/render/build-dashboard-local.sh
DOCKER_IMAGE=docker.io/YOURUSER/starserve-dashboard:render ./scripts/render/publish-dashboard-image.sh
export RENDER_API_KEY=rnd_...
RENDER_DASHBOARD_IMAGE=docker.io/YOURUSER/starserve-dashboard:render ./scripts/render/apply-dashboard-render.sh
```

Or keep the current GAR image and only refresh env: `./scripts/render/apply-dashboard-render.sh`

## Path B — GCP Artifact Registry (optional)

Use when billing is active and you already push `api:render` / `web:render`.

Marketing site: `https://starserveinsuranceagency.com/`  
App: `https://quote.starserveinsuranceagency.com/dashboard/`

## Path B details — Artifact Registry

### 1. Registry credentials (GAR services)

Artifact Registry:

```text
europe-west1-docker.pkg.dev/star-serve-508614/starserve/
```

Create a GCP service account with `roles/artifactregistry.reader`, download a
JSON key, then in each Render service:

| Field | Value |
|--------|--------|
| Username | `_json_key` |
| Password | full JSON key contents |

## 2. Build and push images

From `v1.0/`:

```bash
chmod +x scripts/render/build-api.sh scripts/gcp/build-frontend-render.sh
./scripts/render/build-api.sh
API_UPSTREAM=starserve-api.onrender.com ./scripts/gcp/build-frontend-render.sh
```

Override `RENDER_API_HOST` / `API_UPSTREAM` if your Render service hostname differs.

Images:

```text
europe-west1-docker.pkg.dev/star-serve-508614/starserve/api:render
europe-west1-docker.pkg.dev/star-serve-508614/starserve/web:render
```

Redeploy each Render service after pushing a new tag.

## 3. API web service (`starserve-api`)

| Field | Value |
|--------|--------|
| Language | **Deploy an existing image from a registry** |
| Image URL | `…/api:render` |
| Health check path | `/health` |

### Environment (non-secret)

```bash
RENDER_API_HOST=starserve-api.onrender.com ./scripts/render/print-production-env.sh
```

Paste the output into Render → Environment. Set secret variables from the same
values as `scripts/gcp/sync-secrets.sh production` / Secret Manager
`starserve-prod-*` (never commit them).

To **rotate** CSRF / encryption / guest signing / webhook secrets and generate a
production JWT pair into `backend/secrets/prod_jwt_*.pem`:

```bash
./scripts/gcp/rotate-production-secrets.sh          # updates .env + Secret Manager when billing is on
UPLOAD_GCP=false ./scripts/gcp/rotate-production-secrets.sh   # .env only (Render path)
export RENDER_API_KEY=rnd_...
SKIP_DASHBOARD_CUTOVER=true ./scripts/render/apply-production.sh
```

**Note:** A new `ENCRYPTION_KEY` cannot decrypt DB fields encrypted with the old
key. A new JWT pair logs everyone out; new guest signing invalidates open guest links.

### GCS (certificates, PDFs, uploads)

Cloud Run used the runtime service account. On Render:

1. Create (or reuse) a GCP SA with `roles/storage.objectAdmin` on bucket `star_serve`.
2. Render → **Secret files** → mount JSON at `/etc/secrets/gcs-sa.json`.
3. Env: `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcs-sa.json`.

### Migrations (before or after first deploy)

One-shot from your machine (uses Secret Manager, does not print `DATABASE_URL`):

```bash
./scripts/render/migrate.sh production
```

Do **not** set `RUN_MIGRATIONS=true` on the live API service (multi-instance race).

### Callbacks (BirdView, M-Pesa)

`BIRDVIEW_CALLBACK_BASE_URL` and `MPESA_CALLBACK_BASE_URL` must be the public
API base, e.g. `https://starserve-api.onrender.com` (or a custom domain you
attach to the API service). Re-run `print-production-env.sh` after the URL is
known and update Render env.

## 4. SPA web service (`starserve-dashboard`)

| Field | Value |
|--------|--------|
| Image URL | `…/web:render` |
| Health check path | `/ready` |

### Environment

| Key | Value |
|------|--------|
| `PORT` | `8080` |
| `API_UPSTREAM` | `starserve-api.onrender.com` (**host only**, no `https://`) |
| `SPA_BASE_PATH` | `/dashboard` |

### Custom domain

1. Attach `quote.starserveinsuranceagency.com` in Render.
2. DNS CNAME `quote` → `starserve-dashboard.onrender.com` (or Render’s target).

## 5. Routing (unchanged behaviour)

| Path | Behaviour |
|------|-----------|
| `/` | 302 → `/dashboard/` |
| `/dashboard/…` | SPA |
| `/api/v1/…` | Nginx → Render API (same-origin cookies) |
| `/ready` | SPA health |

Guest quotes: browser calls same-origin `/api/v1`; nginx proxies to the API.
`CORS_ORIGINS` must include `https://quote.starserveinsuranceagency.com` (included
in `print-production-env.sh`).

Email deep links: `EMAIL_APP_URL=https://quote.starserveinsuranceagency.com/dashboard`.

## 6. Cutover checklist

1. Build/push `api:render`; create API service; run `migrate.sh production`.
2. Set secrets + `print-production-env.sh` output; verify `GET …/health`.
3. Update BirdView/M-Pesa callback URLs to the new API base if providers pin hostnames.
4. Build/push `web:render` with `API_UPSTREAM=<api-host>`; redeploy dashboard.
5. Smoke-test quote flow, staff login, STK, certificate download on quote domain.
6. Keep Cloud Run revisions for rollback (switch `API_UPSTREAM` back to `*.run.app`).

Reference blueprint: [`render.yaml`](../../render.yaml) at repo `v1.0/`.

## Render API (automation)

Create an API key in Render → Account Settings. **Never commit it** — export in the shell only:

```bash
export RENDER_API_KEY=rnd_...
chmod +x scripts/render/*.sh
./scripts/render/apply-production.sh
```

This creates `starserve-api` (if missing), syncs env from `v1.0/.env`, waits for `/health`, then sets dashboard `API_UPSTREAM`.

## Local development

`npm run dev` + Data **Dev** → local `:8000`. Staging/Live switcher may still
target Cloud Run for comparison; production fallback in Vite can point at the
Render API host — see `frontend/.env.example`.
