#!/usr/bin/env bash
# Create starserve-marketing on Render (idempotent). Prefer Git Docker build.
#
#   export RENDER_API_KEY=rnd_...
#   export RENDER_GIT_REPO=https://github.com/moodteamofficial-ship-it/star-serve
#   ./scripts/render/create-marketing-service.sh
#
# Or image-based:
#   RENDER_MARKETING_IMAGE=docker.io/YOU/starserve-marketing:render ./scripts/render/create-marketing-service.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

EXISTING="$(render_api_service_id starserve-marketing 2>/dev/null || true)"
if [ -n "${EXISTING}" ]; then
  render_log "starserve-marketing already exists: ${EXISTING}"
  printf '%s' "${EXISTING}"
  exit 0
fi

RENDER_GIT_REPO="${RENDER_GIT_REPO:-${RENDER_API_REPO:-}}"
RENDER_GIT_BRANCH="${RENDER_GIT_BRANCH:-${RENDER_API_BRANCH:-main}}"
RENDER_MARKETING_ROOT_DIR="${RENDER_MARKETING_ROOT_DIR:-frontend}"
RENDER_MARKETING_IMAGE="${RENDER_MARKETING_IMAGE:-}"

CREATE_JSON=""

if [ -n "${RENDER_GIT_REPO}" ]; then
  render_log "Creating starserve-marketing from Git ${RENDER_GIT_REPO} (${RENDER_GIT_BRANCH})"
  CREATE_JSON="$(RENDER_OWNER_ID="${RENDER_OWNER_ID}" \
    RENDER_ENVIRONMENT_ID="${RENDER_ENVIRONMENT_ID}" \
    RENDER_GIT_REPO="${RENDER_GIT_REPO}" \
    RENDER_GIT_BRANCH="${RENDER_GIT_BRANCH}" \
    RENDER_MARKETING_ROOT_DIR="${RENDER_MARKETING_ROOT_DIR}" \
    python3 <<'PY'
import json, os
print(json.dumps({
    "type": "web_service",
    "name": "starserve-marketing",
    "ownerId": os.environ["RENDER_OWNER_ID"],
    "environmentId": os.environ["RENDER_ENVIRONMENT_ID"],
    "repo": os.environ["RENDER_GIT_REPO"],
    "branch": os.environ["RENDER_GIT_BRANCH"],
    "rootDir": os.environ["RENDER_MARKETING_ROOT_DIR"],
    "autoDeploy": "yes",
    "serviceDetails": {
        "runtime": "docker",
        "env": "docker",
        "region": "frankfurt",
        "plan": "starter",
        "healthCheckPath": "/ready",
        "envSpecificDetails": {
            "dockerfilePath": "./Dockerfile.marketing",
            "dockerContext": ".",
        },
    },
}))
PY
)"
elif [ -n "${RENDER_MARKETING_IMAGE}" ]; then
  render_log "Creating starserve-marketing from image ${RENDER_MARKETING_IMAGE}"
  CREATE_JSON="$(RENDER_OWNER_ID="${RENDER_OWNER_ID}" \
    RENDER_ENVIRONMENT_ID="${RENDER_ENVIRONMENT_ID}" \
    RENDER_REGISTRY_CREDENTIAL_ID="${RENDER_REGISTRY_CREDENTIAL_ID:-}" \
    python3 - "${RENDER_MARKETING_IMAGE}" <<'PY'
import json, os, sys
image = sys.argv[1]
cred = os.environ.get("RENDER_REGISTRY_CREDENTIAL_ID", "").strip()
payload = {
    "type": "web_service",
    "name": "starserve-marketing",
    "ownerId": os.environ["RENDER_OWNER_ID"],
    "environmentId": os.environ["RENDER_ENVIRONMENT_ID"],
    "image": {
        "ownerId": os.environ["RENDER_OWNER_ID"],
        "imagePath": image,
    },
    "serviceDetails": {
        "runtime": "image",
        "env": "image",
        "region": "frankfurt",
        "plan": "starter",
        "healthCheckPath": "/ready",
    },
}
if cred:
    payload["image"]["registryCredentialId"] = cred
print(json.dumps(payload))
PY
)"
else
  render_die "Set RENDER_GIT_REPO=https://github.com/.../star-serve or RENDER_MARKETING_IMAGE=docker.io/..."
fi

RESP="$(render_curl -X POST "https://api.render.com/v1/services" \
  -H "Content-Type: application/json" \
  -d "${CREATE_JSON}")"
SERVICE_ID="$(printf '%s' "${RESP}" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d.get("service") or d; print(s.get("id") or "")')"
[ -n "${SERVICE_ID}" ] || render_die "Create failed: ${RESP}"
render_log "Created starserve-marketing: ${SERVICE_ID}"
printf '%s' "${SERVICE_ID}"
