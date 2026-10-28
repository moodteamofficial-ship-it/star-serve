# Phase 3 — Definite Assurance Integration

## Completed

- `InsuranceProvider` port expanded
- `DefiniteAssuranceClient` with Basic Auth, timeouts, GET retries, circuit breaker, scrubbed logs
- Mapper → Star Serve domain shapes (never expose raw DA payloads to React)
- `DefiniteAssuranceProvider` adapter
- Factory with `NullInsuranceProvider` when credentials are absent
- Orchestration APIs under `/api/v1/insurance/*` with job + audit trails
- Reference sync into tenant product/make/reason overlays
- Unit tests with mocked HTTP

## APIs

| Method | Path | Permission |
|--------|------|------------|
| GET | `/insurance/clients/check?id_number=` | `customer:read` |
| POST | `/insurance/clients/ensure` | `customer:create` |
| GET | `/insurance/intermediaries/check?identification=` | `agent:read` |
| POST | `/insurance/intermediaries/ensure` | `agent:create` |
| POST | `/insurance/premium/calculate` | `proposal:create` or `product:read` |
| POST | `/insurance/reference/sync` | `product:manage` |

## Credentials

Set in `.env` (never in Vite):

```
DEFINITE_ASSURANCE_BASE_URL=https://uat.definiteassurance.com/api/v1
DEFINITE_ASSURANCE_USERNAME=...
DEFINITE_ASSURANCE_PASSWORD=...
```

Without credentials, check endpoints return `provider: null` via Null provider; mutations that require the provider return `INSURANCE_PROVIDER_UNAVAILABLE`.

## Local DB fix (this environment)

Docker was unavailable; Homebrew Postgres/Redis used instead:

```bash
./scripts/setup_local_db.sh
cd backend && alembic upgrade head
python scripts/seed_phase1.py && python scripts/seed_phase2.py
```
