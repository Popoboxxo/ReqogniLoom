#!/usr/bin/env bash
# ReqogniLoom — regression self-check for the `postgres-backup` sidecar (#1074).
#
# WHAT THIS IS FOR
#   The dump/prune logic of the `postgres-backup` service is INLINED into
#   deploy/docker-compose.yml on purpose (so the service needs no repo file
#   beyond this compose YAML — see that service's header comment). A shell
#   function in a YAML string is exactly the kind of code that silently rots,
#   because nothing ever executes it in CI. This script is that missing
#   executor: it EXTRACTS the real command block out of the compose file (so it
#   can never drift from what actually runs), executes it in a real
#   pgvector/pgvector:pg16 container against a real throwaway Postgres, and
#   asserts the failure semantics that #1074 was about.
#
#   The old bug: `if pg_dump … | gzip > "$outfile"; then echo "wrote …"; fi`
#   reported SUCCESS for a failed dump (a POSIX pipeline's status is that of
#   the LAST command, and gzip exits 0 on empty input) and left the 389-byte
#   empty file behind as if it were a good backup. Case 2 below reproduces
#   exactly that input and asserts it is now rejected.
#
# USAGE
#   deploy/verify-backup-command.sh
#   Requires: bash, docker, python3 with PyYAML. Run from the repository root.
#
# EXIT STATUS
#   0 = all cases behaved as specified. 1 = at least one case regressed.
#
# WHAT IT ASSERTS
#   1. healthy database with data   -> exit 0, one .sql.gz, >= 1 COPY block
#   2. #1074 broken dump (0 COPY
#      blocks, pg_dump exit 0)     -> exit != 0, NO backup file left behind
#   3. pg_dump exits non-zero      -> exit != 0, NO backup file left behind
#   4. empty (freshly wiped) DB,
#      real pg_dump exits 0         -> exit != 0, NO backup file left behind
#
# The good case is also re-read through gunzip, i.e. the compressed artifact on
# the volume is proven to contain table data — that is the restore-verification
# gate docs/DEPLOY_RUNBOOK.md asks the operator to run after every deploy.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/deploy/docker-compose.yml"
PG_IMAGE="pgvector/pgvector:pg16"
NETWORK="reqlo-backup-selftest-$$"
PG_CONTAINER="reqlo-backup-selftest-pg-$$"
WORK="$(mktemp -d)"
STUB_PATH="/stub:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

failures=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; failures=$((failures + 1)); }

cleanup() {
  docker rm -f "${PG_CONTAINER}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT

for tool in docker python3; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "ERROR: ${tool} is required but not on PATH" >&2
    exit 1
  }
done
python3 -c 'import yaml' 2>/dev/null || {
  echo "ERROR: PyYAML is required (pip install pyyaml)" >&2
  exit 1
}

# ── 1. extract the REAL command block from the compose file ──────────────────
# This reproduces what Docker Compose does at parse time: read the YAML, then
# turn every `$$` into a literal `$` (the escape Compose requires so the
# container's shell, not Compose, expands it). Extracting instead of copying is
# the point — the test cannot pass against a block that is not the one that runs.
python3 - "$COMPOSE_FILE" "$WORK/run.sh" <<'PY'
import sys

import yaml

compose = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
raw = compose["services"]["postgres-backup"]["command"][0]
assert "$$" in raw, "no Compose-escaped dollars found — did the block change shape?"
open(sys.argv[2], "w", encoding="utf-8", newline="\n").write(raw.replace("$$", "$"))
PY
cat > "$WORK/wrap.sh" <<'WRAP'
export POSTGRES_HOST=postgres
export POSTGRES_USER=reqogniloom
export POSTGRES_PASSWORD=reqogniloom-selftest
export POSTGRES_DB="${SELFTEST_DB:-reqogniloom}"
exec bash /run.sh
WRAP

echo "ReqogniLoom postgres-backup self-check (#1074)"
echo "compose file: ${COMPOSE_FILE}"
echo

# ── 2. throwaway postgres with a populated database ──────────────────────────
echo "[setup] starting throwaway postgres on network ${NETWORK}"
docker network create "${NETWORK}" >/dev/null
docker run -d --name "${PG_CONTAINER}" --network "${NETWORK}" --network-alias postgres \
  -e POSTGRES_PASSWORD=reqogniloom-selftest \
  -e POSTGRES_DB=reqogniloom -e POSTGRES_USER=reqogniloom \
  "${PG_IMAGE}" >/dev/null
for _ in $(seq 1 60); do
  if docker exec "${PG_CONTAINER}" pg_isready -U reqogniloom -d reqogniloom >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec "${PG_CONTAINER}" psql -U reqogniloom -d reqogniloom -v ON_ERROR_STOP=1 -q <<'SQL' >/dev/null
CREATE TABLE requirement (id serial primary key, title text);
INSERT INTO requirement (title) SELECT 'req-' || g FROM generate_series(1, 200) g;
CREATE TABLE artifact (id serial primary KEY, name text);
CREATE DATABASE freshdb;
SQL

