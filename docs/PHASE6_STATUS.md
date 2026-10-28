# Phase 6 — Notifications (SMS / Email / WhatsApp)

## Completed

- `NotificationService.send(channel, template, recipient, context)` → job + delivery record
- Provider ports: SMS, Email, WhatsApp stubs (no vendor SDK in business code)
- Built-in templates: `GENERIC_ALERT`, `PAYMENT_RECEIVED`, `POLICY_ACTIVATED`, `CERTIFICATE_READY`, `PROPOSAL_APPROVED`
- States: `QUEUED` → `SENDING` → `SENT` | `FAILED` | `CANCELLED`
- Bounded retries with backoff (`max_attempts=3`); never invent delivery success
- Idempotency-Key on send
- Payment SUCCESS enqueues best-effort SMS/email to the customer (failures do not reverse payment)
- RLS on `notifications`
- Frontend Notifications page (send + delivery log + retry)
- Migration `0005_phase6_notifications`

## APIs

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/notifications/templates` | `notification:read` |
| GET | `/api/v1/notifications` | `notification:read` |
| GET | `/api/v1/notifications/{id}` | `notification:read` |
| POST | `/api/v1/notifications` | `notification:send` (+ Idempotency-Key) |
| POST | `/api/v1/notifications/{id}/retry` | `notification:send` |
| POST | `/api/v1/notifications/{id}/cancel` | `notification:send` |

## Apply migration & permissions

```bash
cd backend
alembic upgrade head
python scripts/seed_phase6.py
```

## Env (optional live credentials later)

```text
SMS_API_KEY=
EMAIL_API_KEY=
EMAIL_FROM_ADDRESS=noreply@starserve.local
WHATSAPP_API_TOKEN=
```

Leave blank for local stubs (`mode=STUB` in provider payload).

## Next

Phase 7: Reports, platform/tenant admin, dedicated DB — **done**. See [PHASE7_STATUS.md](PHASE7_STATUS.md).

Post-v1.0: ARQ workers, object storage exports, full dedicated `get_db` routing.
