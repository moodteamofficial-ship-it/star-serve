#!/usr/bin/env bash
# Start the local FastAPI backend for localhost SPA testing (Vite → :8000).
# Usage (from v1.0/):
#   ./scripts/dev-backend.sh
#   ./scripts/dev-backend.sh --migrate   # also alembic upgrade head
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}/backend"

if [ ! -d .venv ]; then
  echo "Missing backend/.venv — create it with: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

export JWT_PRIVATE_KEY_PATH="${JWT_PRIVATE_KEY_PATH:-./secrets/dev_jwt_private.pem}"
export JWT_PUBLIC_KEY_PATH="${JWT_PUBLIC_KEY_PATH:-./secrets/dev_jwt_public.pem}"

if [ ! -f "${JWT_PRIVATE_KEY_PATH}" ] || [ ! -f "${JWT_PUBLIC_KEY_PATH}" ]; then
  mkdir -p secrets
  openssl genrsa -out secrets/dev_jwt_private.pem 2048
  openssl rsa -in secrets/dev_jwt_private.pem -pubout -out secrets/dev_jwt_public.pem
  echo "Generated ${JWT_PRIVATE_KEY_PATH} / ${JWT_PUBLIC_KEY_PATH}"
fi

if [ "${1:-}" = "--migrate" ]; then
  echo "Running alembic upgrade head…"
  alembic upgrade head
fi

PORT="${PORT:-8000}"
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use:"
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN || true
  echo
  echo "Free it (only if it is not a process you need), then retry:"
  echo "  lsof -tiTCP:${PORT} -sTCP:LISTEN | xargs kill"
  echo "Or run on another port:"
  echo "  PORT=8001 DEV_PROXY_LOCAL=http://127.0.0.1:8001 ./scripts/dev-backend.sh"
  exit 1
fi

echo "Local API → http://127.0.0.1:${PORT}  (SPA Dev proxies /api here)"
echo "Pair with:  cd frontend && npm run dev"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT}"
