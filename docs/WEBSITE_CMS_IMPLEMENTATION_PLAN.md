# Star Serve public website and CMS — Stage 1 architecture assessment

**Status:** Planning only. **Do not deploy** until staging sign off (per product directive, November 2026).

**Primary marketing host:** [https://www.starserveinsuranceagency.com/](https://www.starserveinsuranceagency.com/)  
**Existing quote and app:** [https://quote.starserveinsuranceagency.com/dashboard/](https://quote.starserveinsuranceagency.com/dashboard/)  
**Brand line:** STAR SERVE INSURANCE AGENCY — *Insurance, Just a Touch Away.*

---

## 1. Executive summary

Star Serve already has a production grade insurance platform (FastAPI, PostgreSQL, React/Vite SPA, Render). The **quote** experience lives on `quote.*` under `/dashboard/` with same origin API proxy. There is **no database driven marketing CMS yet** and **no full public marketing site** in the repo today. The current “welcome” on the quote app is the **embedded quote wizard** (“Just one touch”), not the editorial marketing homepage described in the product brief.

This plan integrates a **premium public website + PWA + Super Admin CMS** into the **same monorepo and design tokens**, without duplicating auth, payments, quotations, or agent flows. Deployment to www remains **out of scope until explicitly requested**.

---

## 2. Existing system audit (verified in repo)

### 2.1 Frontend (`v1.0/frontend`)

| Area | Finding |
|------|---------|
| Stack | React 18, Vite, React Router, TanStack Query, TypeScript |
| Routing | Single `App.tsx`: `/` → `WelcomePage` (guest quote wizard), `/login`, `/register-agent`, `/app/*` staff dashboard |
| Basename | `appBasename()` from `VITE_BASE_PATH` — production quote uses `/dashboard/` |
| Design system | CSS variables in `src/styles.css` (`--brand-green`, `--brand-blue`, `--paper`, `--radius`, Poppins). **Not** yet extracted to `/constants/` modules (user rule: migrate gradually in Stage 2) |
| Theming | `ThemeProvider` + `data-theme` light/dark (shared with dashboard) |
| UI kit | `components/ui/*` (Button patterns via CSS classes, `TextField`, `Select`, `Modal`, `PhoneField`, etc.) |
| Public quote | `QuoteWizardPage` guest mode, claims modals, agent registration |
| Marketing link | `WelcomeTopbar` already points logo to `https://www.starserveinsuranceagency.com/` |
| PWA | **No** `manifest.webmanifest` or service worker in repo today |
| SEO | SPA only; no prerender/SSR layer |

### 2.2 Backend (`v1.0/backend`)

| Area | Finding |
|------|---------|
| API | FastAPI, `/api/v1` prefix, modular routers |
| Auth | Cookie session, CSRF, RBAC permissions on routes |
| Insurance ops | Products, proposals, policies, payments (Daraja), claims, USSD, agents, commissions |
| Platform admin | `platform:*` permissions; no `website:*` module |
| Media | GCS/local via `stored_files` patterns; suitable for CMS media extension |
| Migrations | Alembic through `0043_*`; next CMS migration should be `0044_website_cms` |
| Enquiries | **No** dedicated public “contact/enquiry” CMS entity; guest flows exist for quotes/claims/agents |

### 2.3 Infrastructure (Render)

| Host | Role today |
|------|----------------|
| `quote.starserveinsuranceagency.com` | Dashboard nginx → `starserve-api`, SPA at `/dashboard/` |
| `www` / apex | CORS allowed on API; **marketing origin not served from this repo’s deploy yet** |
| API | `starserve-api.onrender.com` |

Nginx dashboard template explicitly notes marketing TLS is **separate** from quote app host.

---

## 3. Target experience map

### 3.1 Domain and routing (recommended)

Keep **one API** and **one Postgres**. Split **presentation** by hostname (no second auth system):

```
www.starserveinsuranceagency.com     → Public marketing SPA (basename /)
starserveinsuranceagency.com         → 301 to www (or same marketing app)
quote.starserveinsuranceagency.com   → Existing app SPA (basename /dashboard/)
```

**Implementation options (pick one in Stage 2 sign off):**

| Option | Pros | Cons |
|--------|------|------|
| **A. Two Render web services, one repo** (`frontend/` marketing Dockerfile + existing dashboard Dockerfile) | Clear caches, independent deploy of CMS content vs app | Two builds to maintain |
| **B. One nginx, two static roots + `map $host`** | Single service | More complex nginx; careful PWA scope |
| **C. One Vite app, host based route trees** | One build artifact | Larger bundle unless code split by entry |

**Recommendation:** **Option A** for production reliability: `starserve-marketing` (www) + `starserve-dashboard` (quote). Shared `src/components`, `src/styles.css`, tokens. Marketing build: `VITE_BASE_PATH=/`, `VITE_SITE_ROLE=marketing`. Dashboard unchanged.

### 3.2 Public routes (marketing app)

| Route | Purpose |
|-------|---------|
| `/` | Homepage (CMS sections) |
| `/services` | Service directory |
| `/services/:slug` | Seven product detail pages |
| `/about` | About |
| `/get-covered` | Conversion hub + enquiry form |
| `/offline` | PWA offline fallback (public only) |

**CTA destinations (configurable in CMS, defaults):**

- Get Instant Cover → `https://quote.starserveinsuranceagency.com/dashboard/` (+ product query params where defined)
- Become an Agent → `https://quote.starserveinsuranceagency.com/dashboard/register-agent`
- Agent Login → `https://quote.starserveinsuranceagency.com/dashboard/login`

### 3.3 Quote app (unchanged behavior)

Preserve `/dashboard/` routes, guest quote, `#r=` referral QR, agent flows, USSD, payments. Marketing must **not** replace `WelcomePage` on quote host unless product explicitly merges “instant cover” into quote only.

---

## 4. CMS architecture (new module)

### 4.1 Backend module layout

```
backend/app/modules/website/
  models.py          # pages, sections, revisions, navigation, partners, settings, audit
  enums.py           # section types, publish status
  schemas.py         # public vs admin DTOs
  router_public.py   # unauthenticated published content only
  router_admin.py    # permission gated mutations
  service.py         # draft/publish, reorder, optimistic locking
  seed.py            # idempotent initial content (draft stats flagged unverified)
  sanitize.py        # link validation, rich text policy
  cache.py           # published snapshot + invalidation hooks
```

### 4.2 Suggested tables (high level)

- `website_pages` — slug, title, SEO fields, publish revision id
- `website_sections` — page_id, section_type, sort_order, visibility, JSON content (validated schema per type)
- `website_revisions` — immutable snapshots for publish/rollback
- `website_navigation` — header/footer links (typed destinations)
- `website_partners` — Birdview, Changa Fuel, QR metadata
- `website_media` — FK to existing file storage keys, alt text, variants
- `website_settings` — global contact, social, default CTAs
- `website_enquiries` — public form submissions (PII, spam controls)
- `website_admin_audit` — who published what (align with existing `AuditService`)

**Permissions (new):** `website:read`, `website:edit`, `website:publish`, `website:media`, `website:settings`, `website:audit` — granted to platform super admin role seed, not agents.

### 4.3 Public API shape

- `GET /api/v1/website/bootstrap` — navigation, settings, homepage sections, revision token (ETag)
- `GET /api/v1/website/pages/{slug}` — published page + sections
- `GET /api/v1/website/services` — published service summaries
- `POST /api/v1/website/enquiries` — rate limited, validated enquiry (integrates notifications)

**Cache:** Redis or in process TTL for bootstrap (optional on Render); **must** invalidate on publish (version bump in bootstrap).

### 4.4 Admin UI (dashboard)

New area under `/app/website` (or `/app/platform/website`):

Website Management → Overview, Pages, Homepage Sections, Services, Partners, Navigation & Footer, Media, SEO, Settings, Enquiries, History.

Reuse `config-card`, `config-scene-*`, USSD admin patterns for forms (structured fields, not raw JSON).

### 4.5 Section registry (approved types)

`hero`, `service_grid`, `editorial_split`, `statistics` (each metric: value, label, **verified** flag, default hidden until verified), `partner_showcase`, `agent_promotion`, `benefits`, `faq`, `cta`, `contact_strip`.

Rendering: React components only; CMS stores JSON validated by Pydantic models per type.

---

## 5. Content and copy rules (engineering enforced)

1. **Branding:** Reuse `--brand-*`, `--ink`, `--paper`, logo assets in `frontend/public/`, existing button/topbar patterns.
2. **No generic AI aesthetic:** Editorial layouts, varied section rhythm, no decorative gradient stacks.
3. **Customer facing copy:** Avoid using **hyphens or dash characters to join phrases** in marketing copy (product rule). Implement a optional CMS lint warning; do not mutate URLs, API paths, or legal names.
4. **Facts:** Seed trust metrics (2 min quote, 98% satisfaction, etc.) as **draft + unverified + hidden** until admin confirms.
5. **Insurance legal:** Do not invent coverage terms; service detail pages pull from CMS with empty blocks until compliance fills them.

---

## 6. PWA strategy

| Surface | PWA |
|---------|-----|
| Marketing (`www`) | New manifest (`scope: /`), icons from existing logo, service worker caches static assets + **published bootstrap JSON** (short TTL), offline page |
| Quote dashboard | **Do not** add conflicting SW on same origin paths; quote host keeps existing behavior unless product requests installable dashboard later |

Service worker rules: never cache `/api/v1/auth/*`, payments, or authenticated responses. Publish invalidation via bootstrap `contentVersion` query param bump.

---

## 7. Security checklist (build time)

- Admin CMS: all mutations behind permissions + audit
- Public endpoints: read only published; no draft leakage (RLS or status filter)
- Enquiry POST: honeypot, rate limit, CAPTCHA optional phase 2
- Media uploads: reuse existing file validation pipeline
- XSS: structured content + link allowlist (`https`, `tel`, `mailto`, internal paths)
- CSP: extend existing API/frontend CSP for marketing fonts/images only as needed

---

## 8. Phased delivery (aligned to master prompt)

| Stage | Deliverable | Deploy? |
|-------|-------------|---------|
| **1** | This document + sign off on routing Option A/B/C | No |
| **2** | Extract shared tokens to `frontend/src/constants/theme.ts` (re export CSS vars) | No |
| **3** | Alembic `0044_website_cms` + models | Local/staging only |
| **4** | Public + admin APIs + seed (draft content) | Staging |
| **5** | Super Admin Website Management UI | Staging |
| **6** | Marketing SPA pages + section components | Staging |
| **7** | Content import from brief (verified flags off for stats) | Staging |
| **8** | Wire CTAs to quote/agent URLs + referral params | Staging |
| **9** | Marketing PWA manifest + SW | Staging |
| **10** | Bootstrap cache, ETag, SEO, sitemap route | Staging |
| **11** | Security tests + regression suite for quote/payments | Staging |
| **12** | Staging UAT on www + quote | Staging |
| **13** | Production deploy (www service + DNS) | **Only when approved** |
| **14** | Smoke tests + delivery report | Production |

**Stage 13 (approved):** deploy path lives in
[`docs/deployment/MARKETING_WWW.md`](./deployment/MARKETING_WWW.md)
(`starserve-marketing` + GoDaddy www/apex cutover; quote DNS untouched).

---

## 9. Integration points (must not break)

- Guest quote wizard and `#r=` / `#a=` deep links
- Agent registration and approval emails (quote URLs)
- M-Pesa Daraja callbacks on quote host
- USSD callback on quote host
- Staff dashboard RBAC and RLS
- Definite issuance and certificate generation
- Existing notification and enquiry workflows (extend, do not fork)

---

## 10. Open decisions for product / legal

1. Confirm **apex** redirect: `starserveinsuranceagency.com` → `www`?
2. Confirm **Scan for Instant Cover** destination (QR page on marketing vs quote deep link).
3. Provide **verified** trust statistics or keep hidden at launch.
4. Service detail legal copy source (Definite/product catalog vs manual CMS).
5. Kenya DPA privacy copy for enquiry form retention period.
6. Hosting for **www** on Render: new service vs external CDN.

---

## 11. Next engineering actions (when you say proceed)

1. Sign routing option (recommended: **two Render services, shared repo**).
2. Scaffold `website` backend module + migration `0044`.
3. Add marketing entry (`frontend/src/marketing/` or route tree) without changing quote `Dockerfile` defaults.
4. Implement bootstrap API + one homepage hero section end to end on **local** dev.

No production or Render deploy until you revoke the “do not deploy” instruction.
