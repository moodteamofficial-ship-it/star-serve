#!/usr/bin/env bash
# Create + wire starserve-marketing (www site) on Render.
# Leaves starserve-dashboard / quote.* alone.
#
#   export RENDER_API_KEY=rnd_...
#   export RENDER_GIT_REPO=https://github.com/moodteamofficial-ship-it/star-serve
#   ./scripts/render/deploy-marketing.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

RENDER_GIT_REPO="${RENDER_GIT_REPO:-}"
[ -n "${RENDER_GIT_REPO}" ] || [ -n "${RENDER_MARKETING_IMAGE:-}" ] \
  || render_die "Set RENDER_GIT_REPO or RENDER_MARKETING_IMAGE"

SERVICE_ID="$("${SCRIPT_DIR}/create-marketing-service.sh")"
export RENDER_MARKETING_SERVICE_ID="${SERVICE_ID}"

"${SCRIPT_DIR}/apply-marketing-render.sh"

render_log "Waiting for https://starserve-marketing.onrender.com/ready"
for _ in $(seq 1 60); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' "https://starserve-marketing.onrender.com/ready" 2>/dev/null || echo 000)"
  if [ "${code}" = "200" ]; then
    render_log "Marketing ready"
    break
  fi
  sleep 10
done

code="$(curl -sS -o /dev/null -w '%{http_code}' "https://starserve-marketing.onrender.com/ready" 2>/dev/null || echo 000)"
[ "${code}" = "200" ] || render_log "Still deploying (HTTP ${code}). Check Render logs for starserve-marketing."

boot="$(curl -sS -o /dev/null -w '%{http_code}' "https://starserve-marketing.onrender.com/api/v1/website/bootstrap" 2>/dev/null || echo 000)"
render_log "Bootstrap via marketing proxy: HTTP ${boot} (expect 200 once API + CMS are up)"

render_log "Next: attach www.starserveinsuranceagency.com in Render, then update GoDaddy DNS"
render_log "Guide: docs/deployment/MARKETING_WWW.md"
