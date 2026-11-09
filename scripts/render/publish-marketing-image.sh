#!/usr/bin/env bash
# Tag and push a local marketing image to Docker Hub / GHCR.
#
#   docker login
#   DOCKER_IMAGE=docker.io/YOU/starserve-marketing:render \
#     LOCAL_TAG=starserve-marketing:render-local \
#     ./scripts/render/publish-marketing-image.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

LOCAL_TAG="${LOCAL_TAG:-starserve-marketing:render-local}"
DOCKER_IMAGE="${DOCKER_IMAGE:-}"
[ -n "${DOCKER_IMAGE}" ] || render_die "Set DOCKER_IMAGE=docker.io/YOU/starserve-marketing:render"

render_log "Tagging ${LOCAL_TAG} → ${DOCKER_IMAGE}"
docker tag "${LOCAL_TAG}" "${DOCKER_IMAGE}"
docker push "${DOCKER_IMAGE}"
render_log "Pushed ${DOCKER_IMAGE}"
render_log "Next: RENDER_MARKETING_IMAGE=${DOCKER_IMAGE} ./scripts/render/apply-marketing-render.sh"
