# Phase 4 — Proposals & Policies

## Completed

- Proposal lifecycle with mandatory checks:
  1. Tenant customer validation
  2. Provider policy check
  3. Double-insurance check (blocks if detected)
  4. Authoritative premium from provider (client premiums rejected)
  5. Provider proposal create
  6. Submit → approve → issue policy
- Policy lifecycle: `PENDING_PAYMENT` → `ACTIVE` / `CANCELLED`
- Idempotency-Key support on proposal create
- Partial unique index: one open proposal per tenant+vehicle+product
- RLS on `proposals` and `policies`
- NullInsuranceProvider stubs for offline/local workflow
- Frontend Proposals + Policies pages
- Migration `0003_phase4_proposals_policies`

## APIs

| Method | Path | Permission |
|--------|------|------------|
| POST | `/api/v1/proposals` | `proposal:create` |
| GET | `/api/v1/proposals` | `proposal:read` |
| GET | `/api/v1/proposals/{id}` | `proposal:read` |
| POST | `/api/v1/proposals/{id}/approve` | `proposal:approve` |
| POST | `/api/v1/proposals/{id}/reject` | `proposal:approve` |
| POST | `/api/v1/proposals/{id}/cancel` | `proposal:update` |
| POST | `/api/v1/proposals/{id}/issue-policy` | `policy:create` |
| GET | `/api/v1/policies` | `policy:read` |
| GET | `/api/v1/policies/{id}` | `policy:read` |
| POST | `/api/v1/policies/{id}/activate` | `policy:update` |
| POST | `/api/v1/policies/{id}/cancel` | `policy:cancel` |

## Apply migration

```bash
cd backend
alembic upgrade head
```

Phase 5: Payments, wallet, certificates — **done**. See [PHASE5_STATUS.md](PHASE5_STATUS.md).

## Next

Phase 6: documents, notifications, richer reporting.
