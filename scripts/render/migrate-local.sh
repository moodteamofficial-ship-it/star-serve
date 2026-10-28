#!/usr/bin/env bash
# Alembic upgrade using local image + DATABASE_URL from v1.0/.env (no GCP Secret Manager).
#
# Usage:
#   ./scripts/render/build-api-local.sh
#   ./scripts/render/migrate-local.sh
#   ./scripts/render/migrate-local.sh myimage:tag
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

IMAGE="${1:-starserve-api:local}"
[ -f "${ENV_FILE}" ] || render_die "Missing ${ENV_FILE}"

DATABASE_URL="$(python3 - "${ENV_FILE}" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
for key in ("DATABASE_URL_PRODUCTION", "DATABASE_URL"):
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, val = raw.split("=", 1)
        if name != key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if val:
            print(val)
            raise SystemExit(0)
raise SystemExit("No DATABASE_URL or DATABASE_URL_PRODUCTION in .env")
PY
)"

render_log "Running alembic upgrade head (${IMAGE})"
docker run --rm \
  --env-file "${ENV_FILE}" \
  -e "APP_ENV=production" \
  -e "APP_DEBUG=false" \
  -e "DB_PROVIDER=supabase" \
  -e "DB_SSL_MODE=require" \
  -e "DB_NULL_POOL=true" \
  -e "LOG_JSON=true" \
  -e "DATABASE_URL=${DATABASE_URL}" \
  --entrypoint python \
  "${IMAGE}" \
  -m alembic upgrade head

render_log "Migrations complete"
