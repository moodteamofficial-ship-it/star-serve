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

if [ "${SYNC_EXISTING_ONLY:-false}" = "true" ]; then
  API_SERVICE_ID="$(render_api_service_id starserve-api 2>/dev/null || true)"
  [ -n "${API_SERVICE_ID}" ] || render_die "Create starserve-api in Render, then ./scripts/render/sync-api-after-create.sh"
else
  API_SERVICE_ID="$("${SCRIPT_DIR}/create-api-service.sh")"
fi

export API_SERVICE_ID ENV_FILE BACKEND_DIR RENDER_API_BASE_URL RENDER_API_HOST RENDER_API_KEY
python3 "${SCRIPT_DIR}/sync_api_env.py"

if [ "${SKIP_DASHBOARD_CUTOVER:-false}" = "true" ]; then
  render_log "Env synced (SKIP_DASHBOARD_CUTOVER=true)"
  exit 0
fi

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
