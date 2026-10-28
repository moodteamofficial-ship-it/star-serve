#!/usr/bin/env bash
# Tag + push a locally built API image to Docker Hub or GHCR (no GCP).
#
# Usage (Docker Hub):
#   docker login
#   LOCAL_TAG=starserve-api:local \
#   DOCKER_IMAGE=docker.io/YOURUSER/starserve-api:latest \
#   ./scripts/render/publish-api-image.sh
#
# Usage (GHCR):
#   DOCKER_IMAGE=ghcr.io/YOURORG/starserve-api:latest ./scripts/render/publish-api-image.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

LOCAL_TAG="${LOCAL_TAG:-starserve-api:local}"
DOCKER_IMAGE="${DOCKER_IMAGE:-}"

[ -n "${DOCKER_IMAGE}" ] || render_die "Set DOCKER_IMAGE (e.g. docker.io/you/starserve-api:latest)"

render_log "Tagging ${LOCAL_TAG} → ${DOCKER_IMAGE}"
docker tag "${LOCAL_TAG}" "${DOCKER_IMAGE}"
docker push "${DOCKER_IMAGE}"
render_log "Pushed ${DOCKER_IMAGE}"
render_log "Deploy: RENDER_API_IMAGE=${DOCKER_IMAGE} ./scripts/render/apply-production.sh"
