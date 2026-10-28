#!/usr/bin/env bash
# Thin wrapper around Render REST API. Requires RENDER_API_KEY in the environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

[ -n "${RENDER_API_KEY:-}" ] || render_die "Set RENDER_API_KEY (Render Dashboard → Account Settings → API Keys). Never commit it."

render_curl() {
  curl -sS -H "Authorization: Bearer ${RENDER_API_KEY}" -H "Accept: application/json" "$@"
}

render_api_service_id() {
  local name="$1"
  render_curl "https://api.render.com/v1/services?limit=100" \
    | python3 -c 'import json,sys; name=sys.argv[1]; data=json.load(sys.stdin)
for row in data:
 svc=row.get("service") or row
 if svc.get("name")==name:
  print(svc["id"]); sys.exit(0)
sys.exit(1)' "$name"
}
