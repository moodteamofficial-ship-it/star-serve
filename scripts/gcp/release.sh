#!/usr/bin/env bash
# Build (Cloud Build) + migrate + deploy one environment.
# Usage: release.sh <staging|production|backup>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

ENV_NAME="${1:-}"
require_env_name "${ENV_NAME}"

log "Releasing ${ENV_NAME} via Cloud Build (no local Docker required)"
cd "${ROOT_DIR}"
gcloud builds submit \
  --project="${GCP_PROJECT}" \
  --config=infra/gcp/cloudbuild.yaml \
  --substitutions="_ENV=${ENV_NAME},_REGION=${GCP_REGION},_AR_REPO=${AR_REPO}"
