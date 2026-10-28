# Star Serve v1.0

Enterprise multi-tenant insurance management & distribution platform.

## Documentation

- [Architecture Package](docs/ARCHITECTURE.md) — start here
- [Threat Model](docs/security/THREAT_MODEL.md)
- [Render (production SPA + API)](docs/deployment/RENDER.md) — manual deploy; no auto-deploy
- [Cloud Run](docs/deployment/CLOUD_RUN.md) — optional staging / rollback (GCP `star-serve-508614`)

## Quick start (local Homebrew — recommended when Docker is unavailable)

Local SPA (**Dev**) talks to **local uvicorn** on `:8000`. Deployed quote domain
uses Render for both SPA and API (see [RENDER.md](docs/deployment/RENDER.md)).

**Backend (terminal 1):**

```bash
cd v1.0
chmod +x scripts/dev-backend.sh
./scripts/dev-backend.sh --migrate
```

First-time DB/seeds (once):

```bash
./scripts/setup_local_db.sh
cd backend && source .venv/bin/activate
export JWT_PRIVATE_KEY_PATH=./secrets/dev_jwt_private.pem
export JWT_PUBLIC_KEY_PATH=./secrets/dev_jwt_public.pem
alembic upgrade head
python scripts/seed_phase1.py
python scripts/seed_phase2.py
python scripts/seed_phase5.py
python scripts/seed_phase6.py
python scripts/seed_phase7.py
```

**Frontend (terminal 2):**

```bash
cd v1.0/frontend && npm install && npm run dev
```

Open `http://localhost:5173` — Data → **Dev**. Staging/Live in the switcher can
target Cloud Run or Render for compare (see `frontend/.env.example`).

## Phase status

**Phase 7 complete:** reports, audit browse, tenant settings, platform admin, dedicated DB path.

See [Phase 1](docs/PHASE1_STATUS.md) … [Phase 7](docs/PHASE7_STATUS.md).
