#!/usr/bin/env bash
# Upload env secrets to Secret Manager without printing values.
# Staging copies from local .env so Cloud Run behaves like current local/dev.
# Production gets isolated JWT / CSRF / guest keys; DATABASE_URL_PRODUCTION if set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

ENV_NAME="${1:-}"
require_env_name "${ENV_NAME}"
PREFIX="$(secret_prefix "${ENV_NAME}")"

[ -f "${ENV_FILE}" ] || die "Missing ${ENV_FILE} (copy from .env.example and fill server-side secrets)"

python_read_env() {
  python3 - "$ENV_FILE" "$1" <<'PY'
import sys
from pathlib import Path
path, key = sys.argv[1], sys.argv[2]
value = ""
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

ensure_secret() {
  local name="$1"
  if gcloud secrets describe "${name}" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    return
  fi
  gcloud secrets create "${name}" \
    --replication-policy=automatic \
    --project="${GCP_PROJECT}" >/dev/null
}

grant_runtime_accessor() {
  local name="$1"
  local sa
  sa="$(runtime_sa "${ENV_NAME}")"
  gcloud secrets add-iam-policy-binding "${name}" \
    --member="serviceAccount:${sa}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${GCP_PROJECT}" \
    --quiet >/dev/null
}

upload_value() {
  local secret_name="$1"
  local value="$2"
  if [ -z "${value}" ]; then
    log "skip ${secret_name} (empty)"
    return 1
  fi
  ensure_secret "${secret_name}"
  printf '%s' "${value}" | gcloud secrets versions add "${secret_name}" \
    --data-file=- \
    --project="${GCP_PROJECT}" >/dev/null
  grant_runtime_accessor "${secret_name}"
  log "uploaded ${secret_name}"
  return 0
}

upload_file() {
  local secret_name="$1"
  local path="$2"
  [ -f "${path}" ] || die "Missing ${path}"
  ensure_secret "${secret_name}"
  gcloud secrets versions add "${secret_name}" \
    --data-file="${path}" \
    --project="${GCP_PROJECT}" >/dev/null
  grant_runtime_accessor "${secret_name}"
  log "uploaded ${secret_name} from file"
}

upload_from_env() {
  local env_key="$1"
  local suffix="$2"
  local value
  value="$(python_read_env "${env_key}")"
  upload_value "${PREFIX}-${suffix}" "${value}" || true
}

log "Syncing ${ENV_NAME} secrets into ${GCP_PROJECT} (values never printed)"

if [ "${ENV_NAME}" = "production" ]; then
  prod_dsn="$(python_read_env DATABASE_URL_PRODUCTION)"
  if [ -z "${prod_dsn}" ]; then
    log "DATABASE_URL_PRODUCTION unset — production will use DATABASE_URL (same DB as staging)."
    log "Create a separate Supabase/Cloud SQL database before putting real customers on live."
    upload_from_env DATABASE_URL database-url
  else
    upload_value "${PREFIX}-database-url" "${prod_dsn}" || true
  fi
else
  upload_from_env DATABASE_URL database-url
fi

enc="$(python_read_env ENCRYPTION_KEY)"
csrf="$(python_read_env CSRF_SECRET)"
if [ "${ENV_NAME}" = "production" ]; then
  if printf '%s' "${enc}" | python3 -c 'import sys; sys.exit(0 if "change-me" in sys.stdin.read().lower() else 1)'; then
    if gcloud secrets describe "${PREFIX}-encryption-key" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
      log "keeping existing ${PREFIX}-encryption-key (local value is still a placeholder)"
      grant_runtime_accessor "${PREFIX}-encryption-key"
      enc=""
    else
      log "Local ENCRYPTION_KEY is a placeholder — generating a production key (dedicated DSNs encrypted with the old key will not decrypt)."
      enc="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    fi
  fi
  if printf '%s' "${csrf}" | python3 -c 'import sys; sys.exit(0 if "change-me" in sys.stdin.read().lower() else 1)'; then
    if gcloud secrets describe "${PREFIX}-csrf-secret" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
      log "keeping existing ${PREFIX}-csrf-secret (local value is still a placeholder)"
      grant_runtime_accessor "${PREFIX}-csrf-secret"
      csrf=""
    else
      log "Local CSRF_SECRET is a placeholder — generating a production CSRF secret."
      csrf="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    fi
  fi
fi
upload_value "${PREFIX}-encryption-key" "${enc}" || true
upload_value "${PREFIX}-csrf-secret" "${csrf}" || true
upload_from_env SUPABASE_ANON_KEY supabase-anon-key
upload_from_env SUPABASE_SERVICE_ROLE_KEY supabase-service-role-key
upload_from_env DEFINITE_ASSURANCE_USERNAME definite-username
upload_from_env DEFINITE_ASSURANCE_PASSWORD definite-password
upload_from_env DEFINITE_ASSURANCE_AGENT_CODE definite-agent-code
upload_from_env BIRDVIEW_API_KEY birdview-api-key
upload_from_env BIRDVIEW_WEBHOOK_SECRET birdview-webhook-secret
upload_from_env EMAIL_SMTP_USERNAME email-smtp-username
upload_from_env EMAIL_SMTP_PASSWORD email-smtp-password
upload_from_env EMAIL_API_KEY email-api-key
upload_from_env SMS_API_KEY sms-api-key
upload_from_env SMS_PARTNER_ID sms-partner-id
upload_from_env MPESA_CONSUMER_KEY mpesa-consumer-key
upload_from_env MPESA_CONSUMER_SECRET mpesa-consumer-secret
upload_from_env MPESA_SHORTCODE mpesa-shortcode
upload_from_env MPESA_PASSKEY mpesa-passkey
upload_from_env MPESA_WEBHOOK_SECRET mpesa-webhook-secret
upload_from_env GUEST_TENANT_ID guest-tenant-id
upload_from_env GUEST_SIGNING_SECRET guest-signing-secret

JWT_PRIVATE="${BACKEND_DIR}/secrets/dev_jwt_private.pem"
JWT_PUBLIC="${BACKEND_DIR}/secrets/dev_jwt_public.pem"

if [ "${ENV_NAME}" = "production" ]; then
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' EXIT
  # Isolated production signing keys — tokens cannot be reused from staging/local.
  if ! gcloud secrets describe "${PREFIX}-jwt-private" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    openssl genrsa -out "${tmpdir}/jwt_private.pem" 2048 >/dev/null 2>&1
    openssl rsa -in "${tmpdir}/jwt_private.pem" -pubout -out "${tmpdir}/jwt_public.pem" >/dev/null 2>&1
    upload_file "${PREFIX}-jwt-private" "${tmpdir}/jwt_private.pem"
    upload_file "${PREFIX}-jwt-public" "${tmpdir}/jwt_public.pem"
  else
    log "keeping existing ${PREFIX}-jwt-private / jwt-public"
    grant_runtime_accessor "${PREFIX}-jwt-private"
    grant_runtime_accessor "${PREFIX}-jwt-public"
  fi
  if ! gcloud secrets describe "${PREFIX}-guest-signing-secret" --project="${GCP_PROJECT}" >/dev/null 2>&1 \
    || [ -z "$(python_read_env GUEST_SIGNING_SECRET)" ]; then
    generated="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    upload_value "${PREFIX}-guest-signing-secret" "${generated}" || true
  fi
  if [ -z "$(python_read_env GUEST_TENANT_ID)" ]; then
    log "GUEST_TENANT_ID unset — production will boot with GUEST_QUOTE_ENABLED=false until you set it."
  fi
else
  upload_file "${PREFIX}-jwt-private" "${JWT_PRIVATE}"
  upload_file "${PREFIX}-jwt-public" "${JWT_PUBLIC}"
fi

log "Secret sync complete for ${ENV_NAME}"
