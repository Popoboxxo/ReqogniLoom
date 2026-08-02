#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Retro-fit the pgvector `vector` extension into an EXISTING Postgres volume.
#
# docker/postgres/initdb/10-pgvector.sh only runs when the Postgres data
# directory is empty (official image behaviour). Development machines that
# were set up before that script existed therefore still lack the extension in
# `template1`, and `pytest --create-db` fails while running
# persistence/migrations/0024_requirement_embedding.py with:
#
#   permission denied to create extension "vector"
#
# because the app connects as the NOSUPERUSER role (REQ-L2-PL-010).
#
# This script performs the same superuser bootstrap idempotently against a
# RUNNING compose stack — no data is touched, no volume is recreated.
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
