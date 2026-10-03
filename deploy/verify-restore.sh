#!/usr/bin/env bash
# ReqogniLoom — atomic restore smoke gate (ADR-012, DATA-01).
#
# WHAT THIS PROVES
#   A backup is only proven by restoring it (ADR-012). This gate:
#     1. extracts the REAL inlined `postgres-backup` command block out of
#        deploy/docker-compose.yml (it cannot pass against a block that is not
#        the one that actually runs),
#     2. runs it against a throwaway SOURCE Postgres that holds 15 tables with
#        known row counts plus a pgvector (vector(3)) column,
#     3. restores the produced `.sql.gz` ATOMICALLY (`psql --single-transaction`,
#        `ON_ERROR_STOP=1`) into a separate throwaway TARGET Postgres,
#     4. asserts 15/15 tables have identical row counts, the vector column
#        survived, and the restore log contains 0 errors,
#     5. injects a deliberate error into a third restore and asserts the single
#        transaction rolled back — no half-restored database is left behind.
#
#   The live database is never contacted. Every Postgres here is a throwaway
#   container on a private network, removed on exit. The dump travels through a
#   disposable named volume, so no host path is ever bind-mounted.
#
# USAGE
#   deploy/verify-restore.sh
#   Requires: bash, docker, python3 or python (stdlib only). Run from anywhere.
#
# EXIT STATUS
#   0 = restore gate passed. 1 = at least one assertion failed.

set -euo pipefail

# Git for Windows' MSYS layer rewrites container paths in argv (e.g. the
# `/backups` in `--mount target=...`) into host paths like `C:/Program Files/...`,
# which Docker rejects. Disable that rewrite; this is a no-op on Linux/CI.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/deploy/docker-compose.yml"

# `--project-directory`/`-f` need a host path the Windows Docker CLI can read;
# with conversion disabled above, translate them explicitly when running under
# Git for Windows. On Linux cygpath does not exist and the path is used as-is.
if command -v cygpath >/dev/null 2>&1; then
  COMPOSE_ARG="$(cygpath -w "${COMPOSE_FILE}")"
  REPO_ARG="$(cygpath -w "${REPO_ROOT}")"
else
  COMPOSE_ARG="${COMPOSE_FILE}"
  REPO_ARG="${REPO_ROOT}"
fi
PG_IMAGE="${RESTORE_SMOKE_PG_IMAGE:-pgvector/pgvector:pg16}"
NET="reqlo-restore-smoke-$$"
SRC="reqlo-restore-smoke-src-$$"
TGT="reqlo-restore-smoke-tgt-$$"
VOL="reqlo-restore-smoke-dump-$$"
WORK="$(mktemp -d)"
EXPECTED_TABLES=15

failures=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; failures=$((failures + 1)); }

cleanup() {
  docker rm -fv "${SRC}" "${TGT}" >/dev/null 2>&1 || true
  docker volume rm -f "${VOL}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker is required but not on PATH" >&2
  exit 1
}
# Prefer a Python that actually runs: on Windows, `command -v python3` finds
# the Microsoft Store alias stub, which only prints an install hint. Probe each
# candidate functionally instead of trusting PATH order.
PYBIN=""
for candidate in python python3 py; do
  if command -v "${candidate}" >/dev/null 2>&1 \
    && "${candidate}" -c 'import json' >/dev/null 2>&1; then
    PYBIN="${candidate}"
    break
  fi
done
if [ -z "${PYBIN}" ]; then
  echo "ERROR: a working python3 or python is required but was not found on PATH" >&2
  exit 1
fi

wait_ready() {
  local container="$1" i
  for i in $(seq 1 60); do
    if docker exec "${container}" pg_isready -U smoke -d smoke >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ${container} did not become ready within 120s" >&2
  return 1
}

# Per-table row count, one `table=count` line per user table, sorted.
COUNT_SQL="SELECT relname || '=' || (xpath('/row/count/text()', query_to_xml('SELECT count(*) AS count FROM ' || quote_ident(relname), false, true, '')))[1]::text FROM pg_stat_user_tables ORDER BY relname;"

echo "ReqogniLoom atomic restore smoke (ADR-012)"
echo "compose file: ${COMPOSE_FILE}"
echo

# ── 1. extract the REAL sidecar command block from the compose file ──────────
# Same idea as deploy/verify-backup-command.sh: read the resolved Compose model
# (so `$$` escaping is handled the way Compose handles it), take the actual
# command the `postgres-backup` service runs, and execute THAT.
# stdout is redirected by the caller (MSYS-style path), so the script never has
# to open a Git-for-Windows path from native Python.
"${PYBIN}" - "${COMPOSE_ARG}" "${REPO_ARG}" >"${WORK}/backup_run.sh" <<'PY'
import json
import subprocess
import sys

