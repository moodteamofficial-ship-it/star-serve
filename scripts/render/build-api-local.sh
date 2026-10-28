#!/usr/bin/env bash
# Build the API image locally (no Cloud Build / Artifact Registry).
#
# Usage:
#   ./scripts/render/build-api-local.sh
#   TAG=myregistry/starserve-api:v1 ./scripts/render/build-api-local.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

TAG="${TAG:-starserve-api:local}"

render_log "Building ${TAG} from ${BACKEND_DIR}"
docker build -t "${TAG}" "${BACKEND_DIR}"
render_log "Built ${TAG}"
render_log "Publish: DOCKER_IMAGE=${TAG} ./scripts/render/publish-api-image.sh"
render_log "Migrate: ./scripts/render/migrate-local.sh ${TAG}"
