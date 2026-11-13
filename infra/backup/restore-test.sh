#!/usr/bin/env bash
# Monthly restore test on the staging server (NF-08). Writes a timed report. Target: under 4 hours.
set -euo pipefail
source /run/arha/backup.env
START=$(date +%s)
WORK=$(mktemp -d /var/lib/arha/restore-test.XXXX)
wal-g backup-fetch "$WORK/pgdata" LATEST
touch "$WORK/pgdata/recovery.signal"
docker run -d --name arha-restore-test -v "$WORK/pgdata:/var/lib/postgresql/data" postgres:16-alpine >/dev/null
for i in $(seq 1 120); do docker exec arha-restore-test pg_isready -q && break; sleep 5; done
ROWS=$(docker exec arha-restore-test psql -U postgres -d arha -tAc "select count(*) from organizations")
restic restore latest --tag arha-files --target "$WORK/files" >/dev/null
docker rm -f arha-restore-test >/dev/null
ELAPSED=$(( $(date +%s) - START ))
mkdir -p /var/lib/arha/reports
echo "$(date -u +%FT%TZ) restore_ok organizations=$ROWS seconds=$ELAPSED" | tee -a /var/lib/arha/reports/restore-tests.log
rm -rf "$WORK"
