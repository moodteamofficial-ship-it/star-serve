# Phase 2 — Customers, Intermediaries, Products

## Completed

- **Customers**: tenant-scoped CRUD (soft delete), search, assign, audit events
- **Intermediaries**: create/update/list, approve/suspend workflow, audit events
- **Products / vehicle makes / cancellation reasons**: platform catalog + tenant overlays
- Redis cache for reference reads (TTL 1h), invalidated on tenant writes
- Permissions: `agent:read`, `product:read`, `product:manage`
- Alembic migration `0002_phase2_customers_products` + RLS policies
- Frontend pages: Customers, Intermediaries, Products
- Security/validation tests for mass-assignment, identity, tenant miss, approve rules

## APIs

| Method | Path | Permission |
|--------|------|------------|
| POST | `/api/v1/customers` | `customer:create` |
| GET | `/api/v1/customers` | `customer:read` |
| GET | `/api/v1/customers/{id}` | `customer:read` |
| PATCH | `/api/v1/customers/{id}` | `customer:update` |
| DELETE | `/api/v1/customers/{id}` | `customer:delete` |
| POST | `/api/v1/customers/{id}/assign` | `customer:update` |
| POST | `/api/v1/intermediaries` | `agent:create` |
| GET | `/api/v1/intermediaries` | `agent:read` |
| POST | `/api/v1/intermediaries/{id}/approve` | `agent:approve` |
| GET | `/api/v1/products` | `product:read` |
| GET | `/api/v1/vehicle-makes` | `product:read` |
| GET | `/api/v1/cancellation-reasons` | `product:read` |

## Bootstrap

```bash
cd backend
alembic upgrade head
python scripts/seed_phase1.py   # if needed
python scripts/seed_phase2.py   # permissions + reference catalog
```

## Deferred to Phase 3

Definite Assurance live check/create client & intermediary sync — local records are ready with `external_*_ref` fields.
