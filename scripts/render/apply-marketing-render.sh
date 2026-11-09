#!/usr/bin/env bash
# Wire starserve-marketing → Render API and optionally set image.
# Does not modify starserve-dashboard or quote.* DNS.
#
#   export RENDER_API_KEY=rnd_...
#   ./scripts/render/apply-marketing-render.sh
#   RENDER_MARKETING_IMAGE=docker.io/you/starserve-marketing:render ./scripts/render/apply-marketing-render.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

API_HOST="${API_UPSTREAM:-${RENDER_API_HOST}}"
SERVICE_ID="${RENDER_MARKETING_SERVICE_ID:-}"
if [ -z "${SERVICE_ID}" ]; then
  SERVICE_ID="$(render_api_service_id starserve-marketing 2>/dev/null || true)"
fi
[ -n "${SERVICE_ID}" ] || render_die "starserve-marketing not found. Run ./scripts/render/create-marketing-service.sh first."

if [ "${SKIP_API_HEALTH_CHECK:-false}" != "true" ]; then
  HEALTH_URL="https://${API_HOST}/health"
  code="$(curl -sS -o /dev/null -w '%{http_code}' "${HEALTH_URL}" 2>/dev/null || echo 000)"
  if [ "${code}" != "200" ]; then
    render_die "Refusing cutover: ${HEALTH_URL} returned HTTP ${code}. Deploy API first."
  fi
fi

set_env() {
  local svc="$1" key="$2" val="$3"
  local body
  body="$(KEY="$key" VAL="$val" python3 - <<'PY'
import json, os
print(json.dumps({"value": os.environ["VAL"]}))
PY
)"
  render_curl -X PUT \
    "https://api.render.com/v1/services/${svc}/env-vars/${key}" \
    -H "Content-Type: application/json" \
    -d "${body}" >/dev/null
  render_log "Set ${key}=${val}"
}

set_env "${SERVICE_ID}" API_UPSTREAM "${API_HOST}"
set_env "${SERVICE_ID}" SITE_ROLE marketing
set_env "${SERVICE_ID}" PORT 8080
set_env "${SERVICE_ID}" SPA_BASE_PATH ""

# Ensure API CORS allows www + apex + pre-cutover Render host.
CORS_VAL="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,https://quote.starserveinsuranceagency.com,https://www.starserveinsuranceagency.com,https://starserveinsuranceagency.com,https://starserve-dashboard.onrender.com,https://starserve-marketing.onrender.com"
API_SERVICE_ID="$(render_api_service_id starserve-api 2>/dev/null || true)"
if [ -n "${API_SERVICE_ID}" ]; then
  set_env "${API_SERVICE_ID}" CORS_ORIGINS "${CORS_VAL}"
  render_log "Updated starserve-api CORS_ORIGINS (includes www + marketing.onrender.com)"
fi

if [ -n "${RENDER_MARKETING_IMAGE:-}" ]; then
  PATCH_JSON="$(python3 - "${RENDER_MARKETING_IMAGE}" <<'PY'
import json, os, sys
image = sys.argv[1]
print(json.dumps({
    "imagePath": image,
    "image": {
        "ownerId": os.environ["RENDER_OWNER_ID"],
        "imagePath": image,
    },
}))
PY
)"
  render_curl -X PATCH "https://api.render.com/v1/services/${SERVICE_ID}" \
    -H "Content-Type: application/json" \
    -d "${PATCH_JSON}" >/dev/null || render_log "Image patch may require dashboard UI if API rejects partial patch"
  render_log "Requested image → ${RENDER_MARKETING_IMAGE}"
fi

# Trigger redeploy
render_curl -X POST "https://api.render.com/v1/services/${SERVICE_ID}/deploys" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}' >/dev/null || true

render_log "Marketing service id=${SERVICE_ID}"
render_log "Verify Render URL first: https://starserve-marketing.onrender.com/"
render_log "Then attach custom domains www + apex — see docs/deployment/MARKETING_WWW.md"
render_log "Quote app stays on https://quote.starserveinsuranceagency.com/dashboard/ (unchanged)"
