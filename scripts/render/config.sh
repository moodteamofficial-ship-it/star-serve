# Shared Render deployment settings (production API + SPA on Render).
# shellcheck shell=bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../gcp/config.sh
source "${SCRIPT_DIR}/../gcp/config.sh"

# Host only — no scheme. Set after creating the Render web service, or override per command.
RENDER_API_HOST="${RENDER_API_HOST:-starserve-api.onrender.com}"
RENDER_DASHBOARD_HOST="${RENDER_DASHBOARD_HOST:-starserve-dashboard.onrender.com}"

# Render resource IDs (Birdview workspace — do not commit RENDER_API_KEY).
RENDER_OWNER_ID="${RENDER_OWNER_ID:-tea-d0iqggbuibrs73evhssg}"
RENDER_ENVIRONMENT_ID="${RENDER_ENVIRONMENT_ID:-evm-dapb4hn40ujc7392r720}"
RENDER_REGISTRY_CREDENTIAL_ID="${RENDER_REGISTRY_CREDENTIAL_ID:-rgc-dapgf53m8hqs739njv1g}"
RENDER_DASHBOARD_SERVICE_ID="${RENDER_DASHBOARD_SERVICE_ID:-srv-dapgidbbc2fs73fm165g}"

# GCP Artifact Registry (optional — requires billing). Prefer RENDER_API_IMAGE or Git build.
API_RENDER_IMAGE="${API_RENDER_IMAGE:-}"
WEB_RENDER_IMAGE="${WEB_RENDER_IMAGE:-$(web_image_base):render}"

# External registry image, e.g. docker.io/you/starserve-api:latest or ghcr.io/org/starserve-api:latest
RENDER_API_IMAGE="${RENDER_API_IMAGE:-}"

# Git → Render builds Dockerfile on deploy (no GAR). Example: https://github.com/org/StarServe
RENDER_API_REPO="${RENDER_API_REPO:-}"
RENDER_API_BRANCH="${RENDER_API_BRANCH:-main}"
RENDER_API_ROOT_DIR="${RENDER_API_ROOT_DIR:-backend}"

render_log() {
  printf '[render] %s\n' "$*"
}

render_die() {
  printf '[render] ERROR: %s\n' "$*" >&2
  exit 1
}

require_render_api_url() {
  if [ -z "${RENDER_API_BASE_URL:-}" ]; then
    RENDER_API_BASE_URL="https://${RENDER_API_HOST}"
  fi
  RENDER_API_BASE_URL="${RENDER_API_BASE_URL%/}"
}
