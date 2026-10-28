# StarServe USSD Platform

## Architecture summary

USSD is an **additional channel** on the existing StarServe backend. It does not create a second insurance system.

| Concern | Reuse |
| --- | --- |
| Motor quotation / premium | `GuestService` → insurer provider (`calculate_premium`, catalog, returning client lookup) |
| Report claim | `GuestClaimService.file` |
| Follow up claim | `GuestClaimService.lookup` (claim number + ID + phone) |
| Identity / tenant | Guest tenant resolution + RLS |
| Notifications | Existing claim / payment notification paths when business services fire them |

Module: `app/modules/ussd/`

## Callback URL

After deployment, share with the aggregator:

`https://<your-api-host>/api/v1/ussd/callback`

Local health check: `GET /api/v1/ussd/health`

## Navigation rules

| Input | Behaviour |
| --- | --- |
| `0` | Previous step (at main menu: redisplay main menu) |
| `00` | Main menu; clears workflow answers except MSISDN |
| `1`…`n` | Menu selection when on a MENU screen |
| `99` | Repeat current message when configured |
| Phone / ID entry starting with `0` | **Not** treated as back |

Sessions pin to a **published configuration version** so live edits do not corrupt in-flight journeys.

## Provider adapter

Implemented adapters:

- `SIMULATOR` — dashboard JSON simulator (`is_test=true`)
- `GENERIC_FORM` / `AFRICAS_TALKING` — form or JSON fields `sessionId`, `phoneNumber`, `text`, `serviceCode`; responses `CON …` / `END …`

**Production provider onboarding is still pending.** Do not invent protocol SLAs. Configure `auth_secret` and optional IP allowlist in Admin → USSD → Provider.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `USSD_ENABLED` | Master switch (default true) |
| `USSD_ALLOW_UNAUTHENTICATED` | Dev only when no provider secret |
| `USSD_HASH_PEPPER` | Pepper for MSISDN hashing in analytics |
| `USSD_DEFAULT_SERVICE_CODE` | Default dial code (default `*652*6#`) |
| `GUEST_TENANT_ID` | Agency tenant used when no provider row maps the service code |

## Dashboard

Route: `/app/ussd`

Permissions: `ussd:read`, `ussd:manage`, `ussd:analytics`

Sections: Overview, Menu builder, Simulator, Analytics, Sessions, Provider, Audit.

## Migration

`alembic upgrade head` applies `0042_ussd_platform`.

Rollback: `alembic downgrade 0041_sales_agent_logins` (drops USSD tables and seeded permissions).

## Metric definitions

See `app/modules/ussd/analytics.py` and the analytics API payload `metric_definitions`.

- **Session completion rate** — completed / (completed + abandoned/timed_out/terminated) × 100; period by `session.created_at`.
- **Unique access count** — distinct `msisdn_hash` values (pseudonymized), not verified people.
- **Test sessions** — `is_test=true` from the simulator; excluded from production metrics unless `include_test=true`.

## Residual risks

1. Real aggregator protocol (auth, retries, character limits) must be confirmed at onboarding.
2. Motor USSD currently supports **returning clients + quotation display**; full new-business issuance still completes on the website when Definite requires email/chassis/KYC documents.
3. Provider secret storage should move to the app encryption helper before production.
4. Load test evidence is not yet available — do not claim a specific TPS rating.
