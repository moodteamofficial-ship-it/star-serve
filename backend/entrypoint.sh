#!/bin/sh
# Cloud Run / Render / Compose entrypoint. Secrets are runtime env — never baked into the image.
set -eu

PORT="${PORT:-8000}"

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  python -m alembic upgrade head
fi

# Cloud Run terminates TLS in front of the container. Honour X-Forwarded-* only
# from the platform proxy (see TRUST_X_FORWARDED_FOR in the service env).
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --timeout-keep-alive 5
