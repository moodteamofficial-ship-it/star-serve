#!/usr/bin/env bash
# Build the public marketing image (www / apex) locally.
# Quote dashboard image is unchanged — use build-dashboard-local.sh for that.
#
# Usage:
#   ./scripts/render/build-marketing-local.sh
#   API_UPSTREAM=starserve-api.onrender.com ./scripts/render/build-marketing-local.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

TAG="${TAG:-starserve-marketing:render-local}"
API_HOST="${API_UPSTREAM:-${RENDER_API_HOST}}"
QUOTE_APP="https://quote.starserveinsuranceagency.com/dashboard"
MARKETING_URL="${VITE_MARKETING_PUBLIC_URL:-https://www.starserveinsuranceagency.com}"

render_log "Building ${TAG} (VITE_SITE_ROLE=marketing, VITE_BASE_PATH=/, API → ${API_HOST})"

docker build \
  -f "${ROOT_DIR}/frontend/Dockerfile.marketing" \
  -t "${TAG}" \
  --build-arg "RENDER_API_UPSTREAM=${API_HOST}" \
  --build-arg "VITE_WEB_URL_PRODUCTION=${QUOTE_APP}" \
  --build-arg "VITE_WEB_URL_STAGING=${QUOTE_APP}" \
  --build-arg "VITE_MARKETING_PUBLIC_URL=${MARKETING_URL}" \
  "${ROOT_DIR}/frontend"

render_log "Built ${TAG}"
render_log "Runtime on Render: PORT=8080 SITE_ROLE=marketing API_UPSTREAM=${API_HOST}"
render_log "Publish: DOCKER_IMAGE=docker.io/YOU/starserve-marketing:render ./scripts/render/publish-marketing-image.sh"
