#!/usr/bin/env bash
# One-shot Alembic upgrade as a Cloud Run Job (avoids multi-instance race on boot).
# Usage: migrate.sh <staging|production|backup> [image]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

ENV_NAME="${1:-}"
require_env_name "${ENV_NAME}"
IMAGE="${2:-$(image_base):${ENV_NAME}}"
JOB="$(migrate_job_name "${ENV_NAME}")"
SA="$(runtime_sa "${ENV_NAME}")"
PREFIX="$(secret_prefix "${ENV_NAME}")"
DB_SECRET="${PREFIX}-database-url"

gcloud secrets describe "${DB_SECRET}" --project="${GCP_PROJECT}" >/dev/null 2>&1 \
  || die "Missing secret ${DB_SECRET}. Run scripts/gcp/sync-secrets.sh ${ENV_NAME}"

APP_ENV="${ENV_NAME}"

log "Ensuring Cloud Run Job ${JOB}"
gcloud run jobs deploy "${JOB}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --image="${IMAGE}" \
  --service-account="${SA}" \
  --cpu=1 \
  --memory=512Mi \
  --task-timeout=10m \
  --max-retries=1 \
  --command=python \
  --args=-m,alembic,upgrade,head \
  --set-env-vars="APP_ENV=${APP_ENV},APP_DEBUG=false,DB_PROVIDER=supabase,DB_SSL_MODE=require,DB_NULL_POOL=true,LOG_JSON=true" \
  --set-secrets="DATABASE_URL=${DB_SECRET}:latest" \
  --quiet

log "Executing ${JOB}"
gcloud run jobs execute "${JOB}" \
  --project="${GCP_PROJECT}" \
  --region="${GCP_REGION}" \
  --wait \
  --quiet

log "Migrations complete for ${ENV_NAME}"
