#!/bin/sh
# ---------------------------------------------------------------------------
# Pre-install the pgvector `vector` extension as the cluster superuser.
#
# Why this exists
# ---------------
# `CREATE EXTENSION vector` requires superuser rights (the extension is not
# marked "trusted" in pgvector for pg16). At runtime the application connects
# as the least-privilege, NOSUPERUSER role DB_APP_USER (default
# `reqogniloom_app`, see persistence/migrations/0048_app_role.py,
# REQ-L2-PL-010). Any code path that reaches `CREATE EXTENSION` under that
# role fails with:
#
#   ProgrammingError: permission denied to create extension "vector"
#   HINT: Must be superuser to create this extension.
#
# The affected path is persistence/migrations/0024_requirement_embedding.py,
# which runs `CREATE EXTENSION IF NOT EXISTS vector;` — e.g. when pytest
# builds a fresh `test_<db>` database (`pytest --create-db`).
#
# Fix: install the extension up front, as the superuser, in BOTH
#   1. template1 — every database created afterwards (including Django's
#      ephemeral `test_*` databases, which `CREATE DATABASE` clones from
#      template1 because Django does not pass an explicit TEMPLATE) inherits
#      the extension automatically; and
#   2. $POSTGRES_DB — the application database itself.
#
# With the extension already present, `CREATE EXTENSION IF NOT EXISTS vector`
# is a no-op that only emits a NOTICE: PostgreSQL short-circuits on the
# existence check BEFORE the superuser privilege check, so migration 0024
# succeeds even under the restricted app role.
#
# This script is executed by the official Postgres entrypoint from
# /docker-entrypoint-initdb.d/ as $POSTGRES_USER (a superuser) — but ONLY on a
# completely empty data directory. For an ALREADY initialised volume, apply
# the same statements once by hand:
#
#   docker compose exec -T postgres \
#     psql -U "$DB_USER" -d template1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
#   docker compose exec -T postgres \
#     psql -U "$DB_USER" -d "$DB_NAME" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
#
# (or run scripts/enable_pgvector.sh, which does exactly that).
# ---------------------------------------------------------------------------
set -e

for db in template1 "${POSTGRES_DB:-postgres}"; do
    echo "[initdb] installing pgvector 'vector' extension into database: ${db}"
    psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${db}" \
        -c 'CREATE EXTENSION IF NOT EXISTS vector;'
done
