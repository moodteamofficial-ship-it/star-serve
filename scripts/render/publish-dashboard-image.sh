#!/usr/bin/env bash
# Push local Render SPA image to Docker Hub / GHCR.
#
#   LOCAL_TAG=starserve-dashboard:render-local \
#   DOCKER_IMAGE=docker.io/YOU/starserve-dashboard:render \
#   ./scripts/render/publish-dashboard-image.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

LOCAL_TAG="${LOCAL_TAG:-starserve-dashboard:render-local}"
DOCKER_IMAGE="${DOCKER_IMAGE:-}"
[ -n "${DOCKER_IMAGE}" ] || render_die "Set DOCKER_IMAGE"

docker tag "${LOCAL_TAG}" "${DOCKER_IMAGE}"
docker push "${DOCKER_IMAGE}"
render_log "Pushed ${DOCKER_IMAGE}"
render_log "Update Render starserve-dashboard image URL, or run apply-dashboard-render.sh"
