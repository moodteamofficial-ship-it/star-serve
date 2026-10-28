#!/usr/bin/env bash
# One-shot Alembic upgrade using the Render API image (same as Cloud Run Job).
# Reads DATABASE_URL from Secret Manager — value is never printed.
#
# Usage:
#   ./scripts/render/migrate.sh production
#   IMAGE=europe-west1-docker.pkg.dev/.../api:render ./scripts/render/migrate.sh staging
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

ENV_NAME="${1:-}"
require_env_name "${ENV_NAME}"
IMAGE="${2:-${API_RENDER_IMAGE}}"
PREFIX="$(secret_prefix "${ENV_NAME}")"
DB_SECRET="${PREFIX}-database-url"

gcloud secrets describe "${DB_SECRET}" --project="${GCP_PROJECT}" >/dev/null 2>&1 \
  || render_die "Missing secret ${DB_SECRET}. Run scripts/gcp/sync-secrets.sh ${ENV_NAME}"

render_log "Running alembic upgrade head (${ENV_NAME}) with ${IMAGE}"

DATABASE_URL="$(gcloud secrets versions access latest --secret="${DB_SECRET}" --project="${GCP_PROJECT}")"
[ -n "${DATABASE_URL}" ] || render_die "Empty ${DB_SECRET}"

docker run --rm \
  -e "APP_ENV=${ENV_NAME}" \
  -e "APP_DEBUG=false" \
  -e "DB_PROVIDER=supabase" \
  -e "DB_SSL_MODE=require" \
  -e "DB_NULL_POOL=true" \
  -e "LOG_JSON=true" \
  -e "DATABASE_URL=${DATABASE_URL}" \
  "${IMAGE}" \
  python -m alembic upgrade head

render_log "Migrations complete for ${ENV_NAME}"
