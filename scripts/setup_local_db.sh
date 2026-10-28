#!/usr/bin/env bash
# Bootstrap local Homebrew Postgres + Redis for Star Serve (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_USER="${STARSERVE_DB_USER:-starserve}"
DB_PASS="${STARSERVE_DB_PASS:-starserve}"
DB_NAME="${STARSERVE_DB_NAME:-starserve}"

echo "Ensuring PostgreSQL role/database (${DB_USER}/${DB_NAME})..."
psql -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\\gexec
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
\\c ${DB_NAME}
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER SCHEMA public OWNER TO ${DB_USER};
SQL

if ! command -v redis-cli >/dev/null 2>&1 && [[ -x /opt/homebrew/opt/redis/bin/redis-cli ]]; then
  export PATH="/opt/homebrew/opt/redis/bin:$PATH"
fi

if ! redis-cli ping >/dev/null 2>&1; then
  echo "Starting Redis via Homebrew..."
  brew list redis >/dev/null 2>&1 || brew install redis
  brew services start redis
  sleep 1
fi

redis-cli ping
echo "OK: Postgres role/db ready and Redis responding."
echo "Next:"
echo "  cd ${ROOT}/backend && source .venv/bin/activate"
echo "  export JWT_PRIVATE_KEY_PATH=./secrets/dev_jwt_private.pem JWT_PUBLIC_KEY_PATH=./secrets/dev_jwt_public.pem"
echo "  alembic upgrade head && python scripts/seed_phase1.py && python scripts/seed_phase2.py"
echo "  uvicorn app.main:app --reload --port 8000"