compose_file, repo_root = sys.argv[1], sys.argv[2]
raw = subprocess.check_output(
    [
        "docker", "compose", "-f", compose_file,
        "--project-directory", repo_root,
        "config", "--format", "json",
    ],
    text=True,
)
compose = json.loads(raw)
command = compose["services"]["postgres-backup"]["command"]
if isinstance(command, list):
    command = "\n".join(command)
assert "$$" in command, "no Compose-escaped dollars found — did the block change shape?"
# Bytes, not text: Windows Python's text stdout would turn every \n into \r\n
# and the POSIX script would die on `$'\r'`.
sys.stdout.buffer.write(command.replace("$$", "$").replace("\r\n", "\n").encode("utf-8"))
PY

# ── 2. isolated SOURCE and TARGET Postgres ───────────────────────────────────
echo "[setup] private network ${NET}, throwaway source + target Postgres"
docker network create "${NET}" >/dev/null
docker volume create "${VOL}" >/dev/null
docker run -d --name "${SRC}" --network "${NET}" --network-alias source \
  -e POSTGRES_DB=smoke -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD=smoke \
  "${PG_IMAGE}" >/dev/null
docker run -d --name "${TGT}" --network "${NET}" --network-alias target \
  -e POSTGRES_DB=smoke -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD=smoke \
  "${PG_IMAGE}" >/dev/null
wait_ready "${SRC}"
wait_ready "${TGT}"

# 15 tables with distinct, deterministic row counts; smoke_t15 is empty on
# purpose (pg_dump emits a COPY block for empty tables too, and the restore must
# reproduce the empty table as well). All tables carry a pgvector column.
docker exec -i "${SRC}" psql -U smoke -d smoke -v ON_ERROR_STOP=1 -q <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
DO $$
DECLARE i int;
BEGIN
  FOR i IN 1..15 LOOP
    EXECUTE format(
      'CREATE TABLE smoke_t%s (id serial PRIMARY KEY, name text, embedding vector(3))',
      lpad(i::text, 2, '0'));
    EXECUTE format(
      'INSERT INTO smoke_t%s (name, embedding) SELECT %L || g, ''[1,2,3]''::vector FROM generate_series(1, %s) g',
      lpad(i::text, 2, '0'), 'row', CASE WHEN i = 15 THEN 0 ELSE i * 100 END);
  END LOOP;
END $$;
SQL

# ── 3. run the real sidecar block against the source ─────────────────────────
echo "[backup] running the extracted postgres-backup command block (BACKUP_ONCE)"
set +e
docker run --rm -i --network "${NET}" \
  --mount "type=volume,source=${VOL},target=/backups" \
  -e POSTGRES_HOST=source -e POSTGRES_DB=smoke \
  -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD=smoke \
  -e BACKUP_DIR=/backups -e BACKUP_ONCE=true -e BACKUP_INITIAL_DELAY=0 \
  -e BACKUP_RETENTION=7 -e BACKUP_INTERVAL=21600 \
  -e BACKUP_MIN_COPY_BLOCKS=1 -e BACKUP_MAX_CONSECUTIVE_FAILURES=3 \
  "${PG_IMAGE}" bash -s <"${WORK}/backup_run.sh" >"${WORK}/backup.log" 2>&1
backup_rc=$?
set -e
cat "${WORK}/backup.log"
if [ "${backup_rc}" -eq 0 ]; then
  pass "sidecar command block exited 0"
else
  fail "sidecar command block exited ${backup_rc}"
fi

dump_name="$(docker run --rm --mount "type=volume,source=${VOL},target=/backups" \
  "${PG_IMAGE}" bash -c 'ls -1t /backups/reqogniloom_*.sql.gz 2>/dev/null | head -1')"
if [ -n "${dump_name}" ]; then
  pass "published dump: $(basename "${dump_name}")"
else
  fail "no .sql.gz dump was published"
fi

copy_blocks="$(docker run --rm --mount "type=volume,source=${VOL},target=/backups,readonly" \
  "${PG_IMAGE}" bash -c \
  'gunzip -c "$(ls -1t /backups/reqogniloom_*.sql.gz | head -1)" | grep -c "^COPY " || true' \
  | tr -d ' \r')"
if [ "${copy_blocks:-0}" -ge "${EXPECTED_TABLES}" ]; then
  pass "dump contains ${copy_blocks} COPY block(s) (>= ${EXPECTED_TABLES})"
else
  fail "dump contains ${copy_blocks} COPY block(s), need >= ${EXPECTED_TABLES}"
fi

# ── 4. atomic restore into the isolated target (one transaction) ─────────────
cat > "${WORK}/restore.sh" <<'RS'
set -euo pipefail
f=$(ls -1t /backups/reqogniloom_*.sql.gz | head -1)
echo "[restore] dump=${f}"
gzip -t "${f}"
gunzip -c "${f}" | psql -h target -U smoke -d smoke --single-transaction -v ON_ERROR_STOP=1 -q -o /dev/null
echo "[restore] committed"
RS

