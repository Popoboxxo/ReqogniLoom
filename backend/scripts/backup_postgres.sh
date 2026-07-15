#!/bin/sh
# REQ-102: PostgreSQL backup strategy for the postgres_data volume.
#
# Creates a timestamped, gzip-compressed pg_dump of the ReqFlow database and
# retains only the most recent backups. Designed to run inside a lightweight
# postgres:16-alpine sidecar container (see docker-compose.yml postgres-backup).
#
# Required environment variables:
#   POSTGRES_HOST      — database host (default: postgres)
#   POSTGRES_DB        — database name
#   POSTGRES_USER      — database user
#   POSTGRES_PASSWORD  — database password
# Optional:
#   BACKUP_DIR         — output directory (default: /backups)
#   BACKUP_RETENTION   — number of backups to keep (default: 7)
set -e
set -u

POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION="${BACKUP_RETENTION:-7}"

timestamp="$(date +%Y%m%d_%H%M%S)"
outfile="${BACKUP_DIR}/reqflow_${timestamp}.sql.gz"

mkdir -p "${BACKUP_DIR}"

# pg_dump reads the password from PGPASSWORD; avoid interactive prompt.
export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "[backup] dumping ${POSTGRES_DB} from ${POSTGRES_HOST} to ${outfile}"
pg_dump \
  --host="${POSTGRES_HOST}" \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --no-owner \
  --no-privileges \
  | gzip > "${outfile}"

echo "[backup] wrote $(du -h "${outfile}" | cut -f1) to ${outfile}"

# Retention: keep only the newest BACKUP_RETENTION dumps, delete the rest.
ls -1t "${BACKUP_DIR}"/reqflow_*.sql.gz 2>/dev/null \
  | tail -n "+$((BACKUP_RETENTION + 1))" \
  | while read -r old; do
      echo "[backup] pruning old backup ${old}"
      rm -f "${old}"
    done

echo "[backup] done"
