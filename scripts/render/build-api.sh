#!/usr/bin/env bash
# Build + push the production API image for Render (Artifact Registry tag :render).
# Does NOT deploy to Cloud Run.
#
# Usage:
#   ./scripts/render/build-api.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

log "Building Render API image ${API_RENDER_IMAGE}"

cd "${ROOT_DIR}"
gcloud builds submit \
  --project="${GCP_PROJECT}" \
  --config=infra/gcp/cloudbuild-api-render.yaml \
  --substitutions="_IMAGE=${API_RENDER_IMAGE}" \
  .

render_log "Pushed ${API_RENDER_IMAGE}"
render_log "Render → New Web Service → Deploy an existing image from a registry"
render_log "  Image URL: ${API_RENDER_IMAGE}"
render_log "  Health check path: /health"
render_log "  PORT: 8000 (Render sets PORT; entrypoint honours it)"
render_log "Then: ./scripts/render/migrate.sh production"
render_log "      ./scripts/render/print-production-env.sh"
render_log "Update dashboard API_UPSTREAM=${RENDER_API_HOST} and redeploy SPA"
