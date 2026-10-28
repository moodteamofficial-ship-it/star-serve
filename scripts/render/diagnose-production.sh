#!/usr/bin/env bash
# Quick checks for quote / Render / Cloud Run API connectivity.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

check() {
  local label="$1"
  local url="$2"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' "${url}" 2>/dev/null || echo err)"
  printf '%-42s %s\n' "${label}" "${code}"
}

render_log "Production API connectivity"
check "Render API /health" "https://${RENDER_API_HOST}/health"
check "Cloud Run API /health" "https://starserve-api-233389149626.europe-west1.run.app/health"
check "Cloud Run alt URL /health" "https://starserve-api-edibu6e5na-ew.a.run.app/health"
check "quote /api/v1/health (nginx proxy)" "https://quote.starserveinsuranceagency.com/api/v1/health"
check "quote /dashboard/" "https://quote.starserveinsuranceagency.com/dashboard/"

if [ -n "${RENDER_API_KEY:-}" ]; then
  # shellcheck source=render-api.sh
  source "${SCRIPT_DIR}/render-api.sh"
  upstream="$(render_curl "https://api.render.com/v1/services/${RENDER_DASHBOARD_SERVICE_ID}/env-vars/API_UPSTREAM" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("value",""))' 2>/dev/null || true)"
  render_log "Dashboard API_UPSTREAM=${upstream:-unknown}"
fi

render_log "Sign-in needs a healthy API behind quote /api/v1 (usually 200 on /health)."
