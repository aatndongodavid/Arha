#!/usr/bin/env bash
# Daily full backup (S-17, NF-07). WAL archiving runs continuously through archive_command (see README).
# Requires WALG_S3_PREFIX, AWS_* and RESTIC_REPOSITORY, RESTIC_PASSWORD in /run/arha/backup.env (SOPS).
set -euo pipefail
source /run/arha/backup.env
docker compose -f /opt/arha/infra/compose/docker-compose.prod.yml exec -T postgres \
  sh -c 'wal-g backup-push "$PGDATA"'
docker compose -f /opt/arha/infra/compose/docker-compose.prod.yml exec -T postgres wal-g delete retain FULL 14 --confirm
restic backup /var/lib/docker/volumes/compose_files/_data --tag arha-files
restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
echo "backup_ok $(date -u +%FT%TZ)"