# run_case <name> <backup-subdir> <stub-name|-> -> prints exit code of the block
run_case() {
  local name="$1" subdir="$2" stub="$3" db="${4:-reqogniloom}"
  local dir="${WORK}/${subdir}"
  rm -rf "${dir}"
  mkdir -p "${dir}"
  local args=(
    run --rm --network "${NETWORK}"
    --mount "type=bind,source=${WORK}/run.sh,target=/run.sh,readonly"
    --mount "type=bind,source=${WORK}/wrap.sh,target=/wrap.sh,readonly"
    --mount "type=bind,source=${dir},target=/backups"
    -e BACKUP_ONCE=true
    -e SELFTEST_DB="${db}"
  )
  if [ "${stub}" != "-" ]; then
    args+=(--mount "type=bind,source=${WORK}/stubs/${stub},target=/stub,readonly")
    args+=(-e "PATH=${STUB_PATH}")
  fi
  set +e
  docker "${args[@]}" "${PG_IMAGE}" bash /wrap.sh >"${WORK}/${subdir}.log" 2>&1
  local rc=$?
  set -e
  printf '%s' "${rc}"
}

dump_count() {
  local dir="$1"
  local f
  f=$(ls -1t "${dir}"/reqogniloom_*.sql.gz 2>/dev/null | head -1 || true)
  [ -n "${f}" ] || { echo 0; return; }
  docker run --rm --mount "type=bind,source=${dir},target=/backups,readonly" \
    "${PG_IMAGE}" bash -c \
    "gunzip -c '${f}' | grep -c '^COPY ' || true" 2>/dev/null | tr -d ' \r'
}

# ── CASE 1: healthy database with data ───────────────────────────────────────
echo "[case 1] healthy database with data -> expect exit 0 and a restorable dump"
rc=$(run_case good good -)
if [ "${rc}" -eq 0 ]; then pass "exit 0"; else fail "expected exit 0, got ${rc}"; fi
n=$(dump_count "${WORK}/good")
if [ "${n:-0}" -ge 1 ]; then
  pass "published .sql.gz contains ${n} COPY block(s)"
else
  fail "published dump contains ${n} COPY block(s), need >= 1"
fi

# ── CASE 2: the #1074 regression ─────────────────────────────────────────────
# pg_dump writes the header/footer preamble only (0 COPY blocks) and exits 0 —
# precisely the input the old `pg_dump | gzip > f` check called a success.
echo "[case 2] #1074 broken dump (0 COPY blocks, pg_dump exit 0) -> expect non-zero, no file"
mkdir -p "${WORK}/stubs/empty-dump"
cat > "${WORK}/stubs/empty-dump/pg_dump" <<'STUB'
#!/bin/bash
# Reproduces the #1074 empty dump: header/footer only, exit 0.
out=""
for arg in "$@"; do
  case "$arg" in
    --file=*) out="${arg#--file=}" ;;
  esac
done
{
  printf '%s\n' 'SET statement_timeout = 0;'
  printf '%s\n' '' '--' '-- PostgreSQL database dump' '--'
  printf '%s\n' '' '--' '-- PostgreSQL database dump complete' '--'
} > "$out"
exit 0
STUB
rc=$(run_case emptydump emptydump empty-dump)
if [ "${rc}" -ne 0 ]; then pass "rejected with exit ${rc}"; else fail "reported SUCCESS for an empty dump"; fi
if [ -z "$(ls -1 "${WORK}"/emptydump/reqogniloom_*.sql.gz 2>/dev/null || true)" ]; then
  pass "no empty backup file left behind"
else
  fail "an empty backup file was published — that is the #1074 data-loss trap"
fi

# ── CASE 3: pg_dump fails outright ───────────────────────────────────────────
echo "[case 3] pg_dump exits non-zero -> expect non-zero, no file"
mkdir -p "${WORK}/stubs/failing-dump"
cat > "${WORK}/stubs/failing-dump/pg_dump" <<'STUB'
#!/bin/bash
echo "pg_dump: error: connection to server failed" >&2
exit 1
STUB
rc=$(run_case failingdump failingdump failing-dump)
if [ "${rc}" -ne 0 ]; then pass "rejected with exit ${rc}"; else fail "reported SUCCESS for a failed pg_dump"; fi
if [ -z "$(ls -1 "${WORK}"/failingdump/reqogniloom_*.sql.gz 2>/dev/null || true)" ]; then
  pass "no partial backup file left behind"
else
  fail "a partial backup file was published"
fi

# ── CASE 4: freshly wiped / empty database ───────────────────────────────────
# The deploy window #1074 hit: `migrate` had not populated anything yet, so the
# first dump was structurally empty. Real pg_dump, exit 0, 0 tables.
echo "[case 4] empty (freshly wiped) database -> expect non-zero, no file"
rc=$(run_case freshdb freshdb - freshdb)
if [ "${rc}" -ne 0 ]; then pass "rejected with exit ${rc}"; else fail "reported SUCCESS for an empty database"; fi
if [ -z "$(ls -1 "${WORK}"/freshdb/reqogniloom_*.sql.gz 2>/dev/null || true)" ]; then
  pass "no empty backup file left behind"
else
  fail "an empty backup file was published for an empty database"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "postgres-backup self-check: ALL CASES PASSED"
  exit 0
fi
echo "postgres-backup self-check: ${failures} assertion(s) FAILED — see above" >&2
exit 1
