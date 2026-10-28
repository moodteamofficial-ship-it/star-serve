#!/usr/bin/env bash
# Generate fresh production security secrets for Render + Cloud Run (Secret Manager).
# Updates v1.0/.env (gitignored). Never prints secret values.
#
#   ./scripts/gcp/rotate-production-secrets.sh
#   UPLOAD_GCP=true ./scripts/gcp/rotate-production-secrets.sh   # also Secret Manager
#   ROTATE_JWT=true ./scripts/gcp/rotate-production-secrets.sh # new RS256 pair for prod
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

UPLOAD_GCP="${UPLOAD_GCP:-true}"
ROTATE_JWT="${ROTATE_JWT:-true}"
PREFIX="$(secret_prefix production)"

[ -f "${ENV_FILE}" ] || die "Missing ${ENV_FILE}"

log "Generating production secrets (values not logged)"

export ENV_FILE BACKEND_DIR ROTATE_JWT
python3 <<'PY'
import os
import re
import secrets
import subprocess
from pathlib import Path

env_file = Path(os.environ["ENV_FILE"])
backend = Path(os.environ["BACKEND_DIR"])
rotate_jwt = os.environ.get("ROTATE_JWT", "true").lower() == "true"

updates = {
    "CSRF_SECRET": secrets.token_urlsafe(48),
    "ENCRYPTION_KEY": secrets.token_urlsafe(48),
    "GUEST_SIGNING_SECRET": secrets.token_urlsafe(48),
    "MPESA_WEBHOOK_SECRET": secrets.token_urlsafe(48),
    "BIRDVIEW_WEBHOOK_SECRET": secrets.token_urlsafe(48),
}

if rotate_jwt:
    secrets_dir = backend / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    priv = secrets_dir / "prod_jwt_private.pem"
    pub = secrets_dir / "prod_jwt_public.pem"
    subprocess.run(
        ["openssl", "genrsa", "-out", str(priv), "2048"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(priv), "-pubout", "-out", str(pub)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.chmod(priv, 0o600)
    updates["JWT_PRIVATE_KEY_PATH"] = "secrets/prod_jwt_private.pem"
    updates["JWT_PUBLIC_KEY_PATH"] = "secrets/prod_jwt_public.pem"

lines = env_file.read_text(encoding="utf-8").splitlines()
seen = set()
out: list[str] = []
key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")

for line in lines:
    m = key_re.match(line.strip())
    if m and m.group(1) in updates:
        key = m.group(1)
        val = updates[key]
        if " " in val or "$" in val:
            out.append(f'{key}="{val}"')
        else:
            out.append(f"{key}={val}")
        seen.add(key)
    else:
        out.append(line)

for key, val in updates.items():
    if key not in seen:
        if " " in val or "$" in val:
            out.append(f'{key}="{val}"')
        else:
            out.append(f"{key}={val}")

env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
print("[gcp] Updated .env keys:", ", ".join(sorted(updates)), flush=True)
PY

if [ "${UPLOAD_GCP}" != "true" ]; then
  log "Skipping Secret Manager (UPLOAD_GCP=false)"
  log "Render: export RENDER_API_KEY=... && ./scripts/render/apply-production.sh"
  exit 0
fi

gcp_secrets_ok=true

upload_env_secret() {
  local suffix="$1"
  local env_key="$2"
  local secret_name="${PREFIX}-${suffix}"
  local value
  value="$(python3 - "$ENV_FILE" "$env_key" <<'PY'
import sys
from pathlib import Path
path, key = sys.argv[1], sys.argv[2]
for line in Path(path).read_text(encoding="utf-8").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    name, val = raw.split("=", 1)
    if name == key:
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        print(val, end="")
        break
PY
)"
  [ -n "${value}" ] || die "Empty ${env_key} after rotate"
  if ! gcloud secrets describe "${secret_name}" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    if ! gcloud secrets create "${secret_name}" \
      --replication-policy=automatic \
      --project="${GCP_PROJECT}" >/dev/null 2>&1; then
      gcp_secrets_ok=false
      log "Secret Manager unavailable (billing?) — .env updated; use Render apply-production.sh"
      return 0
    fi
  fi
  if ! printf '%s' "${value}" | gcloud secrets versions add "${secret_name}" \
    --data-file=- \
    --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    gcp_secrets_ok=false
    log "Could not upload ${secret_name} — .env still has the new value for Render"
    return 0
  fi
  local sa
  sa="$(runtime_sa production)"
  gcloud secrets add-iam-policy-binding "${secret_name}" \
    --member="serviceAccount:${sa}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${GCP_PROJECT}" \
    --quiet >/dev/null 2>&1 || true
  log "Secret Manager new version: ${secret_name}"
}

upload_env_secret csrf-secret CSRF_SECRET
upload_env_secret encryption-key ENCRYPTION_KEY
upload_env_secret guest-signing-secret GUEST_SIGNING_SECRET
upload_env_secret mpesa-webhook-secret MPESA_WEBHOOK_SECRET
upload_env_secret birdview-webhook-secret BIRDVIEW_WEBHOOK_SECRET

if [ "${ROTATE_JWT}" = "true" ]; then
  priv="${BACKEND_DIR}/secrets/prod_jwt_private.pem"
  pub="${BACKEND_DIR}/secrets/prod_jwt_public.pem"
  for pair in jwt-private:"${priv}" jwt-public:"${pub}"; do
    suffix="${pair%%:*}"
    path="${pair#*:}"
    secret_name="${PREFIX}-${suffix}"
    if ! gcloud secrets describe "${secret_name}" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
      gcloud secrets create "${secret_name}" \
        --replication-policy=automatic \
        --project="${GCP_PROJECT}" >/dev/null
    fi
    if ! gcloud secrets versions add "${secret_name}" \
      --data-file="${path}" \
      --project="${GCP_PROJECT}" >/dev/null 2>&1; then
      gcp_secrets_ok=false
      log "Could not upload ${secret_name} — PEM files remain on disk for Render sync"
      continue
    fi
    sa="$(runtime_sa production)"
    gcloud secrets add-iam-policy-binding "${secret_name}" \
      --member="serviceAccount:${sa}" \
      --role="roles/secretmanager.secretAccessor" \
      --project="${GCP_PROJECT}" \
      --quiet >/dev/null 2>&1 || true
    log "Secret Manager new version: ${secret_name} (from file)"
  done
fi

log "Rotate complete — run ./scripts/gcp/release.sh production then ./scripts/render/apply-production.sh"
