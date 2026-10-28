#!/usr/bin/env bash
# Create/update Render production API + point dashboard nginx at it.
#
# Without GCP (local build + Docker Hub / GHCR):
#   ./scripts/render/build-api-local.sh && ./scripts/render/migrate-local.sh
#   DOCKER_IMAGE=docker.io/YOU/starserve-api:latest ./scripts/render/publish-api-image.sh
#   export RENDER_API_KEY=rnd_...
#   RENDER_API_IMAGE=docker.io/YOU/starserve-api:latest ./scripts/render/apply-production.sh
#
# Or Git build on Render:
#   RENDER_API_REPO=https://github.com/YOU/StarServe ./scripts/render/apply-production.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

require_render_api_url
[ -f "${ENV_FILE}" ] || render_die "Missing ${ENV_FILE}"

API_SERVICE_ID="$("${SCRIPT_DIR}/create-api-service.sh")"

export API_SERVICE_ID ENV_FILE RENDER_API_BASE_URL RENDER_API_HOST RENDER_API_KEY
python3 <<'PY'
import json, os, subprocess, sys, urllib.error, urllib.request
from pathlib import Path

service_id = os.environ["API_SERVICE_ID"]
env_file = Path(os.environ["ENV_FILE"])
callback = os.environ["RENDER_API_BASE_URL"]
token = os.environ["RENDER_API_KEY"]

def read_env(key: str) -> str:
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, val = raw.split("=", 1)
        if name != key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        return val
    return ""

cors = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "https://quote.starserveinsuranceagency.com,"
    "https://www.starserveinsuranceagency.com,"
    "https://starserveinsuranceagency.com,"
    "https://starserve-dashboard.onrender.com,"
    "https://starserve-dashboard-staging-233389149626.europe-west1.run.app,"
    "https://starserve-api-233389149626.europe-west1.run.app,"
    "https://starserve-api-staging-233389149626.europe-west1.run.app"
)

plain = {
    "APP_ENV": "production",
    "APP_DEBUG": "false",
    "ALLOW_INSECURE_PRODUCTION": "false",
    "COOKIE_SECURE": "true",
    "COOKIE_SAMESITE": "none",
    "TRUST_X_FORWARDED_FOR": "true",
    "TRUSTED_PROXY_HOPS": "2",
    "STORAGE_BACKEND": "gcs",
    "GCS_BUCKET": "star_serve",
    "GCS_PREFIX": "production",
    "DB_PROVIDER": "supabase",
    "SUPABASE_PROJECT_REF": "wbasegyvtchdmkfkyoei",
    "SUPABASE_URL": "https://wbasegyvtchdmkfkyoei.supabase.co",
    "DB_SSL_MODE": "require",
    "DB_NULL_POOL": "true",
    "DB_POOL_SIZE": "2",
    "DB_MAX_OVERFLOW": "0",
    "LOG_JSON": "true",
    "JWT_ALGORITHM": "RS256",
    "BIRDVIEW_LIVE": "true",
    "GUEST_QUOTE_ENABLED": "true",
    "CORS_ORIGINS": cors,
    "EMAIL_APP_URL": "https://quote.starserveinsuranceagency.com/dashboard",
    "DEFINITE_ASSURANCE_BASE_URL": read_env("DEFINITE_ASSURANCE_BASE_URL")
    or "https://digitalapi.definiteassurance.com/api/app/v1",
    "DEFINITE_ASSURANCE_ENFORCE_DOUBLE_INSURANCE": read_env(
        "DEFINITE_ASSURANCE_ENFORCE_DOUBLE_INSURANCE"
    )
    or "false",
    "DEFINITE_ASSURANCE_TIMEOUT_SECONDS": read_env("DEFINITE_ASSURANCE_TIMEOUT_SECONDS")
    or "60",
    "BIRDVIEW_STK_URL": read_env("BIRDVIEW_STK_URL")
    or "https://payments.birdviewinsurance.com/mobile-payments/stk-push",
    "BIRDVIEW_STK_FALLBACK_URL": read_env("BIRDVIEW_STK_FALLBACK_URL")
    or "https://payments-ewrv.onrender.com/mobile-payments/stk-push",
    "EMAIL_PROVIDER": read_env("EMAIL_PROVIDER") or "gmail",
    "EMAIL_FROM_NAME": read_env("EMAIL_FROM_NAME") or "Star Serve",
    "EMAIL_FROM_ADDRESS": read_env("EMAIL_FROM_ADDRESS"),
    "EMAIL_SUPPORT_ADDRESS": read_env("EMAIL_SUPPORT_ADDRESS"),
    "EMAIL_SMTP_HOST": read_env("EMAIL_SMTP_HOST") or "smtp.gmail.com",
    "EMAIL_SMTP_PORT": read_env("EMAIL_SMTP_PORT") or "587",
    "EMAIL_SMTP_USE_TLS": "true",
    "BIRDVIEW_CALLBACK_BASE_URL": callback,
    "MPESA_CALLBACK_BASE_URL": callback,
    "SMS_API_URL": read_env("SMS_API_URL")
    or "https://sms.textsms.co.ke/api/services/sendsms/",
    "SMS_SENDER_ID": read_env("SMS_SENDER_ID") or "STARSERVE",
    "GOOGLE_APPLICATION_CREDENTIALS": "/etc/secrets/gcs-sa.json",
}

