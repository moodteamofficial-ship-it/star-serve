#!/usr/bin/env bash
# Deploy (or update) a Cloud Run revision. Secrets stay in Secret Manager.
# Usage: deploy.sh <staging|production|backup> [image]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

ENV_NAME="${1:-}"
require_env_name "${ENV_NAME}"
IMAGE="${2:-$(image_base):${ENV_NAME}}"
SERVICE="$(service_name "${ENV_NAME}")"
SA="$(runtime_sa "${ENV_NAME}")"
PREFIX="$(secret_prefix "${ENV_NAME}")"

python_read_env() {
  python3 - "$ENV_FILE" "$1" <<'PY'
import sys
from pathlib import Path
path, key = sys.argv[1], sys.argv[2]
value = ""
if Path(path).exists():
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, val = raw.split("=", 1)
        if name == key:
            value = val.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
sys.stdout.write(value)
PY
}

secret_exists() {
  gcloud secrets describe "$1" --project="${GCP_PROJECT}" >/dev/null 2>&1
}

SECRETS=()
add_secret_if_present() {
  local env_name="$1"
  local suffix="$2"
  local secret="${PREFIX}-${suffix}"
  if secret_exists "${secret}"; then
    SECRETS+=("${env_name}=${secret}:latest")
  fi
}

add_secret_if_present DATABASE_URL database-url
add_secret_if_present JWT_PRIVATE_KEY jwt-private
add_secret_if_present JWT_PUBLIC_KEY jwt-public
add_secret_if_present ENCRYPTION_KEY encryption-key
add_secret_if_present CSRF_SECRET csrf-secret
add_secret_if_present SUPABASE_ANON_KEY supabase-anon-key
add_secret_if_present SUPABASE_SERVICE_ROLE_KEY supabase-service-role-key
add_secret_if_present DEFINITE_ASSURANCE_USERNAME definite-username
add_secret_if_present DEFINITE_ASSURANCE_PASSWORD definite-password
add_secret_if_present DEFINITE_ASSURANCE_AGENT_CODE definite-agent-code
add_secret_if_present BIRDVIEW_API_KEY birdview-api-key
add_secret_if_present BIRDVIEW_WEBHOOK_SECRET birdview-webhook-secret
add_secret_if_present EMAIL_SMTP_USERNAME email-smtp-username
add_secret_if_present EMAIL_SMTP_PASSWORD email-smtp-password
add_secret_if_present EMAIL_API_KEY email-api-key
add_secret_if_present SMS_API_KEY sms-api-key
add_secret_if_present SMS_PARTNER_ID sms-partner-id
add_secret_if_present MPESA_CONSUMER_KEY mpesa-consumer-key
add_secret_if_present MPESA_CONSUMER_SECRET mpesa-consumer-secret
add_secret_if_present MPESA_SHORTCODE mpesa-shortcode
add_secret_if_present MPESA_PASSKEY mpesa-passkey
add_secret_if_present MPESA_WEBHOOK_SECRET mpesa-webhook-secret
add_secret_if_present GUEST_TENANT_ID guest-tenant-id
add_secret_if_present GUEST_SIGNING_SECRET guest-signing-secret

[ ${#SECRETS[@]} -gt 0 ] || die "No secrets found for ${PREFIX}-*. Run scripts/gcp/sync-secrets.sh ${ENV_NAME}"

APP_ENV="${ENV_NAME}"
MIN_INSTANCES=1
MAX_INSTANCES=10
CONCURRENCY=40
MEMORY=512Mi
BIRDVIEW_LIVE="$(python_read_env BIRDVIEW_LIVE)"
# Cloud Build does not upload .env. Staging must keep live 1 KES STK prompts.
if [ "${ENV_NAME}" = "production" ]; then
  BIRDVIEW_LIVE=false
else
  BIRDVIEW_LIVE="${BIRDVIEW_LIVE:-true}"
fi
GUEST_QUOTE_ENABLED=true
CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
EMAIL_APP_URL="$(python_read_env EMAIL_APP_URL)"
EMAIL_APP_URL="${EMAIL_APP_URL:-http://localhost:5173}"

# Prefer the deployed SPA origin for CORS + email deep-links when present.
WEB_SERVICE="$(web_service_name "${ENV_NAME}")"
WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --format='value(status.url)' 2>/dev/null || true)"
PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT}" --format='value(projectNumber)' 2>/dev/null || true)"
if [ -n "${WEB_URL}" ]; then
  CORS_ORIGINS="${CORS_ORIGINS},${WEB_URL}"
  EMAIL_APP_URL="${WEB_URL}"
