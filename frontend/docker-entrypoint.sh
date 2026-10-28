#!/bin/sh
# Render nginx config from env, then start nginx in the foreground.
set -eu

PORT="${PORT:-8080}"
# Host only (no scheme) — nginx upstream + proxy_pass https://…
API_UPSTREAM="${API_UPSTREAM:-starserve-api.onrender.com}"
API_UPSTREAM="$(printf '%s' "$API_UPSTREAM" | sed -e 's|^https://||' -e 's|^http://||' -e 's|/.*||')"

# Empty or / → Cloud Run root template. /dashboard → Render mount (quote.*).
SPA_BASE_PATH="${SPA_BASE_PATH:-}"
SPA_BASE_PATH="$(printf '%s' "$SPA_BASE_PATH" | sed -e 's|/*$||')"
TEMPLATE="/etc/nginx/nginx.conf.template"
if [ "$SPA_BASE_PATH" = "/dashboard" ]; then
  TEMPLATE="/etc/nginx/nginx.dashboard.conf.template"
fi

export PORT API_UPSTREAM
if [ "$SPA_BASE_PATH" = "/dashboard" ]; then
  envsubst '${PORT} ${API_UPSTREAM}' \
    < "$TEMPLATE" \
    > /etc/nginx/nginx.conf
else
  envsubst '${PORT} ${API_UPSTREAM}' \
    < "$TEMPLATE" \
    > /etc/nginx/nginx.conf
fi

exec nginx -g 'daemon off;'
