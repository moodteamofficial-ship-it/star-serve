#!/usr/bin/env bash
# Build + push the Render-oriented SPA image (base path /dashboard).
# Does NOT deploy to Cloud Run and does NOT update production CORS / EMAIL_APP_URL.
#
# Usage:
#   ./scripts/gcp/build-frontend-render.sh
#   API_UPSTREAM=starserve-api.onrender.com ./scripts/gcp/build-frontend-render.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=../render/config.sh
source "${SCRIPT_DIR}/../render/config.sh"

TAG="${1:-render}"
IMAGE="$(web_image_base):${TAG}"
# Default to Render production API host; override for rollback / staging tests.
API_BUILD_DEFAULT="${RENDER_API_HOST}"
API_UPSTREAM_OVERRIDE="${API_UPSTREAM:-}"

log "Building Render SPA image ${IMAGE} (VITE_BASE_PATH=/dashboard/)"
log "QR / VITE_WEB_URL_PRODUCTION → https://quote.starserveinsuranceagency.com/dashboard"

cd "${ROOT_DIR}"
gcloud builds submit \
  --project="${GCP_PROJECT}" \
  --config=infra/gcp/cloudbuild-frontend-render.yaml \
  --substitutions="_IMAGE=${IMAGE}" \
  frontend/

log "Pushed ${IMAGE}"
log "Render → Deploy an existing image from a registry:"
log "  Image URL: ${IMAGE}"
log "  Env: PORT=8080"
log "  Env: API_UPSTREAM=${API_UPSTREAM_OVERRIDE:-$API_BUILD_DEFAULT}"
log "  Env: SPA_BASE_PATH=/dashboard"
log "  Health check path: /ready"
log "  (MARKETING_* no longer used — quote.* redirects / → /dashboard/)"
log "Custom domain: quote.starserveinsuranceagency.com → this service"
log "Ensure API CORS includes https://quote.starserveinsuranceagency.com"