fi
if [ -n "${PROJECT_NUMBER}" ]; then
  ALT_WEB_URL="https://${WEB_SERVICE}-${PROJECT_NUMBER}.${GCP_REGION}.run.app"
  CORS_ORIGINS="${CORS_ORIGINS},${ALT_WEB_URL}"
  # Stable form for email CTA buttons (Open claim / Open Star Serve).
  EMAIL_APP_URL="${ALT_WEB_URL}"
fi
if [ -n "${FRONTEND_URL:-}" ]; then
  CORS_ORIGINS="${CORS_ORIGINS},${FRONTEND_URL}"
  EMAIL_APP_URL="${FRONTEND_URL}"
fi

# Render custom domain (SPA at /dashboard on quote.*). Keep prior origins for rollback.
if [ "${ENV_NAME}" = "production" ]; then
  CORS_ORIGINS="${CORS_ORIGINS},https://quote.starserveinsuranceagency.com,https://www.starserveinsuranceagency.com,https://starserveinsuranceagency.com,https://starserve-dashboard.onrender.com"
  EMAIL_APP_URL="https://quote.starserveinsuranceagency.com/dashboard"
fi

if [ "${ENV_NAME}" = "production" ]; then
  MIN_INSTANCES=1
  MAX_INSTANCES=20
  CONCURRENCY=80
  MEMORY=512Mi
  # Production charges real premium and sends live BirdView STK (callback HMAC + receipt).
  BIRDVIEW_LIVE=true
  # Guest quotes use ensure_default_guest_agency when GUEST_TENANT_ID is unset.
  GUEST_QUOTE_ENABLED=true
fi

# Cloud Build does not upload .env. Non-secret Definite/BirdView defaults must
# match current ops (LIVE Definite API). Secrets still come from Secret Manager.
DEFINITE_BASE="$(python_read_env DEFINITE_ASSURANCE_BASE_URL)"
DEFINITE_BASE="${DEFINITE_BASE:-https://digitalapi.definiteassurance.com/api/app/v1}"
DEFINITE_TEST_AMOUNT="$(python_read_env DEFINITE_ASSURANCE_TEST_AMOUNT_PAID)"
DEFINITE_TEST_AMOUNT="${DEFINITE_TEST_AMOUNT:-1}"
DEFINITE_ENFORCE="$(python_read_env DEFINITE_ASSURANCE_ENFORCE_DOUBLE_INSURANCE)"
DEFINITE_ENFORCE="${DEFINITE_ENFORCE:-false}"
DEFINITE_TIMEOUT="$(python_read_env DEFINITE_ASSURANCE_TIMEOUT_SECONDS)"
DEFINITE_TIMEOUT="${DEFINITE_TIMEOUT:-60}"
BIRDVIEW_TEST_AMOUNT="$(python_read_env BIRDVIEW_TEST_AMOUNT)"
BIRDVIEW_TEST_AMOUNT="${BIRDVIEW_TEST_AMOUNT:-1}"
BIRDVIEW_STK_URL="$(python_read_env BIRDVIEW_STK_URL)"
BIRDVIEW_STK_URL="${BIRDVIEW_STK_URL:-https://payments.birdviewinsurance.com/mobile-payments/stk-push}"
BIRDVIEW_STK_FALLBACK="$(python_read_env BIRDVIEW_STK_FALLBACK_URL)"
BIRDVIEW_STK_FALLBACK="${BIRDVIEW_STK_FALLBACK:-https://payments-ewrv.onrender.com/mobile-payments/stk-push}"
EMAIL_PROVIDER="$(python_read_env EMAIL_PROVIDER)"
EMAIL_PROVIDER="${EMAIL_PROVIDER:-gmail}"
EMAIL_FROM_NAME="$(python_read_env EMAIL_FROM_NAME)"
EMAIL_FROM_NAME="${EMAIL_FROM_NAME:-Star Serve}"
EMAIL_FROM_ADDRESS="$(python_read_env EMAIL_FROM_ADDRESS)"
EMAIL_SUPPORT_ADDRESS="$(python_read_env EMAIL_SUPPORT_ADDRESS)"
EMAIL_SMTP_HOST="$(python_read_env EMAIL_SMTP_HOST)"
EMAIL_SMTP_HOST="${EMAIL_SMTP_HOST:-smtp.gmail.com}"
EMAIL_SMTP_PORT="$(python_read_env EMAIL_SMTP_PORT)"
EMAIL_SMTP_PORT="${EMAIL_SMTP_PORT:-587}"
SMS_API_URL="$(python_read_env SMS_API_URL)"
SMS_API_URL="${SMS_API_URL:-https://sms.textsms.co.ke/api/services/sendsms/}"
SMS_SENDER_ID="$(python_read_env SMS_SENDER_ID)"
SMS_SENDER_ID="${SMS_SENDER_ID:-STARSERVE}"

