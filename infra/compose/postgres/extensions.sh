#!/bin/sh
# Extensions need a superuser; migrations run as arha_owner.
set -e
for db in arha arha_test; do
  psql -v ON_ERROR_STOP=1 -U postgres -d "$db" -c "CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pg_trgm; ALTER SCHEMA public OWNER TO arha_owner;"
done