echo "[restore] atomic restore into isolated target (single transaction)"
set +e
docker run --rm -i --network "${NET}" \
  --mount "type=volume,source=${VOL},target=/backups,readonly" \
  -e PGPASSWORD=smoke "${PG_IMAGE}" bash -s <"${WORK}/restore.sh" \
  >"${WORK}/restore.log" 2>&1
restore_rc=$?
set -e
cat "${WORK}/restore.log"
if [ "${restore_rc}" -eq 0 ]; then
  pass "restore exited 0"
else
  fail "restore exited ${restore_rc}"
fi

# Match PostgreSQL's own error lines ('psql:...: ERROR:' / 'ERROR:'), not a
# table name that happens to contain "error".
error_lines="$(grep -cE '(^| )(ERROR|FATAL|PANIC):' "${WORK}/restore.log" || true)"
if [ "${error_lines}" -eq 0 ]; then
  pass "restore log: 0 error line(s)"
else
  fail "restore log: ${error_lines} error line(s)"
fi

# ── 5. row-count comparison: source vs. restored target ──────────────────────
src_counts="$(docker exec "${SRC}" psql -U smoke -d smoke -tA -c "${COUNT_SQL}")"
tgt_counts="$(docker exec "${TGT}" psql -U smoke -d smoke -tA -c "${COUNT_SQL}")"
src_tables="$(printf '%s\n' "${src_counts}" | grep -c . || true)"
tgt_tables="$(printf '%s\n' "${tgt_counts}" | grep -c . || true)"

if [ "${src_tables}" -eq "${EXPECTED_TABLES}" ]; then
  pass "source holds ${src_tables}/${EXPECTED_TABLES} tables"
else
  fail "source holds ${src_tables} tables, expected ${EXPECTED_TABLES}"
fi

if [ "${tgt_tables}" -eq "${EXPECTED_TABLES}" ]; then
  pass "restored target holds ${tgt_tables}/${EXPECTED_TABLES} tables"
else
  fail "restored target holds ${tgt_tables} tables, expected ${EXPECTED_TABLES}"
fi

if [ "${src_counts}" = "${tgt_counts}" ]; then
  pass "all ${EXPECTED_TABLES}/${EXPECTED_TABLES} table row counts are identical"
else
  fail "row counts differ — source vs. restored target:"
  diff <(printf '%s\n' "${src_counts}") <(printf '%s\n' "${tgt_counts}") || true
fi

vector_type="$(docker exec "${TGT}" psql -U smoke -d smoke -tA -c \
  "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid WHERE c.relname = 'smoke_t01' AND a.attname = 'embedding';" \
  | tr -d ' \r')"
if [ "${vector_type}" = "vector(3)" ]; then
  pass "pgvector column restored as vector(3)"
else
  fail "pgvector column restored as '${vector_type}', expected vector(3)"
fi

# ── 6. atomicity: an injected error must leave NO half-restored database ─────
echo "[atomicity] deliberate error inside the single transaction -> expect rollback"
docker exec "${TGT}" psql -U smoke -d postgres -q -c 'CREATE DATABASE smoke_fail;' >/dev/null
cat > "${WORK}/restore_fail.sh" <<'RS'
set -euo pipefail
f=$(ls -1t /backups/reqogniloom_*.sql.gz | head -1)
{ gunzip -c "${f}"; printf '\nSELECT 1 / 0;\n'; } \
  | psql -h target -U smoke -d smoke_fail --single-transaction -v ON_ERROR_STOP=1 -q -o /dev/null
RS
set +e
docker run --rm -i --network "${NET}" \
  --mount "type=volume,source=${VOL},target=/backups,readonly" \
  -e PGPASSWORD=smoke "${PG_IMAGE}" bash -s <"${WORK}/restore_fail.sh" \
  >"${WORK}/restore_fail.log" 2>&1
fail_rc=$?
set -e
if [ "${fail_rc}" -ne 0 ]; then
  pass "injected error aborted the restore (exit ${fail_rc})"
else
  fail "injected error did NOT abort the restore"
fi

fail_tables="$(docker exec "${TGT}" psql -U smoke -d smoke_fail -tA -c \
  "SELECT count(*) FROM pg_stat_user_tables;" | tr -d ' \r')"
if [ "${fail_tables}" = "0" ]; then
  pass "failed restore left 0 tables — transaction rolled back, no half-restored DB"
else
  fail "failed restore left ${fail_tables} table(s) — the database is half-restored"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "atomic restore smoke: ALL CASES PASSED (${EXPECTED_TABLES}/${EXPECTED_TABLES} tables, 0 errors, rollback verified)"
  exit 0
fi
echo "atomic restore smoke: ${failures} assertion(s) FAILED — see above" >&2
exit 1
