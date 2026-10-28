# Star Serve — Architecture Package (v1.0)

**Status:** Design approved for Phase 1 implementation  
**Audience:** Engineering, Security, DevOps, Product  
**Principle:** Secure multi-tenant insurance OS — modular monolith first, extractable domains later

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [System Architecture Diagram](#2-system-architecture-diagram)
3. [Frontend Architecture](#3-frontend-architecture)
4. [Backend Architecture](#4-backend-architecture)
5. [Multi-Tenant Strategy](#5-multi-tenant-strategy)
6. [Database Schema](#6-database-schema)
7. [RBAC / Permission Model](#7-rbac--permission-model)
8. [Authentication Architecture](#8-authentication-architecture)
9. [Security Architecture](#9-security-architecture)
10. [External Integration Architecture](#10-external-integration-architecture)
11. [Definite Assurance Adapter](#11-definite-assurance-adapter)
12. [Payment Architecture](#12-payment-architecture)
13. [Notification Architecture](#13-notification-architecture)
14. [API Standards](#14-api-standards)
15. [Folder Structure](#15-folder-structure)
16. [Development Phases](#16-development-phases)
17. [Threat Model](#17-threat-model)
18. [Testing Strategy](#18-testing-strategy)
19. [Deployment Architecture](#19-deployment-architecture)
20. [Architectural Reasoning](#20-architectural-reasoning)

---

## 1. High-Level Architecture

Star Serve is a **modular monolith** with clear domain boundaries:

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| Frontend | React + TypeScript + Vite | UX only; never holds secrets |
| API | FastAPI (Python 3.12+) | AuthZ, tenancy, orchestration |
| Workers | ARQ (Redis) | Async jobs, retries, notifications |
| Data | PostgreSQL (portable) | Source of truth + RLS |
| Cache / rate limit / jobs | Redis | Distributed state |
| Object storage | GCS / S3-compatible | Documents, exports |
| Secrets | Google Secret Manager (prod) | Credentials, keys |

### Runtime model

```
Browser (HttpOnly cookies)
    → CDN / WAF / LB
    → Cloud Run (stateless FastAPI × N)
    → PostgreSQL (shared or dedicated per tenant)
    → Redis
    → External providers (via adapters)
    → ARQ workers (Cloud Run Jobs / always-on worker service)
```

### Domain modules (extractable later)

`auth` · `tenants` · `users` · `roles` · `customers` · `intermediaries` · `insurance` · `proposals` · `policies` · `payments` · `wallets` · `documents` · `notifications` · `reports` · `audit` · `jobs` · `integrations`

Business logic lives in **services**. Persistence in **tenant-aware repositories**. HTTP routes stay thin.

---

## 2. System Architecture Diagram

```
                         ┌─────────────────────────────────────┐
                         │           Clients (Browser)         │
                         │     React SPA · HttpOnly cookies    │
                         └─────────────────┬───────────────────┘
                                           │ HTTPS
                         ┌─────────────────▼───────────────────┐
                         │     Cloud DNS · CDN · WAF · LB      │
                         └─────────────────┬───────────────────┘
                                           │
                         ┌─────────────────▼───────────────────┐
                         │     Google Cloud Run (FastAPI)      │
                         │  RequestID · JobID · Auth · Rate    │
                         │  TenantContext · RBAC · Audit       │
                         └─┬───────────┬───────────┬───────────┘
                           │           │           │
              ┌────────────▼──┐  ┌─────▼─────┐  ┌─▼──────────────┐
              │  PostgreSQL   │  │   Redis   │  │ Object Storage │
              │ Shared / Ded. │  │ cache/RL  │  │ docs / exports │
              │ + RLS policies│  │ sessions  │  └────────────────┘
              └───────────────┘  │ job queue │
                                 └─────┬─────┘
                                       │
                                 ┌─────▼─────┐
                                 │ ARQ Workers│
                                 └─────┬─────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
┌────────▼────────┐         ┌──────────▼──────────┐      ┌───────────▼──────────┐
│ InsuranceProvider│         │  PaymentProvider    │      │ NotificationProvider │
│ DefiniteAssurance│         │ M-Pesa / Card / ... │      │ SMS / Email / WA     │
└─────────────────┘         └─────────────────────┘      └──────────────────────┘

TENANCY
  PLATFORM ──► AGENCY A / B / C
                 └── Branch → Department → Team → User
                       └── Customers · Agents · Policies · Jobs · Payments
```

### Job lifecycle spine

```
JOB-{ulid}
├── CLIENT_CHECK → WAITING_EXTERNAL → COMPLETED
├── PREMIUM_CALCULATION
├── DOUBLE_INSURANCE_CHECK
├── PROPOSAL_CREATION (idempotent)
├── PAYMENT_INITIATION → WAITING_PAYMENT
├── CERTIFICATE_GENERATION
└── NOTIFICATION (async)
```

Every hop carries: `job_id`, `request_id`, `correlation_id`, `tenant_id`, `user_id`.

---

## 3. Frontend Architecture

### Stack

- React 18 + TypeScript (strict)
- Vite
- TanStack Query (server state)
- React Router
- Zod schemas (UX validation; backend remains authoritative)
- Feature-based folders

### Rules

1. **No secrets** in Vite env — only public API base URL, app name, feature flags.
2. Auth via **HttpOnly Secure SameSite cookies** (access + refresh rotation).
3. Central `apiClient` with CSRF header when cookie auth is used.
4. Permissions hide UI; **never** authorize on the client alone.
5. Domain APIs: `authApi`, `customerApi`, `proposalApi`, … — no fetch in components.
6. Dashboard nav filtered by effective permissions.

### Feature layout

```
src/features/{auth,dashboard,customers,proposals,policies,payments,
              administration,platform}/
```

Each feature owns pages, components, hooks, and local schemas.

---

## 4. Backend Architecture

### Request pipeline

```
HTTP
 → RequestId / JobId middleware
 → Security headers
 → CORS (explicit allowlist)
 → Body size limits
 → Rate limit (Redis)
 → Auth (JWT from cookie/header)
 → TenantContext (from identity — never from body)
 → Permission dependency
 → Route (thin)
 → Service
 → TenantAwareRepository
 → DB (RLS session vars set)
 → Audit + Job events
 → ApiResponse envelope
```

### Layering

| Layer | Owns |
|-------|------|
| `api/routes` | HTTP mapping, DI wiring |
| `modules/*/schemas` | Pydantic I/O |
| `modules/*/service` | Business rules, workflows |
| `modules/*/repository` | SQLAlchemy, tenant scope |
| `modules/*/models` | ORM entities |
| `integrations/*` | Provider adapters |
| `core/*` | Cross-cutting concerns |

### Internal RPC

In-process service calls via DI for Phase 1–5. Optional gRPC later behind the same service interfaces — no public RPC surface.

### Database portability

```
Settings.DATABASE_URL
 → asyncpg / psycopg
 → SQLAlchemy 2.x engine
 → Alembic migrations
```

Works with Supabase Postgres, Cloud SQL, RDS, Azure Flexible Server, private Postgres. No Supabase Auth/Realtime/Storage in business logic unless isolated behind adapters.

### TenantDatabaseResolver

```
tenant.database_mode ∈ {SHARED, DEDICATED}
 → resolver.session(tenant_id)
 → same repository APIs
```

Moving a tenant to dedicated infra is configuration + data migration, not an app rewrite.

---

## 5. Multi-Tenant Strategy

### Isolation defense-in-depth

1. **Identity-derived tenant** — JWT/`sub` → user → `tenant_id` (never client-supplied).
2. **TenantContext** contextvar — set once per request.
3. **TenantAwareRepository** — auto-scopes all queries; rejects cross-tenant writes.
4. **PostgreSQL RLS** — `SET LOCAL app.tenant_id` / `app.is_platform_admin`.
5. **Suspended tenants** — blocked from business operations at middleware/service gate.
6. **Job / audit / idempotency** rows all carry `tenant_id`.

### Tenant types

`PLATFORM` · `INSURANCE_AGENCY` · `BROKER` · `CORPORATE_CLIENT` · `ENTERPRISE`

### Tenant status

`ACTIVE` · `PENDING` · `SUSPENDED` · `DISABLED` · `ARCHIVED`

### Hierarchy

```
Platform → Tenant → Branch → Department → Team → User
```

Authorization evaluates: user permissions ∩ tenant ∩ branch/team scope ∩ resource ownership.

### Platform vs agency access

Platform admins do **not** get blanket customer PII access. Cross-tenant data access requires explicit privileged permission, reason-for-access, audit, and (later) JIT/time-boxed elevation.

---

## 6. Database Schema

### Core tables (Phase 1)

| Table | Purpose |
|-------|---------|
| `tenants` | Tenant master + plan + `database_mode` + branding JSON |
| `branches` | Org units under tenant |
| `departments` | Optional under branch |
| `teams` | Optional under department |
| `users` | Identity; `tenant_id` FK; password hash (Argon2id) |
| `user_branches` | M:N membership |
| `user_teams` | M:N membership |
| `roles` | Tenant-scoped or system roles |
| `permissions` | Global catalog (`customer:read`, …) |
| `role_permissions` | M:N |
| `user_roles` | Assignment (+ optional branch scope) |
| `sessions` | Refresh tokens / device tracking / revocation |
| `audit_events` | Append-only security/business audit |
| `jobs` | Job lifecycle |
| `job_events` | Append-only job timeline |
| `idempotency_keys` | Critical-op dedupe |

### Later domain tables (Phase 2+)

`customers`, `intermediaries`, `products_cache`, `proposals`, `policies`, `payments`, `wallets`, `documents`, `notifications`, `reports`, …

### Conventions

- UUID primary keys (UUIDv7 preferred for time-order)
- `tenant_id` on every tenant-owned row
- Soft-delete where legally needed (`deleted_at`)
- Optimistic locking (`version`) on financial/stateful entities
- Indexes on `(tenant_id, …)` query patterns
- Check constraints for enums/status machines

### RLS pattern

```sql
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON customers
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true))::uuid);
```

App role is non-superuser; migrations run with a separate migrator role.

---

## 7. RBAC / Permission Model

### Entities

`Permission` → `Role` → `UserRole` (+ optional `branch_id` scope)  
`TenantRole` templates seed new agencies.

### Permission catalog (examples)

```
customer:create|read|update|delete
proposal:create|read|update|approve
policy:create|read|update|cancel
payment:create|read|refund
agent:create|approve
tenant:manage
user:create|disable
role:manage
audit:read
reports:read
settings:manage
job:read|retry|cancel
platform:tenant:manage
platform:metrics:read
```

### Evaluation algorithm

```
1. Load user roles for (tenant_id [, branch_id])
2. Expand permissions
3. Check required permission for action
4. Check resource.tenant_id == context.tenant_id
5. Check org scope (branch/team/owner) if applicable
6. Deny by default
```

Frontend mirrors permission checks for UX only.

---

## 8. Authentication Architecture

### Flows

- Email/password (Argon2id)
- Email verification
- Password reset (one-time, rate-limited)
- MFA-ready (`mfa_methods` table stub)
- Account lockout after N failures
- Session list + revoke

### Tokens

| Token | Lifetime | Storage |
|-------|----------|---------|
| Access JWT (RS256/ES256) | ~15 min | HttpOnly cookie |
| Refresh (opaque random) | ~7–30 d | HttpOnly cookie + hashed in `sessions` |

### Claims (minimal)

```json
{ "sub": "<user_uuid>", "sid": "<session_uuid>", "typ": "access" }
```

No roles, permissions, or PII in JWT. Server loads authz on each request.

### Hardening

- Refresh rotation + reuse detection → revoke session family
- Password change → revoke sessions
- Disable user → revoke sessions + reject immediately
- CSRF: double-submit / synchronizer token for cookie auth
- Uniform login errors (no user enumeration)

---

## 9. Security Architecture

### Standards mapped

OWASP ASVS · OWASP Top 10 · OWASP API Security Top 10 · CWE · NIST CSF principles

### Control layers

| Layer | Controls |
|-------|----------|
| Edge | TLS, WAF, CDN, size limits |
| App | AuthN/Z, tenancy, validation, rate limits, headers |
| Data | RLS, encryption at rest, least-privilege DB user |
| Ops | Secrets Manager, scanning, monitoring, VAPT |

### Security headers

`HSTS` · `CSP` · `X-Content-Type-Options` · `Referrer-Policy` · `Permissions-Policy` · frame ancestors

### SSRF

Outbound URLs only from config allowlists. No user-supplied fetch URLs.

### Fail-safe

External failure → job `WAITING_EXTERNAL_SERVICE` / `FAILED` — never invent payment/certificate success.

### Break-glass

Time-boxed, reason-required, fully audited elevation — no hidden backdoors.

---

## 10. External Integration Architecture

```
Business Service
  → Port (Protocol / ABC)
  → Adapter (DefiniteAssuranceProvider, MpesaProvider, …)
  → HTTP Client (timeouts, retries, circuit breaker, correlation)
  → Mapper → Star Serve domain schemas
```

Rules:

- Never expose raw provider payloads to React
- Never log credentials or full sensitive bodies
- Circuit breaker: CLOSED → OPEN → HALF_OPEN
- Idempotent retries only when safe
- Provider failures map to stable error codes (`INSURANCE_PROVIDER_UNAVAILABLE`)

---

## 11. Definite Assurance Adapter

```
modules/integrations/insurance/
  ports.py                 # InsuranceProvider ABC
  definite_assurance/
    client.py              # HTTP Basic Auth client
    schemas.py             # Provider DTOs
    mapper.py              # → Star Serve models
    service.py             # Implements InsuranceProvider
    exceptions.py
```

**Base URL:** configurable (UAT default `https://uat.definiteassurance.com/api/v1`)  
**Auth:** HTTP Basic from Secret Manager — never in frontend

### Covered operations (ports)

`check_client`, `create_client`, `check_intermediary`, `register_intermediary`, `get_products`, `get_makes`, `calculate_premium`, `check_policy`, `create_proposal`, `get_policy_details`, `check_double_insurance`, `initiate_payment`, `pay_extension`, `check_credit_limit`, `check_wallet_balance`, `top_up_wallet`, `initiate_extension`, `generate_certificate`, `cancel_policy`, `get_cancellation_reasons`

Reference data (products/makes/reasons) cached in Redis with TTL.

**Phase note:** Adapter scaffolding in Phase 3; ports defined early to keep domains provider-agnostic.

---

## 12. Payment Architecture

```
PaymentService
  → validate amount server-side (authoritative premium)
  → create PaymentIntent (INITIATED)
  → PaymentProvider.initiate()
  → webhook (signature + replay + amount checks)
  → SUCCESS / FAILED
  → continue insurance workflow
  → audit + job events
```

States: `INITIATED` → `PENDING` → `SUCCESS` | `FAILED` | `REVERSED` | `CANCELLED`

Providers: `MpesaProvider`, `CardProvider`, `BankProvider`, `WalletProvider` behind `PaymentProvider`.

Idempotency-Key required on initiation. No blind payment retries.

---

## 13. Notification Architecture

```
NotificationService.send(channel, template, recipient, context)
  → queue job
  → SmsProvider | EmailProvider | WhatsAppProvider | PushProvider
```

Business code never imports Twilio/Africa's Talking/etc. directly. Failures retry with backoff; delivery status stored for audit.

---

## 14. API Standards

### Versioning

`/api/v1/...` — breaking changes → `/api/v2/...`

### Success envelope

```json
{
  "success": true,
  "data": {},
  "message": "Operation completed successfully",
  "requestId": "REQ-...",
  "jobId": "JOB-..."
}
```

### Error envelope

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid information",
    "details": []
  },
  "requestId": "REQ-...",
  "jobId": "JOB-..."
}
```

### Status codes

400 · 401 · 403 · 404 · 409 · 413 · 422 · 429 · 500 · 502 · 503

Never return stack traces, SQL errors, or internal hosts.

### Pagination

`page` + `limit` (capped) or cursor for large sets. Search rate-limited + indexed + tenant-scoped.

### Idempotency

Header `Idempotency-Key` for mutations that matter.

### Health

`GET /health` (liveness) · `GET /ready` (DB + Redis) — no secrets/diagnostics dump.

---

## 15. Folder Structure

```
v1.0/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── security/
│   └── deployment/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/           # config, security, db, logging, middleware, exceptions, responses, dependencies
│   │   ├── api/            # routers aggregation
│   │   ├── modules/        # domain modules
│   │   ├── integrations/   # provider adapters
│   │   └── workers/
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── services/
│   │   └── ...
│   ├── package.json
│   └── Dockerfile
├── infra/
│   ├── docker/
│   └── cloud-run/
├── scripts/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## 16. Development Phases

| Phase | Scope | Gate |
|-------|-------|------|
| **1** | Core, DB, Auth, Tenancy, RBAC, middleware, audit, jobs skeleton | Tenant isolation tests green |
| **2** | Customers, intermediaries, products, vehicle ref data | CRUD + RBAC + isolation |
| **3** | Definite Assurance adapter + client/intermediary APIs | Provider mocked + contract tests |
| **4** | Proposals, premium, policies, double-insurance | Workflow integrity tests |
| **5** | Payments, wallet, certificates | Idempotency + webhook security |
| **6** | Notifications (SMS/Email/WhatsApp) | Async delivery tests |
| **7** | Reports, platform/tenant admin, dedicated DB path | Enterprise readiness |

**Rule:** Do not start Phase N+1 until Phase N security reviews (tenancy, authz, validation, logging leakage) pass.

---

## 17. Threat Model

### Assets

Tenant data · PII · financial transactions · API credentials · JWT signing keys · audit integrity · certificates

### Actors

External attacker · malicious agent · compromised account · malicious tenant admin · insider platform op · buggy integration

### Critical threats → mitigations

| Threat | Mitigation |
|--------|------------|
| Cross-tenant IDOR/BOLA | Identity tenant + repo scope + RLS + tests |
| Privilege escalation | Explicit permissions; no JWT roles |
| Auth brute force | Rate limit, lockout, uniform errors |
| Refresh replay | Rotation + reuse detection |
| Payment tampering | Server-side amounts; webhook verify |
| SQL injection | Parameterized ORM only |
| XSS | CSP, no `dangerouslySetInnerHTML`, sanitize |
| CSRF | SameSite + CSRF token |
| SSRF | Config allowlist only |
| Secret leak | Secret Manager; no Vite secrets |
| Provider outage abuse | Circuit breaker; fail-safe job states |
| Mass assignment | Explicit Pydantic update schemas |

Full STRIDE matrix: `docs/security/THREAT_MODEL.md`.

---

## 18. Testing Strategy

### Pyramids

1. **Unit** — services, permission evaluation, mappers, state machines  
2. **Integration** — DB + Redis (Testcontainers)  
3. **API** — FastAPI TestClient with real middleware  
4. **Security** — tenant A/B isolation, BOLA, JWT abuse, mass assignment, rate limits  
5. **Contract** — Definite Assurance / payment adapters with recorded fixtures  

### Mandatory security fixtures

Tenant A/B · User A/B · Resource A/B → cross access must yield **403 or 404** (consistent disclosure policy).

### CI gates

Ruff · Black · MyPy · Pytest · ESLint · Prettier · `tsc --strict` · dependency/secret/container scans

---

## 19. Deployment Architecture

### Environments

`development` · `staging` · `production` — isolated credentials and provider URLs.

### Local

`docker-compose`: API, worker, Postgres, Redis, Mailhog (dev).

### Production (GCP reference)

```
Internet → Cloud DNS → Cloud Armor/CDN → HTTPS LB
  → Cloud Run (API)
  → Cloud Run / GCE (workers)
  → Cloud SQL Postgres (or Supabase Postgres via private connectivity)
  → Memorystore Redis
  → GCS
  → Secret Manager
```

### Cloud Run constraints

- Stateless; no local FS state  
- Connection pooling sized for concurrency (e.g. PgBouncer / Cloud SQL connector)  
- Graceful shutdown  
- `/health`, `/ready`  
- Min/max instances, CPU boost, request timeout tuned per endpoint class  

### Portability

Same app image runs against any managed Postgres; infra adapters only in `infra/` and `core/config`.

---

## 20. Architectural Reasoning

1. **Modular monolith first** — insurance workflows are transactional and tightly coupled; premature microservices multiply failure modes without isolation benefit we already get from tenancy.

2. **Tenant isolation as a platform primitive** — IDOR across agencies is an existential risk; central TenantContext + repositories + RLS beats hope-based `WHERE` clauses.

3. **Provider ports** — Definite Assurance will change; payments will multiply; business modules must not import vendor SDKs.

4. **Jobs as the spine** — insurance ops are multi-step and external; `job_id` makes support, audit, and VAPT reconstruction possible.

5. **Stateless Cloud Run** — horizontal scale and cheap HA; Redis/DB own durable state.

6. **Database-portable Postgres** — enterprises demand dedicated DBs and different clouds; SQLAlchemy + Alembic + resolver keeps the app movable.

7. **Minimal JWT claims** — tokens are bearer credentials, not authorization databases; revocation and RBAC stay server-side.

8. **Phase discipline** — shipping proposals before auth/tenancy/RBAC would cement insecure patterns; Phase 1 is the security foundation on purpose.

---

## Golden Rule Checklist

Every critical operation must answer:

- WHO? WHICH TENANT? WHAT resource? WHAT permission?  
- WHAT `job_id` / `request_id`? WHAT externals? WHAT result?  
- Retry-safe? WHAT audit event? Reconstructable?

If not — the implementation is incomplete.