secret_keys = [
    "DATABASE_URL",
    "JWT_PRIVATE_KEY",
    "JWT_PUBLIC_KEY",
    "ENCRYPTION_KEY",
    "CSRF_SECRET",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DEFINITE_ASSURANCE_USERNAME",
    "DEFINITE_ASSURANCE_PASSWORD",
    "DEFINITE_ASSURANCE_AGENT_CODE",
    "BIRDVIEW_API_KEY",
    "BIRDVIEW_WEBHOOK_SECRET",
    "EMAIL_SMTP_USERNAME",
    "EMAIL_SMTP_PASSWORD",
    "EMAIL_API_KEY",
    "SMS_API_KEY",
    "SMS_PARTNER_ID",
    "MPESA_CONSUMER_KEY",
    "MPESA_CONSUMER_SECRET",
    "MPESA_SHORTCODE",
    "MPESA_PASSKEY",
    "MPESA_WEBHOOK_SECRET",
    "GUEST_TENANT_ID",
    "GUEST_SIGNING_SECRET",
]
secrets = {k: read_env(k) for k in secret_keys if read_env(k)}

def put_env(key: str, value: str) -> None:
    body = json.dumps({"value": value}).encode()
    req = urllib.request.Request(
        f"https://api.render.com/v1/services/{service_id}/env-vars/{key}",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        resp.read()

for key, value in plain.items():
    if not value:
        continue
    put_env(key, value)
    print(f"[render]   set {key}", flush=True)
for key in sorted(secrets):
    put_env(key, secrets[key])
    print(f"[render]   secret {key}", flush=True)
PY

render_log "Waiting for ${RENDER_API_BASE_URL}/health"
for _ in $(seq 1 60); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' "${RENDER_API_BASE_URL}/health" 2>/dev/null || echo 000)"
  if [ "${code}" = "200" ]; then
    render_log "API healthy"
    break
  fi
  sleep 10
done
code="$(curl -sS -o /dev/null -w '%{http_code}' "${RENDER_API_BASE_URL}/health" 2>/dev/null || echo 000)"
[ "${code}" = "200" ] || render_die "API not healthy (HTTP ${code}). Fix GAR image/billing and redeploy before cutover."

render_log "Pointing starserve-dashboard API_UPSTREAM → ${RENDER_API_HOST}"
render_curl -X PUT "https://api.render.com/v1/services/${RENDER_DASHBOARD_SERVICE_ID}/env-vars/API_UPSTREAM" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json; print(json.dumps({'value': '${RENDER_API_HOST}'}))")" >/dev/null

render_log "Cutover complete — verify quote.starserveinsuranceagency.com/dashboard/"
