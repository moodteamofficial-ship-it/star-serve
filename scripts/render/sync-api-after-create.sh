#!/usr/bin/env bash
# After you create starserve-api in the Render UI (Public Git / Git Provider):
#   export RENDER_API_KEY=rnd_...
#   ./scripts/render/sync-api-after-create.sh
#
# Sets health check, Docker paths, and all env vars from v1.0/.env (never printed).
# You still add Secret File gcs-sa.json in the dashboard once (GCS JSON).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

require_render_api_url
[ -f "${ENV_FILE}" ] || render_die "Missing ${ENV_FILE}"

API_SERVICE_ID="$(render_api_service_id starserve-api 2>/dev/null || true)"
[ -n "${API_SERVICE_ID}" ] || render_die "Create Web Service named starserve-api first, then re-run this script."

render_log "Patching service ${API_SERVICE_ID} (health + Docker)"
PATCH_BODY="$(python3 -c 'import json; print(json.dumps({
    "rootDir": "backend",
    "serviceDetails": {
        "healthCheckPath": "/health",
        "envSpecificDetails": {
            "dockerContext": ".",
            "dockerfilePath": "./Dockerfile",
        },
    },
}))')"
render_curl -X PATCH "https://api.render.com/v1/services/${API_SERVICE_ID}" \
  -H "Content-Type: application/json" \
  -d "${PATCH_BODY}" >/dev/null

render_log "Syncing environment from ${ENV_FILE}"
export API_SERVICE_ID ENV_FILE BACKEND_DIR RENDER_API_BASE_URL RENDER_API_KEY
python3 "${SCRIPT_DIR}/sync_api_env.py"

if [ "${SKIP_DASHBOARD_CUTOVER:-false}" != "true" ]; then
  render_log "Triggering deploy (clear build cache optional in dashboard)"
  render_curl -X POST "https://api.render.com/v1/services/${API_SERVICE_ID}/deploys" \
    -H "Content-Type: application/json" \
    -d '{"clearCache":"do_not_clear"}' >/dev/null 2>&1 || true
fi

render_log "Done. Add Secret File gcs-sa.json → /etc/secrets/gcs-sa.json if not already."
render_log "Verify: curl -sS https://${RENDER_API_HOST}/health"
