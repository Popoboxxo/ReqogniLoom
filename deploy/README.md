# ReqogniLoom — Deployment Examples

This directory holds the reference Docker Compose deployments for ReqogniLoom. Pick one file (or
combination), run it from the **repository root**, and the stack comes up.

| File | Purpose | Use when |
|---|---|---|
| `docker-compose.yml` | Full stack: postgres, postgres-backup, redis, backend, migrate, celery, celery-beat, frontend. Optional Honcho memory backend (`honcho-postgres`/`honcho-redis`/`honcho-migrate`/`honcho`) gated behind the `honcho` Compose profile — costs nothing unless activated. | Production, or any deployment that needs async task processing and scheduled backups. **Default choice.** |
| `docker-compose.minimal.yml` | Slim stack: postgres, redis, backend, migrate, frontend only. No Celery worker/beat, no backup sidecar, no Honcho. | Quick try-out, or a small install that doesn't need async tasks (webhooks, long-running LLM calls, memory consolidation silently never run — see the file's own header comment) or automated backups. |
| `docker-compose.override.yml` | Dev overlay: hot-reload (`uvicorn --reload` / Vite dev server), source bind-mounts, weaker defaults. Auto-applied by `make up` (see repo-root `Makefile`). | Local development against the full stack only — **not** compatible with `docker-compose.minimal.yml` (it re-adds `celery`/`celery-beat`, defeating the point of minimal). |
| `docker-compose.override.example.yml` | Documentation only — a commented-out template for optional local services (e.g. Ollama). **Never read by Compose itself** (wrong filename on purpose); copy it to `docker-compose.override.yml` and uncomment what you need. | Reference when wiring up an optional local service. |

## Required flag: `--project-directory .`

These compose files do **not** live in the repository root. Every direct `docker compose`
invocation against them MUST include `--project-directory .`, run from the repo root, in
addition to `-f`. Do not omit this flag — it is not optional convenience, it is required
for the stack to work correctly:

- Without it, Compose looks for `.env` relative to `deploy/` instead of the repo root, so none
  of your configured secrets/overrides are picked up.
- Without it, every relative bind-mount in these files (`./backend`, `./docker/postgres/initdb`,
  `./docs`, `./backend/scripts/backup_postgres.sh`) resolves relative to `deploy/` instead of the
  repo root, and the container either fails to start or mounts an empty/wrong directory.
- `deploy/docker-compose.override.yml` does **not** auto-merge the way a root-level
  `docker-compose.override.yml` would — Compose's automatic override discovery only triggers
  when both files sit in the same directory and no `-f` flag is passed. Once `-f` is used (which
  it must be here, since the files are not in the default location), the override has to be
  passed explicitly with its own `-f`, every time.

The canonical command shape is always:

```bash
docker compose -f deploy/docker-compose.yml [-f deploy/docker-compose.override.yml] [--profile honcho] --project-directory . <subcommand> [args...]
```

The repo-root `Makefile` wraps the common cases (`make up`, `make down`, `make minimal`,
`make minimal-down`, `make honcho`, `make build`) so day-to-day use does not require typing the
full invocation — but the flags above are what those targets expand to, and are required if you
call `docker compose` directly instead.

## Full stack — step by step

1. From the repository root:
   ```bash
   cp .env.example .env
   ```
2. Fill in the required secrets in `.env` — `SECRET_KEY`, `AUTH_JWT_SECRET`,
   `FIELD_ENCRYPTION_KEY`, `DB_PASSWORD`, `DB_APP_PASSWORD` have no default and the stack refuses
   to start without them. `SYSTEM_ADMIN_PASSWORD` is different: leaving it empty does **not**
   abort the stack, it only skips auto-provisioning the admin user (logged, not fatal — see
   `backend/application/self_init.py`); set it if you want an admin account created automatically
   on first start. (See `.env.example` for the full annotated list and generation commands.)
3. Start the stack:
   ```bash
   docker compose -f deploy/docker-compose.yml --project-directory . up -d
   ```
   For local development with hot-reload instead, use `make up` (equivalent to adding
   `-f deploy/docker-compose.override.yml` to the command above).
4. Wait for all services to report healthy:
   ```bash
   docker compose -f deploy/docker-compose.yml --project-directory . ps
   ```
5. Verify the backend is serving:
   ```bash
   curl http://localhost:8001/health/
   # → {"status": "ok", "checks": {"database": "ok"}, ...}
   ```

## Minimal stack

Same sequence, different `-f` path:

```bash
docker compose -f deploy/docker-compose.minimal.yml --project-directory . up -d
docker compose -f deploy/docker-compose.minimal.yml --project-directory . ps
curl http://localhost:8001/health/
```

No Celery worker/beat, no backup sidecar, no Honcho. Async-task-dependent features (LLM
long-running calls, webhooks, GitHub sync, memory consolidation) silently enqueue and never run —
see the header comment in `docker-compose.minimal.yml` for the exact list.

## Optional: Honcho memory backend

Add `--profile honcho` to the full-stack command (not available on the minimal stack):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho up -d
```

Then set `MEMORY_BACKEND=honcho` and `HONCHO_BASE_URL=http://honcho:8000` in `.env` and restart
`backend`/`celery`. See the `honcho`/`honcho-migrate` service comments in `docker-compose.yml` for
the embedding-dimension pitfall if you change `EMBEDDING_VECTOR_DIMENSIONS` after the first run.

## For AI agents

If you are an AI agent deploying this system unattended, the canonical, verified command
sequence is:

```bash
# From the repository root of this checkout:
cp .env.example .env
# Fill SECRET_KEY, AUTH_JWT_SECRET, FIELD_ENCRYPTION_KEY, DB_PASSWORD, DB_APP_PASSWORD in
# .env before proceeding — the stack refuses to start without them. Also set
# SYSTEM_ADMIN_PASSWORD if you want an admin user auto-created on first start (optional:
# if left empty, admin provisioning is skipped, logged, not fatal).

docker compose -f deploy/docker-compose.yml --project-directory . up -d
docker compose -f deploy/docker-compose.yml --project-directory . ps
curl -sf http://localhost:8001/health/
```

Facts:
- Always run from the repository root. Always include `--project-directory .` on every
  `docker compose` call against files in this directory — see "Required flag" above for why.
- Health check URL: `http://localhost:8001/health/` — HTTP 200 with `{"status": "ok"}` means the
  stack is fully up (`migrate` completed, `postgres`/`redis`/`backend` are healthy).
- If a service does not reach `healthy` within a few minutes, inspect its logs:
  ```bash
  docker compose -f deploy/docker-compose.yml --project-directory . logs <service-name>
  ```
- Do not delete or rename `docker-compose.override.yml` to "fix" a production deploy — it is
  never applied unless explicitly passed via `-f`, so its mere presence in this directory changes
  nothing for a plain `up -d` without `-f deploy/docker-compose.override.yml`.
- Prefer `docker-compose.minimal.yml` only when explicitly asked for a minimal/slim deployment;
  default to the full stack (`docker-compose.yml`) otherwise.
- Admin provisioning is create-only: changing `SYSTEM_ADMIN_PASSWORD` in `.env` and
  re-running `up -d` does **not** reset an already-existing admin's password. It only takes
  effect the very first time, against an empty database.
- `.env` changes are read at container **creation**, not live. `docker compose restart
  <service>` does NOT pick up a changed `.env` — re-run `up -d` (recreates containers whose
  resolved config changed) instead.
