---
type: REVIEW
scope: "WP-1c (Infrastructure) — supplement"
status: final
date: 2026-10-01
author_agent: devops-engineer
branch: chore/audit-review-2026-09
method: "read-only adversarial verification against real product source/config; Docker stack UP (2026-10-01) → live re-test where non-colliding; isolated kombu/celery reproduction with the project .venv"
targets: [AUD-2026-09-120, -121, -130, -131, -132, -133, -134, -135, -136, -138, -139, -140, -141, -142, -143, -144, -145, -146, -147, -148]
---

# REVIEW_WP1C_SUPP — adversarial supplement to `REVIEW_WP1C.md`

**Scope.** Independent falsification of the WP-1c findings that `REVIEW_WP1C.md`
did **not** cover (register `docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5 and report
`AUDIT_INFRASTRUCTURE.md`). The audit's own `AUDIT_EVIDENCE/*` was **not** accepted
as proof; every verdict is re-derived from product source/config. Docker stack was
**UP** during this review (`ai-native-reqflow-poc-*`, backend `localhost:8001`), so
runtime-only claims were re-tested read-only. No Redis stop, no container restart,
no push; only `docs/audit/2026-09/review/` was written. `.kimi-code/` and
`stack-seeds.md` untouched.

**Method.**
1. Static: `celery.py`, `settings.py`, `deploy/docker-compose*.yml`,
   `testing/docker-compose.test.yml`, `scripts/build.sh`, `mcp_server/sse_pubsub.py`,
   `persistence/cache_generation.py`, `.github/workflows/*`.
2. Isolated reproduction: Celery 5.6.3 / kombu 5.6.2 from the project `.venv`
   (`.venv/Scripts/python.exe`) with the **literal** `celery.py` config, memory
   transport — no broker contacted.
3. Live read-only: broker binding set (`redis-cli`), Celery `inspect registered`,
   `django_celery_beat_periodictask` (Postgres), worker/beat logs, `redis CONFIG GET`,
   `SHOW <pg param>`, `pg_indexes`, HTTP probes, `docker compose build` on the release file.

## 1. Gegenbeweis-Tabelle (Zielbefunde, Original-Aussage gegen echten Code/Config)

| ID | orig_sev | VERDIKT | korr. sev | Gegenbeweis `<pfad>:<zeile>` + Zitat | Anmerkung |
|---|---|---|---|---|---|
| **120** | Critical | **BESTAETIGT** | Critical | `backend/reqogniloom/celery.py:31-36` `app.conf.task_queues = (Queue('default'), Queue('llm'), Queue('events'), Queue('memory'))`; `celery.py:37` `task_default_queue='default'`. Isolated probe (`.venv` Celery 5.6.3): **all four** resolve to `exchange='default' type='direct' routing_key='default'`. Live worker banner: `default/events/llm/memory exchange=default(direct) key=default`. Broker set `_kombu.binding.default` = 4 members; kombu format is `routing_key\x06\x16pattern\x06\x16queue` (`kombu/transport/redis.py:1053-1063`), so all four members are `routing_key='default'` with queues `default,llm,events,memory`. Worker consumes all four queues: `deploy/docker-compose.yml:887` `... -Q default,llm,events,memory ...`. Isolated fanout (`memory://`, publish 1 msg to `exchange=default/rk=default`): **4/4 queues received → TOTAL DELIVERIES = 4**. | Claim holds exactly. `application/tasks.py:20` shows the task is *not* self-rescheduling; `task_routes` only pick a queue name, not a routing key, so every task is published with `rk='default'` and copied to all four queues → 4 executions. |
| **121** | Critical | **FALSCH** (Headline) | **Low** (Rest) | **Headline „Beat dispatcht nie — gesamter Schedule tot" live widerlegt.** `deploy/docker-compose.yml:947` `celery -A reqogniloom beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`; `deploy/docker-compose.yml:817-830` (Settings) = 3 schedules. Live DB `django_celery_beat_periodictask`: `dispatch-outbox-events total_run_count=223653 last_run_at=17:08:43`, `record-celery-beat-heartbeat 18652 / 17:08:47` — both **advanced during observation** (T0 223619/17:05:42 → T1 223653/17:08:43). Worker log executes `application.dispatch_outbox_events` **every 5 s** (`DomainEventBus: dispatched 0 event(s) this cycle` @ 17:07:53…17:08:53). Ratio 223619/18648 = **12.0** = 5s:60s exactly. | Sub-claims: **(a) BESTAETIGT** `docker-compose.yml:933` `pgrep -f 'celery.*beat'` (process only). **(b) BESTAETIGT** `audit/archive.py:448` defines the task, `backend/audit/tasks.py` does **not** exist, `audit/apps.py:36` imports only `audit.writer`, `celery.py:45` `autodiscover_tasks()`; live `celery inspect registered` lists 6 tasks, `audit.archive_lifecycle_manager` **absent** → this is exactly **AUD-125/270** (Duplikat). **(c)** The register's „0× `Sending due task`" is *literally* true (0 hits in the beat log) but is a **logging artifact**, not evidence of a dead schedule — the DB counters and the 5-s worker executions prove dispatch. |
| 130 | Medium | **TEILWEISE** | **Low** | No-TTL part true: `ai_derivation_service.py:396` `cache.set(version_key, version, None)`; `:500` `cache.set(version_key, 2, None)`. **But**: derivation *results* are TTL-bound (`:373` `DERIVATION_CACHE_TTL_SECONDS = 3600`; `:2235` `cache.set(cache_key, result, DERIVATION_CACHE_TTL_SECONDS)`) and are deleted (`:2433 cache.delete(cache_key)`); the counters **are** invalidated via `invalidate_derivation_cache` (`:481-506`, caller `application/cache_invalidation.py:286`). Live db1: 843 keys, 659 ohne TTL, davon **658 `llm_derivation_ver:<uuid>`** (+1 heartbeat), 184 mit TTL. | Register „648/831 ohne TTL, **nie invalidiert**" ist irreführend: die 648 no-TTL-Keys sind **Versionszähler** (bewusst non-expiring, Doku `:388-397`, ein Key pro Artefakt), nicht die teuren Resultate; sie werden per `incr` **aktualisiert**. Wachstum ist durch die Artefaktmenge begrenzt, nicht durch Derivationen. Zahl 648 ist Snapshot (jetzt 658). |
| 131 | Medium | **BESTAETIGT** | Medium | `deploy/docker-compose.yml:543/545` `exec redis-server --maxmemory 256mb --maxmemory-policy noeviction --appendonly yes`; `settings.py:879-884` `CACHES` = nur `BACKEND`/`LOCATION`, kein `TIMEOUT`/`SOCKET_TIMEOUT`. Live `CONFIG GET`: `maxmemory=268435456`, `maxmemory-policy=noeviction`. | Broker (db0) und Cache (db1) teilen **eine** 256-MB-Instanz; bei Volldruck scheitern `cache.set()` mit OOM. Bestätigt. |
| 132 | Medium | **BESTAETIGT** | Medium | `settings.py:793` Result-Backend = `.../0`; **kein** `result_expires` in `settings.py` → Celery-Default 86400 s. Live db0: 2425 `celery-task-meta-*`; TTL-Stichprobe `[1995, 86021, 1900, 86257, 8091]` s ≤ 86400. | 24-h-Aufbewahrung bestätigt. **Zahl nicht reproduzierbar**: Register nennt 5914, live 2425 (Snapshot/Stack-Neustart + `celery.backend_cleanup`). „Ungebremst" ist durch das 24-h-TTL faktisch begrenzt. |
| 133 | Medium | **BESTAETIGT** | Medium | `mcp_server/sse_pubsub.py:29-31` `_get_redis_url()` `return getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/0")`; Keys `mcp:session:{id}:auth/eventid/buffer` (`:48,52,56`); `settings.py:792` Broker = `.../0`. | MCP-Sessions liegen in **db0** (Broker). Live aktuell **0** `mcp:session:*` (keine aktiven SSE-Clients) → Live-Zahl nicht reproduzierbar, Speicherort aber statisch belegt. `FLUSHDB`/`FLUSHALL` auf db0 zerstört Sessions und Queue. Medium haltbar. |
| 134 | Medium | **UEBERZOGEN** | **Low** | `settings.py:879-884` — tatsächlich kein `KEY_PREFIX`/`KEY_FUNCTION`. Aber die Keys enthalten strukturelle UUIDs: `persistence/cache_generation.py:80` `f"{_KEY_PREFIX}:{namespace}:{scope_id}"` (scope_id = Workspace-UUID, `:88`), `ai_derivation_service.py:413` `llm_derivation:{sha256(provider:capability:artifact_id…)}`. | „Tenant-Trennung nur **zufällig** über UUIDs" überzeichnet: UUIDs sind **global eindeutig** → keine Kollision möglich; es fehlt lediglich ein explizites Tenant-Präfix (Defense-in-Depth), kein Korrektheitsdefekt heute. Low. |
| 135 | Medium | **BESTAETIGT** | Medium | 15 Services (`docker-compose.yml:247…1331`); `logging:`-Blöcke nur 11× (285,501,547,636,734,786,841,923,971,1305,1344). **Ohne** `logging:`: `honcho-postgres:1015`, `honcho-redis:1030`, `honcho-migrate:1046`, `honcho:1108` = **4**. | Genau die 4 genannten honcho-Services. (`honcho-deriver:1305` hat sehr wohl Rotation.) Bestätigt. |
| 136 | Medium | **BESTAETIGT** | Medium | `docker-compose.yml:1047,1109,1231` `image: ghcr.io/plastic-labs/honcho:latest`; ferner bewegliche Tags `redis:7-alpine` (`:516,1031`), `pgvector/pgvector:pg16` (`:248,…`), `node:22-slim` (`:1332`); grep `@sha256` → **0**. | Kein Digest-Pinning bestätigt; `honcho:latest` konkret vorhanden. Medium haltbar. |
| 138 | Medium | **BESTAETIGT** | Medium | `scripts/build.sh:88-92` ruft `docker compose -f deploy/docker-compose.yml build`; `:94` `log_info "Build completed"`. `grep -c '^\s+build:'` in `deploy/docker-compose.yml` = **0**. Live: `docker compose … build` → `level=warning msg="No services to build"`, **EXITCODE=0**. | Bestätigt: Skript meldet Erfolg bei 0 gebauten Images. (Kein Sicherheitsimpact; Medium als „falsche Erfolgsmeldung" verteidigbar.) |
| 139 | Medium | **BESTAETIGT** | Medium | Backend-Healthcheck `docker-compose.yml:641-642` `curl -f http://localhost:8000/health/ \|\| exit 1`; einziger Health-Pfad `reqogniloom/urls.py:28` `path("health/", …)`; grep `livez\|readyz` im Backend → **0 Treffer**. | Keine getrennten Liveness-/Readiness-Checks bestätigt. **Zitatfehler:** die Register-Orte `deploy/docker-compose.yml:139,147` zeigen aktuell auf den `x-honcho-env`-Block (LLM_OPENCODE_SESSION/DERIVER_*), **nicht** auf Healthchecks (Zeilenverschiebung seit Audit-Commit `3dcc80d8`). `:933` ist der Beat-Healthcheck. |
| 140 | Low | **BESTAETIGT** | Low | `testing/docker-compose.test.yml:54-56` `depends_on:\n      - postgres\n      - redis` — Listenform ohne `condition: service_healthy`. | Bestätigt. Kontext: Overlay setzt laut Header-`docker-compose.test.yml:16-17` einen bereits laufenden Basis-Stack voraus; dennoch kein Wait auf Health. Low haltbar. |
| 141 | Medium | **BESTAETIGT** | Medium | `settings.py:899-953`: Root/`django`/`reqogniloom`/`celery` alle hart `"level": "INFO"`, **kein** `LOG_LEVEL`-Env (`grep LOG_LEVEL` = 0). `backend/requirements.txt` grep `prometheus\|opentelemetry\|sentry\|otel` → **0**. Live: `GET /metrics/` → **404**, `GET /health/` → 200. `rest_api/urls.py:237` `router.register(r"metrics", MetricsViewSet)` = authentifizierter SE-Metrik-Proxy, kein Exporter. | Kein Exporter/Tracing, `LOG_LEVEL` nicht konfigurierbar — bestätigt. |
| 142 | Medium | **TEILWEISE** | **Low** | Eigene Extraktion der echten Compose-Interpolationen (ohne Kommentare, ohne escapte `$${…}`) über die 4 Compose-Dateien vs. aktive `^[A-Z_]+=` in `.env.example`: **7** fehlende aktive Variablen — `AUTH_COOKIE_SECURE` (override:63), `BACKEND_PORT` (compose:635), `BACKUP_ONCE` (compose:370), `CELERY_CONCURRENCY` (compose:887), `COMPOSE_PROJECT_NAME` (override:46), `FRONTEND_PORT` (compose:970), `HONCHO_DB_PASSWORD` (compose:73). | Register nennt **8**. Abweichung: `CELERY_CONCURRENCY` **ist** in `.env.example:571` als `#CELERY_CONCURRENCY=4` dokumentiert (nur auskommentiert) → „fehlt in `.env.example`" ist unpräzise. Alle 7 haben Compose-Defaults (`:-…`) ⇒ kein Laufzeitausfall, reine Doku-/Tuning-Drift ⇒ eher Low. |
| 143 | Medium | **BESTAETIGT** (als **DUPLIKAT #1019**) | Medium | `persistence/embedding_dimensions.py:84` `DEFAULT_EMBEDDING_VECTOR_DIMENSIONS = 384`; Live `information_schema`: genau 4 `vector`-Spalten (`pl_requirement`, `pl_tracelink`, `icd_icd`, `mem_memory_entry`), alle `vector(384)`. | Kontrolle erfüllt: Register führt `143` korrekt als `DUPLIKAT #1019` (vgl. `AUDIT_FINDINGS.md:1854`); die Laufzeitfehler-Prämisse ist widerlegt. Kein eigenständiger Befund. |
| 144 | Low | **TEILWEISE** | Low | `pg_indexes` auf `pl_artifact`: kein Index auf `created_at` → „Sort nötig" bestätigt. Duplikate: **exakt** ist nur `parent_id` doppelt (`idx_artifact_parent_btree` und `pl_artifact_parent_id_71baafe4`). `lifecycle_status`/`priority` haben je einen `…_like`-**varchar_pattern_ops**-Index — **keine** exakten Duplikate (andere Operator-Klasse). | „4 exakte Duplikate (parent_id ×2, lifecycle_status ×2, priority ×2)" ist **falsch**: nur **1** exaktes Duplikat; die `_like`-Indizes bedienen `LIKE 'prefix%'`. Teilaussage `created_at` unindiziert bleibt. Low (und eher reduziert). |
| 145 | Low | **TEILWEISE** | Low | `deploy/docker-compose.yml:887` `--concurrency=${CELERY_CONCURRENCY:-4}` (Release-Default 4); **Live-Stack läuft mit dem Override** `deploy/docker-compose.override.yml:131` `--concurrency=${CELERY_CONCURRENCY:-2}`; `docker inspect` Cmd = `celery -A reqogniloom worker --loglevel=debug --concurrency=2`; Worker-Banner `concurrency: 2 (prefork)`. | Beobachtung (Release-Default 4 vs. live 2) stimmt, aber die Ursache ist der **Dev-Override**, nicht ein Widerspruch innerhalb des Release-Compose. `CELERY_CONCURRENCY` ist nirgends aktiv gesetzt. Framing „Release-Compose ≠ laufender Stack" ist überzeichnet. Low. |
| 146 | Low | **BESTAETIGT** | Low | `llm_adapter/tasks.py:188-189` `… CONN_MAX_AGE is unset (Django default 0), so that connection is closed …`; dagegen `settings.py:347` `"CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int)`. | Stale-Kommentar exakt bestätigt (60, nicht 0). Low. |
| 147 | Medium | **TEILWEISE** | **Low** | `max_connections`-Teil: Live `SHOW max_connections` = **300**; `postgresql.auto.conf` enthält `max_connections = '300'` + `superuser_reserved_connections='5'`; **kein** `command:` am Postgres-Service (`docker-compose.yml:247-295`) → nur im Volume, nicht versioniert: **BESTAETIGT**. **shared_buffers**-Teil: Live `SHOW shared_buffers` = **128MB** (Postgres-Default), nicht 160 MB; cgroup-Limit 384M (`docker-compose.yml:252`). | Zahlfehler: „`shared_buffers` 160 MB in 384 MB cgroup" ist live **nicht reproduzierbar** (128 MB = 33 % cgroup, unauffällig). Der belastbare Kern ist die unversionierte `max_connections=300` (`down -v` → 100). Low statt Medium. |
| 148 | Low | **BESTAETIGT** | Low | `docker-compose.yml:73,1020,1053` `postgresql+psycopg://honcho:${HONCHO_DB_PASSWORD:-honcho-dev-password}@…` bzw. `POSTGRES_PASSWORD: ${HONCHO_DB_PASSWORD:-honcho-dev-password}`. | Klartext-Default exakt bestätigt. Low. (Überlappung mit `AUD-2026-09-241` siehe `REVIEW_WP6A.md:53` — Register-Doppelführung.) |

## 2. Register-Quercheck

1. **120 vs. 126 (kein Widerspruch, Verstärkung).** `120` = 4-facher Queue-Fanout
   (jede Nachricht an alle 4 Queues), `126` = Pre-Ack ohne Retry (`acks_late=False`,
   kein `reject_on_worker_lost`). Beide sind unabhängig; der Report-Faktor
   „4 × 2 = bis zu 8" ist eine zulässige Kombination, keine Doppelzählung.
2. **121 vs. 125/270 (echtes Duplikat).** `121`-Teilaussage (b)
   (`audit.archive_lifecycle_manager` nicht im Worker-Set) ist inhaltlich
   **identisch** mit `AUD-2026-09-125` (= `AUD-2026-09-270`). Beide werden als
   eigene Findings geführt — Zähl-/Doppelführungsproblem im Register, kein
   zusätzlicher Defekt. Nach Abzug des (live widerlegten) Beat-Teils bleibt für
   `121` nur die schwache Healthcheck-Teilaussage (a) übrig.
3. **121 vs. frühere K-4-Einstufung.** Das Register stufte `c` nach `K-4` als
   **NICHT VERIFIZIERBAR** ein. Die Live-Prüfung zeigt: nicht „nicht
   verifizierbar", sondern **widerlegt** (Beat dispatcht nachweislich). Die
   K-4-Fußnote ist damit zu korrigieren.
4. **143 vs. #1019 (Kontrolle).** `143` ist korrekt als `DUPLIKAT #1019` geführt;
   die Prämisse (Laufzeitfehler durch dimensionsfremde Vektoren) ist widerlegt
   (4× `vector(384)`). Bestätigt.
5. **148 vs. 241.** `AUD-2026-09-148` (WP-1c) und `AUD-2026-09-241` (WP-6a)
   zitieren dieselben Compose-Defaults (`:73,1020,1053`); Register-Doppelführung
   (bereits in `REVIEW_WP6A.md` vermerkt).
6. **Zitatfehler.** `139`: Orte `:139,147` zeigen aktuell auf Honcho-Env, nicht auf
   Healthchecks (Zeilenverschiebung). `147`: Zahl `shared_buffers=160 MB` nicht
   reproduzierbar (live 128 MB). `132`: `5914` nicht reproduzierbar (live 2425).
7. **Zahl `648/831` vs. live `659/843`.** Prinzip (Version-Zähler ohne TTL)
   bestätigt; die Absolutwerte sind Snapshots und um ~10 gestiegen.

## 3. Verdikt-Zählung (Zielbefunde, n=20)

- **BESTAETIGT: 13** — 120, 131, 132, 133, 135, 136, 138, 139, 140, 141, 143, 146, 148
- **TEILWEISE: 5** — 130 (→Low), 142 (→Low), 144, 145, 147 (→Low)
- **UEBERZOGEN: 1** — 134 (→Low)
- **FALSCH: 1** — 121 (Headline; Rest Low)
- NICHT VERIFIZIERBAR: 0 · KEIN REQOGNILOOM-BEZUG: 0

Korrigierte Schweregrade: `121` Critical → **Low** (Rest), `130` Medium → **Low**,
`134` Medium → **Low**, `142` Medium → **Low**, `147` Medium → **Low**.

## 4. Key-Verdikte

1. **AUD-120 BESTAETIGT (Critical) — der stärkste Befund hält der Gegenprüfung
   stand.** Isolierte Messung mit der Projekt-eigenen Celery/kombu-Version:
   1 Nachricht ⇒ 4 Zustellungen; Live-Broker set `_kombu.binding.default` enthält
   4 Mitglieder mit `routing_key='default'`; Worker-Banner und `-Q default,llm,events,memory`
   belegen, dass alle vier konsumiert werden. „Jede Task läuft 4×" ist korrekt.
2. **AUD-121 FALSCH — Beat ist nicht tot.** Live: DB-Zähler
   (`dispatch-outbox-events` 223653, Heartbeat 18652) **schreiten voran**, der
   Worker führt `application.dispatch_outbox_events` **alle 5 s** aus, das
   Zählerverhältnis ist exakt 12:1 (5 s : 60 s). Die Register-Evidenz
   „0× `Sending due task`" ist ein **Log-Artefakt**, kein Funktionsnachweis.
   Verbleibend: (a) Healthcheck prüft nur Prozessexistenz (Low), (b) = Duplikat
   von 125/270.
3. **AUD-130/134/147 überzeichnet.** Die no-TTL-Keys sind bewusste
   Versionszähler (Resultate haben TTL 3600 + `delete`), UUID-Namespacing ist
   strukturell eindeutig, und `shared_buffers` ist live 128 MB statt 160 MB.
4. **AUD-131/133/136/141/142 bestätigt bzw. real, aber teils niedriger.** Kein
   Cache-TIMEOUT, MCP-Sessions in db0 (FLUSHDB-Risiko), keine Digest-Pins, kein
   Exporter/Tracing und `.env.example`-Drift (7 statt 8) sind real.
5. **AUD-138 live bestätigt.** `docker compose … build` auf der Release-Datei →
   `"No services to build"`, **exit 0**, danach `build.sh:94` „Build completed".

## 5. NEU-AUDIT-LUECKE

- **Celery-Beat-Beobachtbarkeit ist kaputt — und die Audit-Evidenz hing daran.**
  Bei laufendem Beat (`-l info`, DatabaseScheduler) erscheinen **0**
  `Scheduler: Sending due task`-Zeilen, obwohl der Scheduler nachweislich
  dispatcht (DB-Zähler fortschreitend). Ein funktionierender Dienst ist damit
  aus den Logs **nicht** erkennbar. Das ist die eigentliche Betriebs-Lücke, die
  `AUD-121` hätte adressieren sollen: der Healthcheck (`pgrep`) und das
  Beat-Log liefern beide keine Funktionsaussage; nur die
  `django_celery_beat_periodictask`-Zähler (oder der #822-Heartbeat) tun es.
  **Kein eigenes Finding im Register** — Neuerfassung empfohlen
  (Medium, Observability; prüfen, ob `beat_log_sent_tasks`/Logger-Konfiguration
  die INFO-Zeile verschluckt).
- **Register-Doppelführung 121(b)/125/270 und 148/241** verzerrt die Zählung
  (siehe §2). Empfehlung: `121` auf die Healthcheck-Teilaussage reduzieren und
  (b) auf `125` verweisen.

## 6. Nicht verifizierbar / offen

| Punkt | Grund |
|---|---|
| `mcp:session:*`-Live-Zahl (Register: 4) | aktuell keine aktiven SSE-Sessions; Speicherort statisch belegt (db0) |
| `celery-task-meta-*`-Zahl 5914 | Snapshot; live 2425 (Cleanup/Neustart) |
| `shared_buffers` 160 MB des Audit-Laufs | aktuelles Volume zeigt 128 MB (Default) und keine `auto.conf`-Zeile |
| Ursache der fehlenden `Sending due task`-Logzeile | erfordert Beat-Debug/Neustart → nicht durchgeführt (Kollisionsvermeidung mit Live-Agent) |

**Neue Dateien:** nur diese (`docs/audit/2026-09/review/evidence/REVIEW_WP1C_SUPP.md`).
**Stack:** 11 laufende Container unverändert; keine Redis-Stopps, keine Neustarts,
kein Push.
