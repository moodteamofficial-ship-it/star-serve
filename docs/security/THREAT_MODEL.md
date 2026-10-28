# Star Serve — Threat Model (Phase 1 Baseline)

## Scope

Authentication, session management, multi-tenancy, RBAC, API edge controls, audit, job tracking.

## STRIDE Summary

| Category | Example | Control |
|----------|---------|---------|
| Spoofing | Stolen refresh token | Rotation, reuse detection, HttpOnly cookies |
| Tampering | Client sends `tenant_id` / amount | Ignore client tenant; server-side amounts later |
| Repudiation | Denied privileged action | Append-only audit + job events |
| Information disclosure | Cross-tenant IDOR | TenantContext + RLS + 404/403 policy |
| Denial of service | Login flooding | Redis rate limits + lockout |
| Elevation of privilege | Mass-assign `is_admin` | Explicit schemas; deny unknown fields |

## Trust Boundaries

1. Browser ↔ API (untrusted)
2. API ↔ PostgreSQL / Redis (trusted network)
3. API ↔ External providers (semi-trusted; validate all responses)
4. Platform admin ↔ Tenant data (explicit elevation only)

## Abuse Cases (must have automated tests)

- Agency A user reads Agency B customer by UUID
- Agent escalates to tenant admin via PATCH body
- Expired / forged / algorithm-confused JWT
- Refresh token replay after rotation
- Suspended tenant continues business APIs
- Login enumeration via timing/message differences (mitigate to best effort)

## Residual Risks

- Insider platform operator with break-glass — mitigated by audit + time box
- Provider compromise — mitigated by least data sent, validation, fail-safe states
- Dependency CVE — mitigated by scanning + pinning