if [ "${ENV_NAME}" = "production" ]; then
  # Never leave UAT 1 KES overrides on the live API.
  BIRDVIEW_TEST_AMOUNT=""
  DEFINITE_TEST_AMOUNT=""
fi

# Keep HTTPS callback bases on the revision at boot (live BirdView asserts this).
EXISTING_API_URL="$(gcloud run services describe "${SERVICE}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --format='value(status.url)' 2>/dev/null || true)"
CALLBACK_BASE="${EXISTING_API_URL}"
if [ -z "${CALLBACK_BASE}" ] && [ -n "${PROJECT_NUMBER}" ]; then
  CALLBACK_BASE="https://${SERVICE}-${PROJECT_NUMBER}.${GCP_REGION}.run.app"
fi

ENV_FILE_YAML="$(mktemp)"
trap 'rm -f "${ENV_FILE_YAML}"' EXIT
python3 - "${ENV_FILE_YAML}" "${APP_ENV}" "${BIRDVIEW_LIVE}" "${GUEST_QUOTE_ENABLED}" \
  "${CORS_ORIGINS}" "${EMAIL_APP_URL}" "${DEFINITE_BASE}" "${DEFINITE_TEST_AMOUNT}" \
  "${DEFINITE_ENFORCE}" "${DEFINITE_TIMEOUT}" "${BIRDVIEW_TEST_AMOUNT}" "${BIRDVIEW_STK_URL}" \
  "${BIRDVIEW_STK_FALLBACK}" "${EMAIL_PROVIDER}" "${EMAIL_FROM_NAME}" \
  "${EMAIL_FROM_ADDRESS}" "${EMAIL_SUPPORT_ADDRESS}" "${EMAIL_SMTP_HOST}" \
  "${EMAIL_SMTP_PORT}" "${CALLBACK_BASE}" "${SMS_API_URL}" "${SMS_SENDER_ID}" <<'PY'
import sys
from pathlib import Path

# YAML (not CSV) so CORS origins and display names can contain commas/spaces.
pairs = [
    ("APP_ENV", sys.argv[2]),
    ("APP_DEBUG", "false"),
    ("ALLOW_INSECURE_PRODUCTION", "false"),
    ("COOKIE_SECURE", "true"),
    ("COOKIE_SAMESITE", "none"),
    ("TRUST_X_FORWARDED_FOR", "true"),
    # SPA nginx → API adds one platform hop beyond Cloud Run's GFE.
    ("TRUSTED_PROXY_HOPS", "2"),
    ("STORAGE_BACKEND", "gcs"),
    ("GCS_BUCKET", "star_serve"),
    ("GCS_PREFIX", sys.argv[2]),  # staging | production | backup
    ("DB_PROVIDER", "supabase"),
    ("SUPABASE_PROJECT_REF", "wbasegyvtchdmkfkyoei"),
    ("SUPABASE_URL", "https://wbasegyvtchdmkfkyoei.supabase.co"),
    ("DB_SSL_MODE", "require"),
    ("DB_NULL_POOL", "true"),
    ("DB_POOL_SIZE", "2"),
    ("DB_MAX_OVERFLOW", "0"),
    ("LOG_JSON", "true"),
    ("JWT_ALGORITHM", "RS256"),
    ("BIRDVIEW_LIVE", sys.argv[3]),
    ("GUEST_QUOTE_ENABLED", sys.argv[4]),
    ("CORS_ORIGINS", sys.argv[5]),
    ("EMAIL_APP_URL", sys.argv[6]),
    ("DEFINITE_ASSURANCE_BASE_URL", sys.argv[7]),
    ("DEFINITE_ASSURANCE_TEST_AMOUNT_PAID", sys.argv[8]),
    ("DEFINITE_ASSURANCE_ENFORCE_DOUBLE_INSURANCE", sys.argv[9]),
    ("DEFINITE_ASSURANCE_TIMEOUT_SECONDS", sys.argv[10]),
    ("BIRDVIEW_TEST_AMOUNT", sys.argv[11]),
    ("BIRDVIEW_STK_URL", sys.argv[12]),
    ("BIRDVIEW_STK_FALLBACK_URL", sys.argv[13]),
    ("EMAIL_PROVIDER", sys.argv[14]),
    ("EMAIL_FROM_NAME", sys.argv[15]),
    ("EMAIL_FROM_ADDRESS", sys.argv[16]),
    ("EMAIL_SUPPORT_ADDRESS", sys.argv[17]),
    ("EMAIL_SMTP_HOST", sys.argv[18]),
    ("EMAIL_SMTP_PORT", sys.argv[19]),
    ("EMAIL_SMTP_USE_TLS", "true"),
    ("BIRDVIEW_CALLBACK_BASE_URL", sys.argv[20]),
    ("MPESA_CALLBACK_BASE_URL", sys.argv[20]),
    ("SMS_API_URL", sys.argv[21]),
    ("SMS_SENDER_ID", sys.argv[22]),
]
lines = []
for key, value in pairs:
    if not value:
        continue
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'{key}: "{escaped}"')
Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

