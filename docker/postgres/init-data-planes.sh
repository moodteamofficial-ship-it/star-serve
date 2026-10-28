#!/bin/bash
# Create isolated staging + live + backup databases (separate DBs, not a column).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE starserve_staging;
  CREATE DATABASE starserve_live;
  CREATE DATABASE starserve_backup;
EOSQL
