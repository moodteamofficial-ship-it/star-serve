#!/usr/bin/env bash
# Print non-secret env vars for the Render production API service.
# Secrets must be copied from Secret Manager / local .env in the Render dashboard.
#
# Usage:
#   RENDER_API_HOST=starserve-api.onrender.com ./scripts/render/print-production-env.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

require_render_api_url

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

CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
CORS_ORIGINS="${CORS_ORIGINS},https://quote.starserveinsuranceagency.com"
CORS_ORIGINS="${CORS_ORIGINS},https://www.starserveinsuranceagency.com"
CORS_ORIGINS="${CORS_ORIGINS},https://starserveinsuranceagency.com"
CORS_ORIGINS="${CORS_ORIGINS},https://${RENDER_DASHBOARD_HOST}"
CORS_ORIGINS="${CORS_ORIGINS},https://starserve-dashboard-staging-233389149626.europe-west1.run.app"
CORS_ORIGINS="${CORS_ORIGINS},https://starserve-api-233389149626.europe-west1.run.app"
CORS_ORIGINS="${CORS_ORIGINS},https://starserve-api-staging-233389149626.europe-west1.run.app"

EMAIL_APP_URL="https://quote.starserveinsuranceagency.com/dashboard"
CALLBACK_BASE="${RENDER_API_BASE_URL}"

DEFINITE_BASE="$(python_read_env DEFINITE_ASSURANCE_BASE_URL)"
DEFINITE_BASE="${DEFINITE_BASE:-https://digitalapi.definiteassurance.com/api/app/v1}"
DEFINITE_ENFORCE="$(python_read_env DEFINITE_ASSURANCE_ENFORCE_DOUBLE_INSURANCE)"
DEFINITE_ENFORCE="${DEFINITE_ENFORCE:-false}"
DEFINITE_TIMEOUT="$(python_read_env DEFINITE_ASSURANCE_TIMEOUT_SECONDS)"
DEFINITE_TIMEOUT="${DEFINITE_TIMEOUT:-60}"
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

cat <<EOF
# Paste into Render → starserve-api → Environment (non-secret keys).
# Match Secret Manager starserve-prod-* / scripts/gcp/sync-secrets.sh for secrets.

APP_ENV=production
APP_DEBUG=false
ALLOW_INSECURE_PRODUCTION=false
COOKIE_SECURE=true
COOKIE_SAMESITE=none
TRUST_X_FORWARDED_FOR=true
TRUSTED_PROXY_HOPS=2
STORAGE_BACKEND=gcs
GCS_BUCKET=star_serve
GCS_PREFIX=production
DB_PROVIDER=supabase
SUPABASE_PROJECT_REF=wbasegyvtchdmkfkyoei
SUPABASE_URL=https://wbasegyvtchdmkfkyoei.supabase.co
DB_SSL_MODE=require
DB_NULL_POOL=true
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=0
LOG_JSON=true
JWT_ALGORITHM=RS256
BIRDVIEW_LIVE=true
GUEST_QUOTE_ENABLED=true
CORS_ORIGINS=${CORS_ORIGINS}
EMAIL_APP_URL=${EMAIL_APP_URL}
DEFINITE_ASSURANCE_BASE_URL=${DEFINITE_BASE}
DEFINITE_ASSURANCE_ENFORCE_DOUBLE_INSURANCE=${DEFINITE_ENFORCE}
DEFINITE_ASSURANCE_TIMEOUT_SECONDS=${DEFINITE_TIMEOUT}
BIRDVIEW_STK_URL=${BIRDVIEW_STK_URL}
BIRDVIEW_STK_FALLBACK_URL=${BIRDVIEW_STK_FALLBACK}
EMAIL_PROVIDER=${EMAIL_PROVIDER}
EMAIL_FROM_NAME=${EMAIL_FROM_NAME}
EMAIL_FROM_ADDRESS=${EMAIL_FROM_ADDRESS}
EMAIL_SUPPORT_ADDRESS=${EMAIL_SUPPORT_ADDRESS}
EMAIL_SMTP_HOST=${EMAIL_SMTP_HOST}
EMAIL_SMTP_PORT=${EMAIL_SMTP_PORT}
EMAIL_SMTP_USE_TLS=true
BIRDVIEW_CALLBACK_BASE_URL=${CALLBACK_BASE}
MPESA_CALLBACK_BASE_URL=${CALLBACK_BASE}
SMS_API_URL=${SMS_API_URL}
SMS_SENDER_ID=${SMS_SENDER_ID}

# Secret env vars (Render → Secret type):
# DATABASE_URL, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY, ENCRYPTION_KEY, CSRF_SECRET,
# SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, DEFINITE_ASSURANCE_* (user/pass/agent),
# BIRDVIEW_API_KEY, BIRDVIEW_WEBHOOK_SECRET, EMAIL_SMTP_*, EMAIL_API_KEY,
# SMS_API_KEY, SMS_PARTNER_ID, MPESA_*, GUEST_TENANT_ID, GUEST_SIGNING_SECRET

# GCS from Render (not Cloud Run ADC):
# 1. SA with roles/storage.objectAdmin on gs://star_serve
# 2. Secret file mounted at /etc/secrets/gcs-sa.json
# 3. GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcs-sa.json

EOF

render_log "Callback + webhook base: ${CALLBACK_BASE}"
render_log "After API is live, set dashboard API_UPSTREAM=${RENDER_API_HOST}"
