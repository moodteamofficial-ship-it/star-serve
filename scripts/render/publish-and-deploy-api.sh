#!/usr/bin/env bash
# Push local API image to Docker Hub and create starserve-api on Render.
#
#   docker login
#   export DOCKERHUB_USER=your-dockerhub-username
#   export RENDER_API_KEY=rnd_...
#   ./scripts/render/publish-and-deploy-api.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

DOCKERHUB_USER="${DOCKERHUB_USER:-}"
[ -n "${DOCKERHUB_USER}" ] || render_die "Set DOCKERHUB_USER (docker hub username). Run: docker login"

LOCAL_TAG="${LOCAL_TAG:-starserve-api:local}"
IMAGE="docker.io/${DOCKERHUB_USER}/starserve-api:latest"

if [ -n "${DOCKERHUB_TOKEN:-}" ]; then
  render_log "Logging in to Docker Hub as ${DOCKERHUB_USER} (DOCKERHUB_TOKEN)"
  printf '%s' "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USER}" --password-stdin
fi

docker image inspect "${LOCAL_TAG}" >/dev/null 2>&1 \
  || "${SCRIPT_DIR}/build-api-local.sh"

render_log "Pushing ${IMAGE}"
docker tag "${LOCAL_TAG}" "${IMAGE}"
docker push "${IMAGE}"

export RENDER_API_IMAGE="${IMAGE}"
"${SCRIPT_DIR}/apply-production.sh"
"${SCRIPT_DIR}/apply-dashboard-render.sh"

render_log "Done — test: curl -sS https://${RENDER_API_HOST}/health"
