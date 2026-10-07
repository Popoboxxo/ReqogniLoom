# Deployment Runbook — Post-Deploy Verification Gate

**Run this after every `docker compose … up -d`. A deploy is not done until this gate is green.**

Everything here exists because a deployment could report success while being broken
(#1074, #1050, #1051, #1052, #1053, #1054). Each check below has a failure mode that
is invisible from the UI, from `docker ps`, and from the container health status.

Run from the **repository root**. The canonical command shape is always:

```bash
docker compose -f deploy/docker-compose.yml [--profile honcho] --project-directory . <subcommand>
```

Set a shorthand once:

```bash
DC="docker compose -f deploy/docker-compose.yml --project-directory ."
BACKEND=http://localhost:${BACKEND_PORT:-8001}
```

---

## 1. Backup verification (#1074) — a file existing is not a backup

The automatic `pg_dump` sidecar used to write a **389-byte file containing no table
data** and log `wrote …`, because `pg_dump … | gzip > f` reports the exit status of
`gzip` (always 0), not of `pg_dump`. The first dump also landed on a freshly
migrated, empty database, with the next attempt 24 h away.

```bash
# 1a. Is the newest dump real? (COPY-block count, NOT file existence)
$DC exec postgres-backup sh -c '
  f=$(ls -1t /backups/reqogniloom_*.sql.gz | head -1)
  echo "file=$f size=$(stat -c%s "$f")"
  n=$(gunzip -c "$f" | grep -c "^COPY ")
  echo "COPY blocks=$n"
  [ "$n" -ge 1 ] || { echo "FAIL: dump contains no table data"; exit 1; }
  cat /backups/.last_backup_status
'
```

**PASS** = `COPY blocks >= 1` and `.last_backup_status` says `status=ok`.
**FAIL** = 0 blocks, or the marker says `status=failed`, or no dump file at all.
A dump of a migrated ReqogniLoom database always has one `COPY` block per table.

```bash
# 1b. Force a fresh dump and let its exit code BE the verdict.
#     BACKUP_ONCE runs exactly one dump and exits with the dump's own status,
#     so a broken backup fails this command instead of passing quietly.
#     BACKUP_INITIAL_DELAY=0 because a gate does not wait 5 minutes.
$DC run --rm -e BACKUP_ONCE=true -e BACKUP_INITIAL_DELAY=0 postgres-backup \
  && echo "backup gate OK"
```

Then re-run 1a. A **newly deployed** instance has no dump until
`BACKUP_INITIAL_DELAY` (default 300 s) has elapsed — that is intended (#1074), so
run 1b explicitly right after a deploy rather than waiting.

Restore drill (optional but this is the only thing that proves restorability):

```bash
gunzip -c /backups/reqogniloom_<ts>.sql.gz | head -50   # real DDL, not just a header
```

**Failure semantics** — the sidecar exits non-zero when `pg_dump` fails, when the
dump has fewer than `BACKUP_MIN_COPY_BLOCKS` `COPY` blocks, when `gzip` fails, or
when the published file is not a valid gzip stream. A failed dump is **deleted**,
never left behind looking like a backup. After `BACKUP_MAX_CONSECUTIVE_FAILURES`
(3) consecutive failures the process exits non-zero on purpose, so the container
shows as restarting in `docker ps` instead of rotating empty files forever.

Regression self-check for the script itself (needs bash, docker, python3+PyYAML):

```bash
deploy/verify-backup-command.sh
```

---

## 2. Health, including embedding dimensions (#1053)

```bash
curl -sf $BACKEND/health/ | python -m json.tool
```

**PASS** = `"status": "ok"` and `checks.embedding_dimensions` is **not**
`"mismatch"`.

```bash
# Pre-deploy, as the superuser role via the one-shot `migrate` service:
$DC run --rm migrate python manage.py verify_embedding_dimensions

# If it reports a mismatch, fix it with the same service — NOT with
# `exec backend`. The backend runs as the least-privilege DB_APP_USER, which
# does not own the tables or their HNSW indexes, so that path dies with
#   django.db.utils.ProgrammingError: must be owner of index mem_entry_embedding_hnsw
$DC run --rm migrate python manage.py align_embedding_dimensions
$DC exec backend python manage.py backfill_embeddings   # the resize discards vectors
```

`/health` deliberately stays **HTTP 200** on a width mismatch (it disables
semantic search without making the service unhealthy), so a container probe will
never restart-loop over it — this gate is the only thing that catches it.

---

## 3. LLM provider, including `x-opencode-session` (#1050, #1051)

`LLM_PROVIDER=opencode_go` without `LLM_OPENCODE_SESSION` is a **fully dead LLM**:
every AI feature returns `400 MissingSessionID` while `/health` stays 200 and the
UI loads normally.

```bash
# 3a. The preflight gate. It must say OK; if it FAILED, the deploy aborted
#     and backend/celery/celery-beat never started.
$DC logs llm-preflight

# 3b. Prove the value actually reaches the running containers.
$DC exec backend printenv LLM_OPENCODE_SESSION
$DC exec backend python -c \
  "from llm_adapter.providers import resolve_provider_config as r; c=r(); \
   print(c.provider_name, c.model_name, c.opencode_session)"
#     -> opencode_go mimo-v2.5 reqogniloom-<instance>     PASS
#     -> opencode_go mimo-v2.5 None                       FAIL (#1050)

# 3c. Prove a real call goes through, not just the config.
$DC exec backend python -c \
  "from llm_adapter.providers import get_provider; \
   print(get_provider().complete('Answer with one word: capital of France?'))"
#     400 MissingSessionID                                 FAIL
```
A `MissingSessionID` also means the variable was changed but the container was only
**restarted**: `.env` is read at container creation, so re-run `up -d`.

The gate rejects two values, not one: an **empty** `LLM_OPENCODE_SESSION`, and the
unedited **placeholder** from `.env.example` (`…change-me…`, case-insensitive). The
second one matters because a copy-paste deployment would otherwise ship the same
session id as every other installation that never edited the line — configured, and
still wrong.


**Honcho side (#1051)**: the same value also feeds the nine Honcho engine-module
header variables, derived at container start. (Docker 29.8.1 *can* carry a dashed
env name — the original "Docker drops it" note was false, #1187 — but the shim is
kept deliberately: harmless, and portable to older Docker versions. See the note
in `deploy/docker-compose.yml`.)

```bash
$DC --profile honcho exec honcho sh -c 'env | grep -c x-opencode-session'  # 0 at rest is expected
$DC --profile honcho logs honcho | grep 'derived x-opencode-session'
#     "[honcho] derived x-opencode-session for 9 engine module(s)"         PASS
#     "[honcho] LLM_OPENCODE_SESSION is empty"                             FAIL
```

---

## 4. nginx resolves upstreams per request (#1054) — no frontend restart needed

**Resolved per request.** A backend recreate used to leave the frontend proxy
answering 502 on `/api/` and `/mcp/` until the *frontend* was also restarted: nginx
resolves a literal `proxy_pass http://backend:8000;` once, at worker start, and
keeps that IP. The SPA is served by the same nginx, so the UI loaded and only the
login POST failed — which reads to the user as "wrong password" and is invisible to
every application health check.

`frontend/nginx.conf` now uses Docker's embedded DNS per request
(`resolver 127.0.0.11 ipv6=off valid=10s;` + `set $…_upstream` + `proxy_pass
$…_upstream;`) for `/api/`, `/mcp/` and the bluepencil sidecar.

```bash
# After any backend recreate, WITHOUT restarting the frontend:
curl -s -o /dev/null -w 'login via frontend proxy: %{http_code}\n' \
  -X POST -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"'"$ADMIN_PW"'"}' \
  http://localhost:${FRONTEND_PORT:-5173}/api/v1/auth/login/
#     401 (bad credentials, backend reachable)   PASS  <- a 401 still proves the proxy works
#     502                                          FAIL  <- nginx is holding a stale backend IP
```

**No frontend restart after a backend recreate is required.** Worst case is a
`valid=10s` DNS cache window, so a request issued in the first 10 s after a recreate
can still 502; retry after 10 s. If a 502 persists beyond that, the frontend
container is running an old image — re-run `up -d frontend`, it is not a
configuration problem.

---

## 5. Honcho worker and derived memory layers (#1052)

Honcho's reasoning (deriver, peer card, summary, dream) runs **server-side in a
separate process**. The image's own entrypoint starts only the API server, so
without a worker the queue is never drained: work units stay `processed = false`
forever, no `document_sources` are written, and the derived memory layers never
materialise — while the model pins sit in the compose file looking configured. The
memory **read** path stays green, so this is invisible from the UI.

```bash
$DC --profile honcho ps honcho honcho-deriver
#     honcho            Up (healthy)
#     honcho-deriver    Up (healthy)              PASS  <- option (a) is in place
#     honcho-deriver    Exited / Restarting       FAIL  <- queue will never drain

$DC --profile honcho logs honcho-deriver | grep -E 'Running main loop|ReconcilerScheduler started'
#     "Running main loop"
#     "ReconcilerScheduler started with 3 tasks: ['sync_vectors', 'cleanup_queue', 'backfill_document_sources']"
```

```bash
# Does the queue actually drain?  Write a message, then watch the work unit.
$DC --profile honcho exec honcho-postgres psql -U honcho -d honcho -c \
  "SELECT count(*) FILTER (WHERE processed) AS done, count(*) FILTER (WHERE NOT processed) AS pending FROM queue;"
#     pending stays constant and done stays 0        FAIL (#1052 regressed)
```

Honcho batches by token threshold, so a low-traffic deployment can legitimately
leave a work unit `pending` for up to `REPRESENTATION_BATCH_MAX_AGE_SECONDS`
(upstream default 1800 s). Judge the worker by its process and log lines above;
`DERIVER_FLUSH_ENABLED=true` (Honcho's own flag) bypasses batching if an immediate
flush is needed for a test.

---

## 6. Restore — a backup is only proven by restoring it (ADR-012, DATA-02)

Backup and restore have exactly **one** source of truth (ADR-012): the
`postgres-backup` sidecar. The former `scripts/backup.sh` / `scripts/restore.sh`
were removed — they could never succeed, and their in-place `--clean --if-exists`
restore was not atomic. There is no second path.

### 6.1 Format / location contract

| Property | Value |
|----------|-------|
| Producer | `postgres-backup` sidecar only (`deploy/docker-compose.yml`) |
| Format | plain `pg_dump` SQL, gzip-compressed: **`reqogniloom_<YYYYmmdd_HHMMSS>.sql.gz`** |
| Location | named Docker volume **`postgres_backup_data`**, mounted at `/backups` inside the sidecar — **never** a host `./backups` folder |
| Marker | `/backups/.last_backup_status` = `<iso8601> status=<ok\|failed\|offhost_failed> copy_blocks=<n> file=<path>` |
| Retention | newest `BACKUP_RETENTION` dumps (default 7) every `BACKUP_INTERVAL` s (default 21600 = 6 h) → default horizon ≈ 42 h |
| Not part of the contract | no `.dump`/`.sql`-only variant, no second producer |

The recovery horizon is only `BACKUP_RETENTION × BACKUP_INTERVAL`; widen both in
`.env` for a longer on-host history.

### 6.2 Off-host export (opt-in, DATA-02)

```bash
# .env: an absolute path on a genuinely separate filesystem/remote mount
BACKUP_OFFHOST_DIR=/mnt/nfs/reqlo-backups

docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.offhost.yml \
  --project-directory . up -d postgres-backup
```

The sidecar then copies each verified `.sql.gz` to the mount. If the copy fails
the **local dump is kept** and the run reports `status=offhost_failed` (non-zero)
— an absent off-host copy is never silent. Without the overlay nothing changes.

**Residual risks (ADR-012 — named, not fixed here):** the exported artifact is
still **unencrypted** (`gzip` is compression, not encryption); **remote
retention is not implemented** (the sidecar prunes only the local volume); and
the repository cannot verify that the configured path is genuinely off-host.
Media/user uploads are not in the dump and the **minimal stack has no sidecar at
all** (`docker-compose.minimal.yml`) — those two require a manual route.

### 6.3 Atomic restore into an isolated target

Never restore into the live database and never run `--clean --if-exists` against
it. The procedure below creates a **throwaway target**, restores the newest real
dump in **one transaction** (`--single-transaction`: any error rolls the whole
restore back) and leaves the live database untouched.

```bash
PG_IMAGE=pgvector/pgvector:pg16
VOLUME="$(docker volume ls -q --filter name=postgres_backup_data | head -1)"
NET=reqlo-restore-$$; TGT=reqlo-restore-pg-$$

docker network create "$NET"
docker run -d --name "$TGT" --network "$NET" --network-alias target \
  -e POSTGRES_DB=restored -e POSTGRES_USER=rt -e POSTGRES_PASSWORD=rt "$PG_IMAGE"
until docker exec "$TGT" pg_isready -U rt -d restored >/dev/null 2>&1; do sleep 2; done

docker run --rm --network "$NET" -v "$VOLUME":/backups:ro -e PGPASSWORD=rt \
  "$PG_IMAGE" bash -c '
    set -euo pipefail
    f=$(ls -1t /backups/reqogniloom_*.sql.gz | head -1)
    echo "restoring $f"
    gzip -t "$f"
    gunzip -c "$f" | psql -h target -U rt -d restored \
      --single-transaction -v ON_ERROR_STOP=1 -q -o /dev/null
    echo "restore committed"
  '

# inspect (optional):  docker exec "$TGT" psql -U rt -d restored -c '\dt'
docker rm -f "$TGT"; docker network rm "$NET"
```

`exit 0` + `restore committed` means the dump is restorable. Any error aborts the
transaction and leaves the target with zero tables — that is the property that
replaces the old non-atomic restore.

**Automated gate (preferred):** `deploy/verify-restore.sh` runs this whole
procedure against a self-contained 15-table source using the **real** inlined
sidecar command block, asserts **15/15 tables / 0 errors**, and proves that an
injected error rolls back to zero tables.

```bash
deploy/verify-restore.sh
```

---

## Gate summary

| # | Check | PASS signal |
|---|-------|-------------|
| #1074 | `COPY` blocks in the newest dump + `status=ok`; `BACKUP_ONCE` run exits 0 | `COPY blocks >= 1` |
| ADR-012 | `deploy/verify-restore.sh` / §6 atomic isolated restore | ALL CASES PASSED (15/15, 0 errors, rollback) |
| #1053 | `/health` `status: ok`, `embedding_dimensions` not `mismatch` | both |
| #1050 | `llm-preflight` OK, session reaches the container, one real LLM call succeeds | no `MissingSessionID` |
| #1051 | Honcho logs `derived x-opencode-session for 9 engine module(s)` | present |
| #1054 | login through the frontend proxy after a backend recreate, no frontend restart | 401, never 502 |
| #1052 | `honcho-deriver` running and logging `Running main loop` | both lines |

## Related issues

#1074 (empty-but-successful backup), #1054 (nginx stale backend IP),
#1050 (missing `LLM_OPENCODE_SESSION`), #1051 (Honcho engine modules cannot
authenticate), #1052 (no Honcho deriver/queue worker), #1053
(`align_embedding_dimensions` fails against the app role),
ADR-012 (sidecar is the single backup source; the dead `scripts/backup.sh` /
`scripts/restore.sh` were removed; §6 is the atomic restore contract).
