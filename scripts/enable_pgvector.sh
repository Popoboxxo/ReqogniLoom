#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Retro-fit the pgvector `vector` extension into an EXISTING Postgres volume.
#
# Normally nothing needs this: `migrate` always connects as the Postgres
# superuser and persistence/migrations/0024_requirement_embedding.py already
# runs `CREATE EXTENSION IF NOT EXISTS vector` on first migrate (see
# deploy/docker-compose.yml's `postgres` service comment). This script is only
# for a database that predates that migration ever running successfully — e.g.
# one created against an old deployment that relied on a since-removed
# `docker-entrypoint-initdb.d` bind-mount and somehow still lacks the
# extension. If you hit `permission denied to create extension "vector"`
# anywhere (that error means the connecting role is DB_APP_USER, the
# least-privilege NOSUPERUSER role — REQ-L2-PL-010 — not the superuser),
# this script performs the same bootstrap idempotently against a RUNNING
# compose stack — no data is touched, no volume is recreated.
#
# Usage:  ./scripts/enable_pgvector.sh
# Env:    DB_USER / DB_NAME are read from .env when present (defaults below).
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "${ROOT_DIR}/.env" ]; then
    # shellcheck disable=SC1091
    set -a && . "${ROOT_DIR}/.env" && set +a
fi

DB_USER="${DB_USER:-reqogniloom}"
DB_NAME="${DB_NAME:-reqogniloom}"
COMPOSE="${COMPOSE:-docker compose}"

for db in template1 "${DB_NAME}"; do
    echo "[enable_pgvector] installing 'vector' extension into database: ${db}"
    ${COMPOSE} exec -T postgres \
        psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${db}" \
        -c 'CREATE EXTENSION IF NOT EXISTS vector;'
done

echo "[enable_pgvector] done — new databases cloned from template1 now ship the extension."
