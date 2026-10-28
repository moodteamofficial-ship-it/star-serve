#!/usr/bin/env bash
# Create starserve-api + wire starserve-dashboard on Render (Git Docker builds).
#
# Prerequisites:
#   - Repo pushed to GitHub (BirdviewInsurance or your org)
#   - Render GitHub app has access to that repo
#
#   export RENDER_API_KEY=rnd_...
#   export RENDER_GIT_REPO=https://github.com/BirdviewInsurance/starserve-v1
#   export RENDER_GIT_BRANCH=main
#   ./scripts/render/deploy-git-stack.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

RENDER_GIT_REPO="${RENDER_GIT_REPO:-}"
RENDER_GIT_BRANCH="${RENDER_GIT_BRANCH:-main}"
[ -n "${RENDER_GIT_REPO}" ] || render_die "Set RENDER_GIT_REPO (https://github.com/org/repo)"

export RENDER_API_REPO="${RENDER_GIT_REPO}"
export RENDER_API_BRANCH="${RENDER_GIT_BRANCH}"
export RENDER_API_ROOT_DIR="${RENDER_API_ROOT_DIR:-backend}"

API_ID="$("${SCRIPT_DIR}/create-api-service.sh")"
export API_SERVICE_ID="${API_ID}"
export RENDER_API_KEY
[ -f "${ENV_FILE}" ] || render_die "Missing ${ENV_FILE}"

SKIP_DASHBOARD_CUTOVER=true "${SCRIPT_DIR}/apply-production.sh"

render_log "Waiting for API https://${RENDER_API_HOST}/health"
for _ in $(seq 1 90); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' "https://${RENDER_API_HOST}/health" 2>/dev/null || echo 000)"
  if [ "${code}" = "200" ]; then
    render_log "API healthy"
    break
  fi
  sleep 10
done

SKIP_HEALTH="${SKIP_API_HEALTH_CHECK:-false}"
if [ "${SKIP_HEALTH}" != "true" ]; then
  code="$(curl -sS -o /dev/null -w '%{http_code}' "https://${RENDER_API_HOST}/health" 2>/dev/null || echo 000)"
  [ "${code}" = "200" ] || render_die "API not ready (HTTP ${code}). Check Render logs for starserve-api."
fi

API_UPSTREAM="${RENDER_API_HOST}" SKIP_API_HEALTH_CHECK=true "${SCRIPT_DIR}/apply-dashboard-render.sh"

render_log "Stack on Render: dashboard → ${RENDER_API_HOST} (same-origin /api/v1)"
render_log "Verify: https://quote.starserveinsuranceagency.com/dashboard/"
