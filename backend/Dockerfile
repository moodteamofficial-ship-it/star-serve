# syntax=docker/dockerfile:1.7
# Production image for Cloud Run / Render. Secrets are runtime-injected — never COPY .env or PEMs.

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

RUN groupadd --system starserve \
    && useradd --system --gid starserve --home /app starserve

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY entrypoint.sh ./entrypoint.sh

RUN mkdir -p /app/data/certificates /app/data/email-pdfs /app/data/claims/documents \
    && chmod 0755 /app/entrypoint.sh \
    && chown -R starserve:starserve /app

USER starserve

EXPOSE 8000

# Compose / local image health; Cloud Run uses startup/liveness probes instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'))" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
