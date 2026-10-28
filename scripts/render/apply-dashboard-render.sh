#!/usr/bin/env bash
# Point starserve-dashboard at the Render API (+ optional new image).
#
#   export RENDER_API_KEY=rnd_...
#   ./scripts/render/apply-dashboard-render.sh
#   RENDER_DASHBOARD_IMAGE=docker.io/you/starserve-dashboard:render ./scripts/render/apply-dashboard-render.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

API_HOST="${API_UPSTREAM:-${RENDER_API_HOST}}"

if [ "${SKIP_API_HEALTH_CHECK:-false}" != "true" ]; then
  HEALTH_URL="https://${API_HOST}/health"
  code="$(curl -sS -o /dev/null -w '%{http_code}' "${HEALTH_URL}" 2>/dev/null || echo 000)"
  if [ "${code}" != "200" ]; then
    render_die "Refusing cutover: ${HEALTH_URL} returned HTTP ${code}. Deploy API first (./scripts/render/deploy-git-stack.sh or publish-and-deploy-api.sh)."
  fi
fi

for key in API_UPSTREAM SPA_BASE_PATH PORT; do
  case "$key" in
    API_UPSTREAM) val="${API_HOST}" ;;
    SPA_BASE_PATH) val="/dashboard" ;;
    PORT) val="8080" ;;
  esac
  render_curl -X PUT \
    "https://api.render.com/v1/services/${RENDER_DASHBOARD_SERVICE_ID}/env-vars/${key}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json; print(json.dumps({'value': '${val}'}))")" >/dev/null
  render_log "Set ${key}=${val}"
done

if [ -n "${RENDER_DASHBOARD_IMAGE:-}" ]; then
  PATCH_JSON="$(python3 - "${RENDER_DASHBOARD_IMAGE}" <<'PY'
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
  render_curl -X PATCH "https://api.render.com/v1/services/${RENDER_DASHBOARD_SERVICE_ID}" \
    -H "Content-Type: application/json" \
    -d "${PATCH_JSON}" >/dev/null || render_log "Image patch may require dashboard UI if API rejects partial patch"
  render_log "Requested image → ${RENDER_DASHBOARD_IMAGE}"
fi

render_log "Dashboard will redeploy; verify https://quote.starserveinsuranceagency.com/dashboard/"
