---
type: REVIEW
scope: WP-1c (Infrastructure/Operations) — adversarial second review
status: final
date: 2026-10-01
author_agent: code-reviewer
branch: chore/audit-review-2026-09
method: read-only static verification against real product source/config; Docker daemon DOWN → no live tests
targets: [AUD-2026-09-124, -125, -126, -127, -128, -129, -137, -149; re-confirm -122, -123]
---

# REVIEW_WP1C — adversarial verification of WP-1c Critical/High findings

**Scope.** Independent read-only falsification attempt of the WP-1c register claims
(`docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5, detail in `AUDIT_INFRASTRUCTURE.md`).
The audit's own `AUDIT_EVIDENCE/` was **not** used as proof. Docker daemon is DOWN;
all claims about the live stack (compose runtime, beat dispatch, an actual backup
run) are runtime-only and are marked as such. No file outside
`docs/audit/2026-09/review/` was modified.

## Counter-evidence table

| ID | orig_sev | REVIEW_VERDICT | corrected_sev | counter-evidence (file:line + quote) | note |
|---|---|---|---|---|---|
| AUD-2026-09-122 | Critical | **UEBERZOGEN** | **High** | `scripts/backup.sh:84-87` `if [ ! -f "${PROJECT_ROOT}/docker-compose.backup.yml" ]; then … exit 1`; `backup.sh:157` `check_prerequisites` runs before every subcommand. But: `deploy/docker-compose.yml:348-505` is the working, tested `postgres-backup` sidecar (`run_once` / `prune_old`), and `docs/archive/audits/UMSETZUNGSPLAN_DOCKER-COMPOSE-2026-08-31.md:152` states `backup.sh` "in keinem Makefile-Target aufgerufen" wird. | Fact confirmed: the script exits 1 in **all** modes (incl. `--list`/`--cleanup`). Severity over-stated: it is dead legacy code, superseded by the automatically running, restore-verified sidecar. No active data-loss path. |
| AUD-2026-09-123 | Critical | **BESTAETIGT** | Critical | `scripts/restore.sh:183` `pg_restore … /tmp/backup.dump`; `:186` `psql … -f /tmp/backup.sql`; `:198-201` `docker-compose … exec -T postgres bash -c "… $restore_command" < "$backup_file"` — the host file is only piped to **stdin**, never copied into the container. | Claim holds exactly. `/tmp/backup.{dump,sql}` is never created inside the postgres container. Mitigation exists (compose comment `:304` `gunzip -c … | psql …`, audit reports 15/15 test) but does not make the script work. Critical retained — restore is the recovery path. |
| AUD-2026-09-124 | High | **BESTAETIGT** | High | `scripts/restore.sh:49` `BACKUPS_DIR="${PROJECT_ROOT}/backups"`; `:116` `ls -t "$BACKUPS_DIR"/*.dump "$BACKUPS_DIR"/*.sql`; `deploy/docker-compose.yml:372` `- postgres_backup_data:/backups`; `:405` sidecar writes `reqogniloom_<ts>.sql.gz`. | Format **and** location mismatch confirmed: sidecar → `.sql.gz` in a named Docker volume; restore.sh → `*.dump`/`*.sql` in a host `./backups` that is never created by the sidecar. |
| AUD-2026-09-125 | High | **BESTAETIGT** | High | `backend/audit/archive.py:448` `@shared_task(name="audit.archive_lifecycle_manager")`; no `backend/audit/tasks.py` (only `admin/apps/archive/events/models/query/services/writer/__init__`); `backend/audit/apps.py` `ready()` imports only `audit.writer`; `backend/reqogniloom/celery.py:45` `app.autodiscover_tasks()`; no `CELERY_IMPORTS`. | Worker autodiscovery only imports `<app>/tasks.py`; `archive.py` is imported only by a test and referenced by name in `settings.py:823`. Task is not in the worker registry → monthly archive is a guaranteed no-op. |
| AUD-2026-09-126 | High | **BESTAETIGT** | High | `backend/reqogniloom/settings.py:777-951` — grep for `task_acks_late\|task_reject_on_worker_lost\|worker_prefetch_multiplier\|broker_transport_options\|visibility_timeout` returns **0 hits**; Celery defaults therefore apply (`acks_late=False`, `reject_on_worker_lost=False`, `prefetch=4`, `{}`). | Semantics confirmed statically: pre-ack + no per-task retry (7 tasks, none `autoretry`) ⇒ SIGKILL/OOM-kill loses the in-flight message. Only the literal live `app.conf` echo is not reproducible (daemon down) — the claim does not depend on it. |
| AUD-2026-09-127 | High | **BESTAETIGT** | High | `scripts/restore.sh:183` `pg_restore -h postgres … --clean --if-exists -v /tmp/backup.dump`, executed in-place against the live `postgres` service (`:198/:206`). | Confirmed: `--clean --if-exists` drops/recreates objects directly on the live DB; `pg_restore` is not wrapped in a single transaction, so an abort leaves a half-restored database. Applies to the script; the compose one-liner is equally non-atomic. |
| AUD-2026-09-128 | High | **BESTAETIGT** | High | `deploy/docker-compose.yml:357` `BACKUP_RETENTION: ${BACKUP_RETENTION:-7}`; `:361` `BACKUP_INTERVAL: ${BACKUP_INTERVAL:-21600}` (6 h ⇒ 7×6 h = **42 h** horizon); `:372` `postgres_backup_data:/backups` (host-local named volume only). | 42-h horizon, no off-host copy, `gzip -9` only (no encryption), confirmed. Grep for `media|upload` in `deploy/docker-compose.yml` → **0 hits**, so no media/upload volume is backed up. |
| AUD-2026-09-129 | High | **TEILWEISE** | High | Confirmed part: `backend/reqogniloom/health.py:118-313` checks only `database`, `memory_backend`, `embedding_dimensions`, `llm_provider_env`, `csrf_cookie_secure_matches_auth`, workflow definitions — **no** cache/Redis, **no** worker, **no** beat. Falsified part: `health.py:134-135` `status["status"]="degraded"` **and** `http_status = 503`; likewise `:160-161`. `deploy/docker-compose.yml:642` `curl -f http://localhost:8000/health/ \|\| exit 1` fails on ≥400. | The register claim "`degraded` liefert HTTP **200**" is **false**: every path that sets `status="degraded"` also sets HTTP 503. HTTP 200 applies to the separate `status="warning"` state (embedding/LLM-env/CSRF/workflow advisories), not `degraded`. This also contradicts `AUD-2026-09-031` in the same register (DB failure → "korrekt 503") and `AUDIT_INFRASTRUCTURE.md:331-333` ("backend bleibt healthy bei DB-Verlust"), which `curl -f` + 503 disproves. Core gap (no cache/worker/beat probe) remains High. |
| AUD-2026-09-137 | High | **BESTAETIGT** | High | `.github/workflows/docker-publish.yml` has exactly **one** job `build-and-push` (`:26-27`) with **no** `needs:`/`workflow_run`/`concurrency:`; build (load-only, `:102`/`:118`) and push (`:168`/`:183`) are **two separate** `docker/build-push-action` steps; `ci.yml:4-7` triggers only `branches: [main, feat/**]` / `pull_request` — **no tag trigger**; grep `sbom\|cosign\|provenance\|attest\|slsa` across all workflows → **0 hits** (`environment:`/`concurrency:` exist only in `pages.yml:31,38`, out of scope). | All three sub-claims confirmed: no test-before-image gate (tag push needs no CI), scan artefact ≠ pushed artefact (separate build), no SBOM/signing/provenance. |
| AUD-2026-09-149 | High | **BESTAETIGT** | High | No staging definition in repo (only unrelated `.venv/.../repowise/.../staging.py`); grep `environment:\|concurrency:\|needs:\|workflow_run` in `.github/workflows/*.yml` → only `pages.yml`. `ci.yml` and `docker-publish.yml` contain **0** `environment:`/`concurrency:` and no approval gate; the sole deploy path is `docker compose up` on `deploy/docker-compose.yml`. | Confirmed. Process gap rather than a code defect; High is defensible for a customer-facing release chain, though it could be argued as Medium. |

## Register cross-check notes

1. **Internal contradiction (129 vs 031 / §8).** `AUD-2026-09-031` states `/health/`
   returns 503 on DB failure; `AUD-2026-09-129` and `AUDIT_INFRASTRUCTURE.md:323,331-333`
   claim `degraded` → HTTP 200 and a healthy backend container on DB loss. The source
   (`health.py:134-135,160-161`; `docker-compose.yml:642`) supports **031**, not 129/§8.
   The 129 summary must be restated as: *warnings* return 200; *degraded* returns 503;
   cache/worker/beat are not probed at all.
2. **Cited locations.** All cited `file:line` anchors for 122–128, 137, 149 were
   verified and are correct. `126` and `149` cite runtime/absence observations rather
   than a file:line; the semantic claims were nonetheless confirmed by static config.
3. **Not independently reproducible (daemon DOWN).** Live `app.conf` echo (126),
   beat `0× Sending due task` (121, out of scope), and an actual backup run (128)
   are runtime-only. None of the target verdicts hinge on them.

## Verdict counts (targets, n=10)

- BESTAETIGT: **8** (123, 124, 125, 126, 127, 128, 137, 149)
- TEILWEISE: **1** (129 — core gap true, HTTP-200 claim false)
- UEBERZOGEN: **1** (122 — fact true, severity overstated)
- FALSCH: 0 · NICHT VERIFIZIERBAR: 0 · KEIN REQOGNILOOM-BEZUG: 0

**Top 5 key verdicts**

1. **129 TEILWEISE — the headline "degraded liefert HTTP 200" is wrong.** Source sets
   HTTP 503 whenever it sets `status="degraded"` (`health.py:134-135,160-161`). The
   genuine defect is the *absence* of cache/worker/beat probes, not a false 200.
2. **122 UEBERZOGEN (Critical → High).** `backup.sh` is indeed dead (`:84-87`), but it
   is unused legacy code next to the working, restore-verified sidecar
   (`compose:348-505`); no active data-loss path.
3. **137 BESTAETIGT.** One publish job, no `needs`/`workflow_run`/`concurrency`,
   separate build-vs-push actions, no tag trigger in `ci.yml`, 0 SBOM/Cosign/provenance.
4. **125 BESTAETIGT.** `audit.archive_lifecycle_manager` is defined in `archive.py`, no
   `audit/tasks.py`, `autodiscover_tasks()` cannot see it → monthly retention never runs.
5. **124/123 BESTAETIGT.** Format/location mismatch (`.sql.gz` in Docker volume vs.
   `*.dump|*.sql` in host `./backups`) and the file never entering the container make the
   documented operator backup/restore path non-functional.
