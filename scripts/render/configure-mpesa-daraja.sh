#!/usr/bin/env bash
# Write Safaricom Daraja credentials into v1.0/.env (gitignored) and sync to Render.
#
#   export RENDER_API_KEY=rnd_...
#   export MPESA_CONSUMER_KEY=...
#   export MPESA_CONSUMER_SECRET=...
#   export MPESA_PASSKEY=...
#   export MPESA_SHORTCODE=1378790   # optional; defaults to Star Serve paybill
#   ./scripts/render/configure-mpesa-daraja.sh
#
# Never commit .env or paste keys into chat.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT}/.env"

upsert() {
  local key="$1"
  local val="$2"
  if [ ! -f "${ENV_FILE}" ]; then
    touch "${ENV_FILE}"
  fi
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    python3 - "${key}" "${val}" "${ENV_FILE}" <<'PY'
import sys
from pathlib import Path
key, val, path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
lines = path.read_text().splitlines()
out = []
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={val}")
    else:
        out.append(line)
path.write_text("\n".join(out) + "\n")
PY
  else
    printf '%s=%s\n' "${key}" "${val}" >> "${ENV_FILE}"
  fi
}

require() {
  if [ -z "${!1:-}" ]; then
    echo "Missing ${1}. Export it before running this script." >&2
    exit 1
  fi
}

require MPESA_CONSUMER_KEY
require MPESA_CONSUMER_SECRET
require MPESA_PASSKEY

SHORT="${MPESA_SHORTCODE:-1378790}"
upsert MPESA_CONSUMER_KEY "${MPESA_CONSUMER_KEY}"
upsert MPESA_CONSUMER_SECRET "${MPESA_CONSUMER_SECRET}"
upsert MPESA_PASSKEY "${MPESA_PASSKEY}"
upsert MPESA_SHORTCODE "${SHORT}"
upsert MPESA_LIVE "true"
upsert MPESA_DARAJA_BASE_URL "${MPESA_DARAJA_BASE_URL:-https://api.safaricom.co.ke}"
upsert BIRDVIEW_LIVE "false"

echo "[mpesa] Updated ${ENV_FILE} (Daraja shortcode ${SHORT})."

if [ -n "${RENDER_API_KEY:-}" ]; then
  "${ROOT}/scripts/render/sync-api-after-create.sh"
else
  echo "[mpesa] Set RENDER_API_KEY and re-run sync-api-after-create.sh to push secrets to Render."
fi

CALLBACK="${MPESA_CALLBACK_BASE_URL:-https://quote.starserveinsuranceagency.com}"
echo "[mpesa] Register Daraja STK callback URL with Safaricom:"
echo "  ${CALLBACK}/api/v1/webhooks/payments/mpesa"
