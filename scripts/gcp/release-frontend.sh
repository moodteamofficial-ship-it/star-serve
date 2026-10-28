#!/usr/bin/env bash
# Build (Cloud Build) + deploy the StarServe SPA for one environment.
# Usage: release-frontend.sh <staging|production|backup>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

ENV_NAME="${1:-}"
require_env_name "${ENV_NAME}"

API_UPSTREAM="starserve-api-staging-233389149626.europe-west1.run.app"
if [ "${ENV_NAME}" = "production" ]; then
  API_UPSTREAM="starserve-api-233389149626.europe-west1.run.app"
fi

log "Releasing frontend ${ENV_NAME} via Cloud Build"
cd "${ROOT_DIR}"
gcloud builds submit \
  --project="${GCP_PROJECT}" \
  --config=infra/gcp/cloudbuild-frontend.yaml \
  --substitutions="_ENV=${ENV_NAME},_REGION=${GCP_REGION},_AR_REPO=${AR_REPO},_API_UPSTREAM=${API_UPSTREAM}"
