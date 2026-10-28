# StarServe frontend — production Vite build served by nginx on Cloud Run.
# Build context: frontend/
# Secrets must NEVER be passed as build-args. Only public VITE_* URLs.

FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.ts tsconfig.json ./
COPY public ./public
COPY src ./src

# Relative /api/v1 — nginx proxies to the API (same-origin cookies).
# VITE_BASE_PATH=/dashboard/ for Render custom-domain mount; default / for Cloud Run.
ARG VITE_APP_NAME="Star Serve"
ARG VITE_DEFAULT_API_ENV=production
ARG VITE_BASE_PATH=/dashboard/
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_API_URL_DEVELOPMENT=/api/v1
ARG VITE_API_URL_STAGING=/api/v1
ARG VITE_API_URL_PRODUCTION=/api/v1
ARG VITE_API_URL_BACKUP=/api/v1
ARG VITE_ALLOW_PRODUCTION_ENV_SWITCH=false
ARG VITE_WEB_URL_STAGING=https://starserve-dashboard-staging-233389149626.europe-west1.run.app
ARG VITE_WEB_URL_PRODUCTION=https://quote.starserveinsuranceagency.com/dashboard
ARG VITE_WEB_URL_DEVELOPMENT=
ARG VITE_WEB_URL_BACKUP=

ENV VITE_APP_NAME=$VITE_APP_NAME \
    VITE_DEFAULT_API_ENV=$VITE_DEFAULT_API_ENV \
    VITE_BASE_PATH=$VITE_BASE_PATH \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_URL_DEVELOPMENT=$VITE_API_URL_DEVELOPMENT \
    VITE_API_URL_STAGING=$VITE_API_URL_STAGING \
    VITE_API_URL_PRODUCTION=$VITE_API_URL_PRODUCTION \
    VITE_API_URL_BACKUP=$VITE_API_URL_BACKUP \
    VITE_ALLOW_PRODUCTION_ENV_SWITCH=$VITE_ALLOW_PRODUCTION_ENV_SWITCH \
    VITE_WEB_URL_STAGING=$VITE_WEB_URL_STAGING \
    VITE_WEB_URL_PRODUCTION=$VITE_WEB_URL_PRODUCTION \
    VITE_WEB_URL_DEVELOPMENT=$VITE_WEB_URL_DEVELOPMENT \
    VITE_WEB_URL_BACKUP=$VITE_WEB_URL_BACKUP

RUN npm run build \
  && find dist -name '*.map' -delete

FROM nginx:1.27-alpine AS runtime

RUN apk add --no-cache curl \
  && rm -rf /usr/share/nginx/html/* \
  && mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp \
  && chown -R nginx:nginx /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp \
             /var/cache/nginx /var/log/nginx /etc/nginx /usr/share/nginx/html

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY nginx.dashboard.conf.template /etc/nginx/nginx.dashboard.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html

RUN chmod +x /docker-entrypoint.sh \
  && chown -R nginx:nginx /usr/share/nginx/html

# Cloud Run / Render inject PORT. API host + SPA mount are runtime-configurable.
# RENDER_SPA_BASE_PATH=/dashboard for quote.* Render images; empty for Cloud Run /.
ARG RENDER_SPA_BASE_PATH=
ARG RENDER_API_UPSTREAM=starserve-api.onrender.com
ENV PORT=8080 \
    API_UPSTREAM=${RENDER_API_UPSTREAM} \
    SPA_BASE_PATH=${RENDER_SPA_BASE_PATH}

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:8080/ready" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
