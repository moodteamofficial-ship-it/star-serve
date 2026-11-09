# Deploy marketing www on Render + GoDaddy cutover

**Goal:** serve **this repo’s** CMS marketing site at
[https://www.starserveinsuranceagency.com/](https://www.starserveinsuranceagency.com/)
without breaking the quote dashboard, logins, payments, or emails.

| Host | Service | Role |
|------|---------|------|
| `www.starserveinsuranceagency.com` | **new** `starserve-marketing` | Public CMS site (basename `/`) |
| `starserveinsuranceagency.com` (apex) | same marketing service | Prefer 301 → `www` |
| `quote.starserveinsuranceagency.com` | existing `starserve-dashboard` | **Do not change** — `/dashboard/`, `/api/v1` proxy |
| `starserve-api.onrender.com` | existing `starserve-api` | Shared API + Postgres |

CTAs on the marketing site already point at
`https://quote.starserveinsuranceagency.com/dashboard/…` (cover, agent login,
register). Email / M-Pesa / USSD stay on the quote host.

---

## 0. What must stay untouched

- GoDaddy DNS for **`quote`** (CNAME → `starserve-dashboard.onrender.com` or current Render target)
- Render service **`starserve-dashboard`** and its custom domain
- API callbacks (`BIRDVIEW_CALLBACK_BASE_URL`, `MPESA_CALLBACK_BASE_URL`)
- `EMAIL_APP_URL=https://quote.starserveinsuranceagency.com/dashboard`
- MX / email DNS records for `@starserveinsuranceagency.com`

Only change DNS for **`www`** and (optionally) the **apex** A/ALIAS records that
currently point at the **old** marketing host.

---

## 1. Deploy `starserve-marketing` on Render

Code must be on the GitHub repo Render already builds from
(`moodteamofficial-ship-it/star-serve` or your current production remote),
including `frontend/Dockerfile.marketing`.

### Option A — script (recommended)

```bash
cd v1.0
export RENDER_API_KEY=rnd_...   # never commit
export RENDER_GIT_REPO=https://github.com/moodteamofficial-ship-it/star-serve
export RENDER_GIT_BRANCH=main   # or the branch Render already deploys

./scripts/render/deploy-marketing.sh
```

That creates **`starserve-marketing`**, sets `API_UPSTREAM=starserve-api.onrender.com`,
`SITE_ROLE=marketing`, refreshes API `CORS_ORIGINS`, and waits for `/ready`.

### Option B — Render UI

1. **New → Web Service** → same GitHub repo as the API/dashboard.
2. Settings:

| Field | Value |
|-------|--------|
| Name | `starserve-marketing` |
| Root directory | `frontend` (or `v1.0/frontend` if the Git root is the monorepo parent) |
| Dockerfile path | `./Dockerfile.marketing` |
| Docker context | `.` |
| Health check | `/ready` |
| Region | Frankfurt (match API) |

3. Env vars:

| Key | Value |
|-----|--------|
| `PORT` | `8080` |
| `SITE_ROLE` | `marketing` |
| `SPA_BASE_PATH` | *(empty)* |
| `API_UPSTREAM` | `starserve-api.onrender.com` |

4. Deploy, then open `https://starserve-marketing.onrender.com/` and confirm:
   - homepage sections load
   - `https://starserve-marketing.onrender.com/api/v1/website/bootstrap` → 200
   - **Get Instant Cover** → quote dashboard (new tab / full URL)
   - Agent Login → `…/dashboard/login`

Do **not** point GoDaddy at Render until this smoke test passes.

### Option C — local image

```bash
./scripts/render/build-marketing-local.sh
docker login
DOCKER_IMAGE=docker.io/YOU/starserve-marketing:render \
  ./scripts/render/publish-marketing-image.sh
export RENDER_API_KEY=rnd_...
export RENDER_MARKETING_IMAGE=docker.io/YOU/starserve-marketing:render
./scripts/render/deploy-marketing.sh
```

---

## 2. Attach custom domains on Render (before GoDaddy)

In Render → **starserve-marketing** → **Custom Domains**, add:

1. `www.starserveinsuranceagency.com`
2. `starserveinsuranceagency.com` (apex)

Render shows the exact DNS target (usually a CNAME like
`starserve-marketing.onrender.com`, or A records for apex). Copy those values —
you will paste them into GoDaddy.

Also confirm **starserve-api** `CORS_ORIGINS` includes:

```text
https://www.starserveinsuranceagency.com,https://starserveinsuranceagency.com,https://starserve-marketing.onrender.com
```

(`./scripts/render/apply-marketing-render.sh` and `print-production-env.sh` already do this.)

---

## 3. GoDaddy DNS cutover

Sign in → **My Products** → **starserveinsuranceagency.com** → **DNS** → **Manage DNS**.

### 3.1 Leave these alone

| Type | Name | Purpose |
|------|------|---------|
| CNAME | `quote` | Quote + dashboard |
| MX / TXT / SPF / DKIM | `@` or mail hosts | Email |
| Any records you use for Google Workspace / Microsoft 365 | | |

### 3.2 Point `www` at the new marketing service

Find the existing **`www`** record (A or CNAME to the old site). Edit it:

| Type | Name | Value | TTL |
|------|------|--------|-----|
| CNAME | `www` | `starserve-marketing.onrender.com` *(or the exact host Render shows)* | 600 (or 1 hour) |

If GoDaddy will not CNAME `www` while an A record exists, delete the old A for
`www` first, then add the CNAME.

### 3.3 Apex (`starserveinsuranceagency.com`)

Pick **one**:

**Preferred — redirect apex → www**

- GoDaddy → **Forwarding** → Domain → forward `http(s)://starserveinsuranceagency.com`
  to `https://www.starserveinsuranceagency.com` (permanent / 301), **or**
- Keep apex on Render: add the **A / ALIAS** records Render lists for the apex
  custom domain (replace the old apex A records that pointed at the previous host).

Do **not** leave apex on the old marketing host while `www` is on Render — CTAs
and SEO will split across two codebases.

### 3.4 Propagation

- Lower TTL a day before cutover if you can (e.g. 600 seconds).
- After save, wait for Render → Custom Domains → certificate **Verified**.
- Check: `dig www.starserveinsuranceagency.com` → Render target, not the old IP.

---

## 4. Production smoke checklist (after DNS)

On **https://www.starserveinsuranceagency.com/**:

- [ ] Homepage loads CMS content (hero, partners, stories)
- [ ] `/about`, `/services`, `/get-covered` load
- [ ] Enquiry form submits (200 from `/api/v1/website/enquiries`)
- [ ] **Get Instant Cover** opens quote wizard on **quote.** host
- [ ] **Become an Agent** / **Agent Login** hit `/dashboard/register-agent` and `/dashboard/login`
- [ ] Logo / QR install URL uses www (not localhost)

On **https://quote.starserveinsuranceagency.com/dashboard/** (regression):

- [ ] Guest quote still works
- [ ] Staff / agent login still works
- [ ] Website admin at `/dashboard/app/website` still loads and publishes
- [ ] Publish updates what www shows within ~1 minute (cache TTL)

Rollback if needed: restore previous GoDaddy `www` / apex records; leave quote untouched.

---

## 5. How the pieces stay connected

```
Browser → www (starserve-marketing nginx)
            ├─ static SPA (VITE_SITE_ROLE=marketing)
            └─ /api/v1/*  →  starserve-api  (bootstrap, pages, media, enquiries)

Browser → quote (starserve-dashboard nginx)   ← unchanged
            ├─ /dashboard/* SPA (quote + admin)
            └─ /api/v1/*  →  same starserve-api
```

- One Postgres / one CMS: edits in dashboard **Website** admin publish to the
  same API the marketing site reads.
- Marketing never hosts `/dashboard` — redirects stay on the quote host.
- Cookies for staff sessions stay on the quote origin (SameSite=None across
  HTTPS); public CMS reads do not need auth cookies.

---

## 6. Local reference

```bash
# Marketing SPA on :5174 → local API :8000
cd frontend && npm run dev:marketing
```

Production build args live in `frontend/Dockerfile.marketing`.
Blueprint stub: `render.yaml` service `starserve-marketing`.
