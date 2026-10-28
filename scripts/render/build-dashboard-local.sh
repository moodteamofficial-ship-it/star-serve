#!/usr/bin/env bash
# Build the Render SPA image locally (nginx → Render API, /dashboard mount).
# Same behaviour as quote.starserveinsuranceagency.com: same-origin /api/v1 proxy.
#
# Usage:
#   ./scripts/render/build-dashboard-local.sh
#   API_UPSTREAM=starserve-api.onrender.com ./scripts/render/build-dashboard-local.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

TAG="${TAG:-starserve-dashboard:render-local}"
API_HOST="${API_UPSTREAM:-${RENDER_API_HOST}}"
QUOTE_APP="https://quote.starserveinsuranceagency.com/dashboard"

render_log "Building ${TAG} (VITE_BASE_PATH=/dashboard/, API_UPSTREAM default ${API_HOST})"

docker build \
  -t "${TAG}" \
  --build-arg "RENDER_SPA_BASE_PATH=/dashboard" \
  --build-arg "RENDER_API_UPSTREAM=${API_HOST}" \
  --build-arg "VITE_BASE_PATH=/dashboard/" \
  --build-arg "VITE_DEFAULT_API_ENV=production" \
  --build-arg "VITE_ALLOW_PRODUCTION_ENV_SWITCH=false" \
  --build-arg "VITE_WEB_URL_PRODUCTION=${QUOTE_APP}" \
  --build-arg "VITE_WEB_URL_STAGING=${QUOTE_APP}" \
  --build-arg "VITE_API_URL_STAGING=/api/v1" \
  --build-arg "VITE_API_URL_PRODUCTION=/api/v1" \
  --build-arg "VITE_API_URL_BACKUP=/api/v1" \
  "${ROOT_DIR}/frontend"

render_log "Built ${TAG}"
render_log "Runtime on Render: PORT=8080 SPA_BASE_PATH=/dashboard API_UPSTREAM=${API_HOST}"
render_log "Publish: DOCKER_IMAGE=docker.io/YOU/starserve-dashboard:render ./scripts/render/publish-dashboard-image.sh"
