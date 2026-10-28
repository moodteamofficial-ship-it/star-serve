#!/usr/bin/env bash
# Create starserve-api on Render (idempotent). One of: Git docker, external image, or GAR image.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

API_SERVICE_ID="$(render_api_service_id starserve-api 2>/dev/null || true)"
if [ -n "${API_SERVICE_ID}" ]; then
  render_log "starserve-api already exists: ${API_SERVICE_ID}"
  printf '%s' "${API_SERVICE_ID}"
  exit 0
fi

CREATE_JSON=""

if [ -n "${RENDER_API_REPO}" ]; then
  render_log "Creating starserve-api from Git ${RENDER_API_REPO} (${RENDER_API_BRANCH})"
  CREATE_JSON="$(RENDER_OWNER_ID="${RENDER_OWNER_ID}" \
    RENDER_ENVIRONMENT_ID="${RENDER_ENVIRONMENT_ID}" \
    RENDER_API_REPO="${RENDER_API_REPO}" \
    RENDER_API_BRANCH="${RENDER_API_BRANCH}" \
    RENDER_API_ROOT_DIR="${RENDER_API_ROOT_DIR}" \
    python3 <<'PY'
import json, os
print(json.dumps({
    "type": "web_service",
    "name": "starserve-api",
    "ownerId": os.environ["RENDER_OWNER_ID"],
    "environmentId": os.environ["RENDER_ENVIRONMENT_ID"],
    "repo": os.environ["RENDER_API_REPO"],
    "branch": os.environ["RENDER_API_BRANCH"],
    "rootDir": os.environ["RENDER_API_ROOT_DIR"],
    "autoDeploy": "yes",
    "serviceDetails": {
        "runtime": "docker",
        "env": "docker",
        "region": "frankfurt",
        "plan": "starter",
        "healthCheckPath": "/health",
        "envSpecificDetails": {
            "dockerfilePath": "./Dockerfile",
            "dockerContext": ".",
        },
    },
}))
PY
)"
elif [ -n "${RENDER_API_IMAGE}" ]; then
  render_log "Creating starserve-api from image ${RENDER_API_IMAGE}"
  CREATE_JSON="$(RENDER_OWNER_ID="${RENDER_OWNER_ID}" \
    RENDER_ENVIRONMENT_ID="${RENDER_ENVIRONMENT_ID}" \
    RENDER_REGISTRY_CREDENTIAL_ID="${RENDER_REGISTRY_CREDENTIAL_ID:-}" \
    python3 - "${RENDER_API_IMAGE}" <<'PY'
import json, os, sys
image = sys.argv[1]
cred = os.environ.get("RENDER_REGISTRY_CREDENTIAL_ID", "").strip()
payload = {
    "type": "web_service",
    "name": "starserve-api",
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
        "healthCheckPath": "/health",
    },
}
if cred:
    payload["image"]["registryCredentialId"] = cred
print(json.dumps(payload))
PY
)"
elif [ -n "${API_RENDER_IMAGE}" ]; then
  render_log "Creating starserve-api from GAR ${API_RENDER_IMAGE}"
  CREATE_JSON="$(RENDER_OWNER_ID="${RENDER_OWNER_ID}" \
    RENDER_ENVIRONMENT_ID="${RENDER_ENVIRONMENT_ID}" \
    RENDER_REGISTRY_CREDENTIAL_ID="${RENDER_REGISTRY_CREDENTIAL_ID}" \
    python3 - "${API_RENDER_IMAGE}" <<'PY'
import json, os, sys
image = sys.argv[1]
print(json.dumps({
    "type": "web_service",
    "name": "starserve-api",
    "ownerId": os.environ["RENDER_OWNER_ID"],
    "environmentId": os.environ["RENDER_ENVIRONMENT_ID"],
    "image": {
        "ownerId": os.environ["RENDER_OWNER_ID"],
        "imagePath": image,
        "registryCredentialId": os.environ["RENDER_REGISTRY_CREDENTIAL_ID"],
    },
    "serviceDetails": {
        "runtime": "image",
        "env": "image",
        "region": "frankfurt",
        "plan": "starter",
        "healthCheckPath": "/health",
    },
}))
PY
)"
else
  render_die "Set RENDER_API_REPO, RENDER_API_IMAGE, or API_RENDER_IMAGE (see docs/deployment/RENDER.md)"
fi

RESP="$(render_curl -X POST "https://api.render.com/v1/services" \
  -H "Content-Type: application/json" \
  -d "${CREATE_JSON}")"
API_SERVICE_ID="$(printf '%s' "${RESP}" | python3 -c 'import json,sys
d=json.load(sys.stdin)
print(d.get("service",d).get("id",""))' 2>/dev/null || true)"
if [ -z "${API_SERVICE_ID}" ]; then
  render_die "Create failed: ${RESP}"
fi
render_log "Created starserve-api ${API_SERVICE_ID}"
printf '%s' "${API_SERVICE_ID}"
