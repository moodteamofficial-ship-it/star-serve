# Phase 5 — Payments, Wallet & Certificates

## Completed

- Payment intents with **server-side amount** from `policy.gross_premium` (client amounts rejected)
- State machine: `INITIATED` → `PENDING` → `SUCCESS` | `FAILED` | `REVERSED` | `CANCELLED`
- Providers behind `PaymentProvider`: M-Pesa stub + wallet debit
- M-Pesa webhook: HMAC signature, optional timestamp window, amount match, idempotent replay
- On SUCCESS: activate policy → generate certificate via insurance provider
- Tenant wallet ledger (credit/debit) with unique transaction references
- Certificates module with provider `generate_certificate`
- Idempotency-Key on payment initiate
- RLS on `payments`, `wallets`, `wallet_transactions`, `certificates`
- Frontend Payments page (initiate + wallet top-up)
- Migration `0004_phase5_payments`

## APIs

| Method | Path | Permission |
|--------|------|------------|
| POST | `/api/v1/payments` | `payment:create` (+ Idempotency-Key) |
| GET | `/api/v1/payments` | `payment:read` |
| GET | `/api/v1/payments/{id}` | `payment:read` |
| POST | `/api/v1/webhooks/payments/mpesa` | signed webhook (no session) |
| GET | `/api/v1/wallets/me` | `wallet:read` |
| GET | `/api/v1/wallets/me/transactions` | `wallet:read` |
| POST | `/api/v1/wallets/me/top-up` | `wallet:topup` |
| GET | `/api/v1/certificates` | `certificate:read` |
| GET | `/api/v1/certificates/{id}` | `certificate:read` |
| POST | `/api/v1/certificates/policies/{id}/generate` | `certificate:generate` |

## Apply migration & permissions

```bash
cd backend
alembic upgrade head
python scripts/seed_phase5.py
```

## Local M-Pesa webhook stub

Sign with `MPESA_WEBHOOK_SECRET` (or CSRF secret fallback):

```text
HMAC-SHA256(secret, CheckoutRequestID + Amount + ResultCode)
```

Header: `X-StarServe-Signature`

## Next

Phase 6: Notifications — **done**. See [PHASE6_STATUS.md](PHASE6_STATUS.md).

Phase 7: Reports, platform/tenant admin, dedicated DB path.