SECRET_CSV="$(IFS=,; echo "${SECRETS[*]}")"

log "Deploying ${SERVICE} (${ENV_NAME}) image=${IMAGE}"

gcloud run deploy "${SERVICE}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --image="${IMAGE}" \
  --service-account="${SA}" \
  --port=8000 \
  --cpu=1 \
  --memory="${MEMORY}" \
  --concurrency="${CONCURRENCY}" \
  --min-instances="${MIN_INSTANCES}" \
  --max-instances="${MAX_INSTANCES}" \
  --timeout=180 \
  --cpu-boost \
  --no-cpu-throttling \
  --execution-environment=gen2 \
  --allow-unauthenticated \
  --ingress=all \
  --env-vars-file="${ENV_FILE_YAML}" \
  --set-secrets="${SECRET_CSV}" \
  --quiet

URL="$(gcloud run services describe "${SERVICE}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --format='value(status.url)')"

# Prefer the stable project-number host for provider callbacks (hash URLs can rotate).
CALLBACK_BASE="${URL}"
if [ -n "${PROJECT_NUMBER}" ]; then
  CALLBACK_BASE="https://${SERVICE}-${PROJECT_NUMBER}.${GCP_REGION}.run.app"
fi

log "Updating callback bases to ${CALLBACK_BASE}"
gcloud run services update "${SERVICE}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --update-env-vars="BIRDVIEW_CALLBACK_BASE_URL=${CALLBACK_BASE},MPESA_CALLBACK_BASE_URL=${CALLBACK_BASE}" \
  --quiet

log "${ENV_NAME} URL: ${URL}"
log "Health: ${URL}/health"
if [ "${ENV_NAME}" = "production" ]; then
  # Drop any leftover UAT test-amount env from earlier revisions.
  gcloud run services update "${SERVICE}" \
    --project="${GCP_PROJECT}" \
    --region="${GCP_REGION}" \
    --remove-env-vars=BIRDVIEW_TEST_AMOUNT,DEFINITE_ASSURANCE_TEST_AMOUNT_PAID \
    --quiet || true
fi
if [ "${ENV_NAME}" != "production" ]; then
  log "Docs:   ${URL}/docs"
fi

python3 - "${ROOT_DIR}/frontend/.env.cloud" "${ENV_NAME}" "${URL}" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
env_name = sys.argv[2]
url = sys.argv[3].rstrip("/") + "/api/v1"
existing = {}
if path.exists():
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            existing[k] = v
existing.setdefault("VITE_APP_NAME", "Star Serve")
existing.setdefault("VITE_DEFAULT_API_ENV", "development")
existing.setdefault("VITE_API_URL_DEVELOPMENT", "http://localhost:8000/api/v1")
key = {
    "staging": "VITE_API_URL_STAGING",
    "production": "VITE_API_URL_PRODUCTION",
    "backup": "VITE_API_URL_BACKUP",
}[env_name]
existing[key] = url
path.write_text(
    "# Generated by scripts/gcp/deploy.sh — public API URLs only, never secrets.\n"
    + "\n".join(f"{k}={existing[k]}" for k in sorted(existing))
    + "\n",
    encoding="utf-8",
)
print(f"[gcp] wrote {path} ({key})")
PY
