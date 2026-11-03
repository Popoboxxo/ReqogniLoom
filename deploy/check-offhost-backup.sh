#!/usr/bin/env bash
# Verify the newest OFF-HOST backup before `make wipe` destroys the local volumes
# (plan D3.3, #792 point 13; QR-S22 / KA-D-09).
#
# WHY THIS EXISTS
#   `docker compose ... down -v` removes `postgres_backup_data` together with
#   the database volume, so the only surviving copy is the one the sidecar
#   exported via deploy/docker-compose.offhost.yml. The backup container's exit
#   code 0 is NOT proof: it means the loop iteration returned success, not that
#   the file on the off-host target is complete, current and restorable. This
#   script checks the artifact itself and fails closed.
#
# CHECKS (all on the newest `reqogniloom_*.sql.gz` by mtime)
#   * a file exists,
#   * it is not older than MAX_AGE_SECONDS (default 300) — a stale file is a
#     backup of last week's data, not of the database about to be deleted,
#   * it is larger than 0 bytes — the #1074 empty-dump class,
#   * `gzip -t` accepts the stream — a truncated copy is not a backup,
#   * the first lines contain `PostgreSQL database dump` — proves it is a
#     pg_dump artifact and not, say, an empty gzip of an error message.
#
# Usage: deploy/check-offhost-backup.sh <offhost-dir>
# Exit:  0 verified · 1 any check failed (reason on stderr) · 64 bad usage
set -euo pipefail

MAX_AGE_SECONDS=${MAX_AGE_SECONDS:-300}
DIR=${1:-}

fail() {
  echo "offhost-check: FAILED: $*" >&2
  exit 1
}

case "$DIR" in
  '') echo "usage: $0 <offhost-dir>" >&2; exit 64 ;;
esac

[ -d "$DIR" ] || fail "$DIR is not a directory"

newest=$(ls -1t -- "$DIR"/reqogniloom_*.sql.gz 2>/dev/null | head -n 1 || true)
[ -n "$newest" ] || fail "no reqogniloom_*.sql.gz in $DIR — nothing to restore from"

now=$(date +%s)
mtime=$(stat -c %Y -- "$newest" 2>/dev/null || stat -f %m -- "$newest")
age=$(( now - mtime ))
if [ "$age" -gt "$MAX_AGE_SECONDS" ]; then
  fail "$newest is ${age}s old (max ${MAX_AGE_SECONDS}s) — run a fresh backup first"
fi

size=$(wc -c <"$newest" | tr -d ' ')
if [ "$size" -le 0 ]; then
  fail "$newest is empty (0 bytes)"
fi

gzip -t -- "$newest" 2>/dev/null || fail "$newest is not a valid gzip stream"

# `|| true` is intentional: with `set -o pipefail` a zcat killed by head's
# early exit would otherwise abort the script even when the header matched.
header=$(gzip -dc -- "$newest" 2>/dev/null | head -n 5 || true)
case "$header" in
  *"PostgreSQL database dump"*) ;;
  *) fail "$newest does not look like a pg_dump (no 'PostgreSQL database dump' header)" ;;
esac

echo "offhost-check: OK: $newest (${age}s old, ${size} bytes, gzip valid, pg_dump header present)"
