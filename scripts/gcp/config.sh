# Shared GCP settings for Star Serve Cloud Run.
# shellcheck shell=bash

GCP_PROJECT="${GCP_PROJECT:-star-serve-508614}"
GCP_REGION="${GCP_REGION:-europe-west1}"
AR_REPO="${AR_REPO:-starserve}"
APP_IMAGE_NAME="${APP_IMAGE_NAME:-api}"
WEB_IMAGE_NAME="${WEB_IMAGE_NAME:-web}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"

runtime_sa() {
  local env="$1"
  if [ "$env" = "production" ]; then
    echo "starserve-api@${GCP_PROJECT}.iam.gserviceaccount.com"
  else
    echo "starserve-api-${env}@${GCP_PROJECT}.iam.gserviceaccount.com"
  fi
}

runtime_sa_id() {
  local env="$1"
  if [ "$env" = "production" ]; then
    echo "starserve-api"
  else
    echo "starserve-api-${env}"
  fi
}

service_name() {
  local env="$1"
  if [ "$env" = "production" ]; then
    echo "starserve-api"
  else
    echo "starserve-api-${env}"
  fi
}

web_service_name() {
  local env="$1"
  if [ "$env" = "production" ]; then
    echo "starserve-dashboard"
  else
    echo "starserve-dashboard-${env}"
  fi
}

migrate_job_name() {
  echo "starserve-migrate-$1"
}

secret_prefix() {
  local env="$1"
  if [ "$env" = "production" ]; then
    echo "starserve-prod"
  else
    echo "starserve-${env}"
  fi
}

image_base() {
  echo "${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}/${APP_IMAGE_NAME}"
}

web_image_base() {
  echo "${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}/${WEB_IMAGE_NAME}"
}

require_env_name() {
  local env="${1:-}"
  case "$env" in
    staging|production|backup) return 0 ;;
    *)
      echo "Usage: $0 <staging|production|backup>" >&2
      exit 2
      ;;
  esac
}

log() {
  printf '[gcp] %s\n' "$*"
}

die() {
  printf '[gcp] ERROR: %s\n' "$*" >&2
  exit 1
}
