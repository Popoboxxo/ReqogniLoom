---
type: REVIEW
scope: WP-1c — Infrastruktur-/Betriebsebene (PostgreSQL/pgvector, Redis, Celery, Compose-Profile, Backup/Restore, Release-Kette, Health, Observability)
status: final
date: 2026-09-29
author_agent: devops-engineer
branch: chore/system-audit-2026-09
commit: 3dcc80d8
---

# AUDIT_INFRASTRUCTURE — WP-1c Tiefenaudit der Betriebsebene

**Ampel: 🔴 ROT**

Der Kern dieser Betriebsebene ist **funktionsfähig, aber die asynchrone Hälfte
ist stillgelegt und die dokumentierte Notfall-Wiederherstellung ist tot.**
Zwei Befunde sind Critical, weil sie Produktionsverhalten aktiv und
falsch-signalisieren: alle vier Celery-Queues sind identisch gebunden (jede
Task läuft 4×), und `celery-beat` hat in der gesamten Laufzeit des geprüften
Stacks **keine einzige** Aufgabe dispatcht, während `/health/` durchgehend
`200 {"status":"ok"}` meldet. Die Backup-Mechanismus-Seite ist dagegen
**erfolgreich getestet**: ein echter Restore in eine isolierte Datenbank
reproduzierte 15 von 15 Tabellenzahlen — die beiden dokumentierten
Operator-Skripte `backup.sh`/`restore.sh` können dagegen nie erfolgreich sein.

Keine Produkt-Fixes, kein Build/Deploy, kein Push. Der laufende Stack wurde
nur lesend angefasst; der einzige geschriebene Container
(`wp1c-restore-pg` + Volume) wurde nach dem Test gelöscht. Alle 12 Container
des Stacks und der Parallel-Audits sind unverändert `Up`.

---

## 1. Finding-Tabelle

Schweregrade: **Critical** / **High** / **Medium** / **Low** / **Info**
Reconciliation gegen die maßgeblichen VOR-AUDIT-Tracks und die
Issue-Basis (`docs/audit/2026-09/AUDIT_EVIDENCE/issue-inventory.md`, 608 Issues /
40 offen) sowie `AUD-2026-09-030/031` und Issue #1019 / #171 / #826 / #1074.

| ID | Schweregrad | Klassifikation | CR-Track / Issue | Ort | Kurztitel |
|----|-------------|----------------|------------------|------|-----------|
| `AUD-2026-09-120` | **Critical** | Celery / Message-Semantik | **NEU** (kein Vor-Audit-Track; CR-35-Nähe) | `backend/reqogniloom/celery.py:31-36` | Alle 4 Queues identisch gebunden → **jede Task läuft 4×** |
| `AUD-2026-09-121` | **Critical** | Celery / Scheduler | **BESTAETIGT** Klasse #171 (geschlossen 2026-07-29, Wirkung besteht fort) | Live: `celery-beat`-Log 0× `Sending due task`; `settings.py:817-830` | Beat dispatcht **nie** — gesamter 5-s/60-s/Monats-Schedule tot |
| `AUD-2026-09-122` | **Critical** | Backup / Totcode | **NEU** (CR-37) | `scripts/backup.sh:84-87` | `backup.sh` ist permanent nicht ausführbar (`exit 1`) |
| `AUD-2026-09-123` | **Critical** | Backup / Restore | **NEU** (CR-37) | `scripts/restore.sh:183,186,198-213` | Backup-Datei wird nie in den Container kopiert; `psql -f` liest Datei statt stdin |
| `AUD-2026-09-124` | High | Backup / Restore | **NEU** (CR-37) | `scripts/restore.sh:49,116` vs. `deploy/docker-compose.yml:372` | Format-/Ort-Inkompatibilität: `.sql.gz` im Volume vs. `*.dump\|*.sql` in `./backups` |
| `AUD-2026-09-125` | High | Celery / Registrierung | **NEU** | `backend/audit/archive.py:448` vs. `celery.py:45` | `audit.archive_lifecycle_manager` beim Worker **nicht registriert** |
| `AUD-2026-09-126` | High | Celery / Ack-Semantik | **NEU** (kein Vor-Audit-Track; CR-35-Nähe) | live `app.conf.task_acks_late=False`; 7 Task-Dateien | pre-ack + kein Retry ⇒ Worker-Kill = **endgültiger** Task-Verlust |
| `AUD-2026-09-127` | High | Backup / Restore | **NEU** (CR-37) | `scripts/restore.sh:183` | Restore nicht atomar (`--clean --if-exists` in-place auf der Live-DB) |
| `AUD-2026-09-128` | High | Backup / Aufbewahrung | **NEU** (CR-37) | `deploy/docker-compose.yml:357,361,372` | 42-h-Horizont, kein Off-Host, keine Verschlüsselung, keine Medien/Uploads |
| `AUD-2026-09-129` | High | Health / Readiness | **BESTAETIGT + VERSCHAERFT** `AUD-2026-09-031` | `backend/reqogniloom/health.py:118-313`; `deploy/docker-compose.yml:642` | `/health/` prüft weder Cache **noch Worker/Beat**; `degraded` liefert HTTP **200** |
| `AUD-2026-09-130` | Medium | Redis / Cache-TTL | **NEU** (CR-35) | `backend/application/ai_derivation_service.py:396,500` | 648/831 Cache-Keys **ohne TTL** (`timeout=None`), nie invalidiert |
| `AUD-2026-09-131` | Medium | Redis / Kapazität | **NEU** (CR-35) | `deploy/docker-compose.yml:543,545`; `settings.py:879-884` | `noeviction`@256 MB ⇒ Cache-Writes scheitern mit OOM; kein `TIMEOUT`-Handling |
| `AUD-2026-09-132` | Medium | Redis / Result-Backend | **NEU** | live: 5914 `celery-task-meta-*` Keys | 24-h-Ergebnisaufbewahrung im Broker-DB, ungebremstes Wachstum |
| `AUD-2026-09-133` | Medium | Redis / Namespace | **NEU** (CR-36-Nähe) | live: `mcp:session:*` in db0 | MCP-Sessions teilen die Broker-DB ⇒ `FLUSHDB` zerstört laufende Sessions |
| `AUD-2026-09-134` | Medium | Redis / Key-Namespace | **NEU** | `settings.py:879-884` | Kein `KEY_PREFIX`/`KEY_FUNCTION` ⇒ Tenant-Trennung nur *zufällig* über UUIDs |
| `AUD-2026-09-135` | Medium | Compose / Log-Rotation | **NEU** | `deploy/docker-compose.yml:1015-1194` | 4 honcho-Services **ohne** `logging:` ⇒ unbegrenzte Logs |
| `AUD-2026-09-136` | Medium | Supply-Chain / Pinning | **BESTAETIGT** `CR-38` | `deploy/docker-compose.yml:567,953,1109` | Kein Image per Digest gepinnt; `honcho:latest` |
| `AUD-2026-09-137` | High | Supply-Chain / Provenienz | **BESTAETIGT** `CR-32`, `CR-38` | `.github/workflows/docker-publish.yml:102,145,168,183`; `ci.yml:4-7` | Kein Test-vor-Image-Vertrag; Scan≠Push-Artefakt; **kein** SBOM/Cosign/Provenance |
| `AUD-2026-09-138` | Medium | Release / Build | **BESTAETIGT** | `scripts/build.sh:88-92`; `deploy/docker-compose.yml` (0× `build:`) | `build.sh` meldet „Build completed" bei **exit 0** und 0 gebauten Images |
| `AUD-2026-09-139` | Medium | Konfiguration | **NEU** | `deploy/docker-compose.yml:139,147,933` | Keine getrennten Liveness-/Readiness-Checks; ein Endpoint ist beides und taugt für keines |
| `AUD-2026-09-140` | Low | Compose / Test-Overlay | **NEU** | `testing/docker-compose.test.yml:54-56` | `depends_on` ohne `condition: service_healthy` |
| `AUD-2026-09-141` | Medium | Observability | **NEU** (CR-35) | `settings.py:899-955`; `rest_api/urls.py:237`; kein OTel/Prometheus in `requirements` | Kein Exporter, kein Tracing, `LOG_LEVEL` nicht konfigurierbar |
| `AUD-2026-09-142` | Medium | Konfigurations-Drift | **NEU** (Nachfolger zu `fix/deploy-compose-env-drift`) | `.env.example` vs. 4 Compose-Dateien | 8 referenzierte Variablen fehlen in `.env.example` (u. a. `CELERY_CONCURRENCY`) |
| `AUD-2026-09-143` | Medium | Embedding / pgvector | **DUPLIKAT #1019** (geschlossen 2026-09-21) | `persistence/embedding_dimensions.py:84`; 4× `vector(384)` gemessen | Keine Laufzeitfehler möglich (Prämisse **WIDERLEGT**); Nicht-Default-Provider ⇒ stille Degradation |
| `AUD-2026-09-144` | Low | Datenbank / Index | **TEILWEISE** `CR-35` | `EXPLAIN` auf `pl_artifact`; `pg_indexes` | `created_at` unindiziert (Sort nötig), Composite-Index ungenutzt, 4 Duplikat-Indizes |
| `AUD-2026-09-145` | Low | Konfigurations-Drift | **NEU** | Release-Compose `:887` `--concurrency=4` vs. live `concurrency: 2` | Worker-Konfiguration Release-Compose ≠ laufender Stack |
| `AUD-2026-09-146` | Low | Dokumentation | **NEU** | `backend/llm_adapter/tasks.py:188-189` vs. `settings.py:347` | Stale Kommentar: „CONN_MAX_AGE is unset (Default 0)" — tatsächlich 60 |
| `AUD-2026-09-147` | Medium | PostgreSQL / Tuning | **NEU** (CR-35) | `deploy/docker-compose.yml:247-295`; `postgresql.auto.conf:3` | `max_connections=300` nur im Volume, nicht versioniert; `shared_buffers` 160 MB in 384 MB cgroup |
| `AUD-2026-09-148` | Low | Compose / Credentials | **NEU** | `deploy/docker-compose.yml:73,1020,1053` | Klartext-Default `honcho-dev-password` im Compose |
| `AUD-2026-09-149` | High | Prozess / Staging | **NEU** | keine Staging-Definition; `ci.yml`/`docker-publish.yml` 0× `environment:`/`concurrency:` | **Keine Staging-Stufe** zwischen CI und Produktion; keine Approval-Gate |

**Verteilung:** Critical 4 · High 8 · Medium 13 · Low 5 · Info 0 = **30 Findings**.

### 1.1 Reconciliation-Matrix (Pflicht)

| Vor-Audit-Aussage / Track | Verdikt | Begründung |
|---------------------------|---------|------------|
| `AUD-2026-09-030` — `CACHES` ohne `SOCKET_TIMEOUT` ⇒ unbegrenztes Hängen | **BESTAETIGT** | `settings.py:879-884` unverändert. **Verschärft:** `noeviction`@256 MB lässt Cache-Writes auch im Normalbetrieb scheitern, und es gibt **keinen** Fallback-Pfad (kein `DummyCache`, kein `KEY_PREFIX`-Failover, kein Circuit-Breaker) → `131` |
| `AUD-2026-09-031` — `/health/` prüft den Cache nicht | **BESTAETIGT + VERSCHAERFT** | Live: `{"status":"ok","warnings":[]}`. Es fehlen **auch** Worker und Beat → `129` |
| Embedding-Dimension: „dimensionsfremde Einbettung kann noch Laufzeitfehler auslösen" | **WIDERLEGT** | Alle 4 Spalten `vector(384)`; `EMBEDDING_VECTOR_DIMENSIONS`=384; **jeder** Write-Site guardt `len==dim` **vor** dem Schreiben (`requirement_service.py:894-902`, `trace_link_service.py:792-802`, `icd_manager.py:183-196`), Query-Guard in `search_service.py:572-582`. pgvector sieht nie einen falschen Vektor. **Rest:** stille Degradation = **DUPLIKAT #1019** → `143` |
| `build.sh` ist ein No-op | **BESTAETIGT + quantifiziert** | `No services to build`, **exit 0**, „Build completed"; 0 buildable Services in der Release-Compose, 5 im Merge mit dem Override → `138` |
| `migrate` führt 294 `django_migrations` aus | **BESTAETIGT** | exakt 294, jüngste `persistence.0102_…` |
| `CR-29` ASGI/nginx-Transport | **BLOCKED** | nicht WP-1c-Scope; kein eigener Befund |
| `CR-32` Release-/Provenienz-Gate | **BESTAETIGT** (3 Teilaussagen einzeln belegt) | kein `needs:`/`workflow_run`; `ci.yml` ohne Tag-Trigger; Scan und Push sind 2 getrennte `build-push-action`-Läufe; 0× sbom/cosign/provenance → `137` |
| `CR-35` Performance | **TEILWEISE** | Indizes mit 633 Stück und HNSW auf allen 4 Vektorspalten **vorhanden und wirksam** (EXPLAIN-Beleg). Ein Sort-Befund, ein Duplikat-Index-Befund. **Kein** Benchmark-Roulette → `144` |
| `CR-36` | **NEU** (kein eigene WP-1c-Aussage ableitbar) | in `131`, `132`, `133` subsumiert |
| `CR-37` Backup/Restore | **BESTAETIGT + VERSCHÄRFT + TEILWEISE ENTKRAFTET** | **Entkräftet:** der Sidecar ist funktionsfähig und der Restore ist **erfolgreich getestet** (15/15). **Verschärft:** gerade die *dokumentierten* Skripte sind tot (`122`, `123`, `124`) und die Abdeckung ist unvollständig (`128`) |
| `CR-38` Lieferkette | **BESTAETIGT** | kein Digest, kein SBOM, kein Signing → `136`, `137` |
| `CR-45` Release-Provenienz | **BESTAETIGT** | dieselbe Beweislage wie `CR-32`: `ci.yml` ohne Tag-Trigger, `docker-publish.yml` ohne `needs:`/`workflow_run`/`concurrency:`, Scan und Push als zwei getrennte Build-Läufe, 0× SBOM/Cosign/Provenance → `137` |
| `CR-31` E2E testet nicht ASGI/nginx | **BLOCKED** | WP-1c-Scope |
| Issue **#1019** Nicht-384-Embeddings | **DUPLIKAT** | exakt dasselbe Residuum → `143` |
| Issue **#171** „periodische Tasks laufen nie" | **BESTAETIGT** (geschlossen, Wirkung fortbestehend) | → `121` |
| Issue **#1074** Backup-Härtung | **BESTAETIGT WIRKSAM** | 8/8 Dumps `status=ok`, 98→100 COPY-Blöcke, `prune_old` korrekt; Restore-Test bestanden |
| Issue **#823** `fix/backup-gzip-823` | **RELATIVIERT** | betraf `admin_ops`-DR-Backups, **nicht** `scripts/backup.sh`; die Sidecar nutzt `gzip -9` (`deploy/docker-compose.yml:436`) und ist korrekt. `backup.sh` hat gar kein gzip — es ist ein toter Wrapper |
| Offene Issues (#792 RFC usw.) | deckt **keinen** dieser Befunde ab | alle 40 offenen Issues geprüft |

---

## 2. Restore-Test — hat er funktioniert?

### **JA. 15/15 Tabellen, 0 Fehler.**

`reqogniloom_20260930_034136.sql.gz` (10 012 937 B) wurde in eine **isolierte
Wegwerf-Datenbank** (PG 16.15, eigenes Volume, kein Host-Port, kein
Compose-Netz) restauriert: `gzip -t` OK → 54 070 604 B SQL → 100 COPY-Blöcke →
`psql exit 0`, **0 ERROR**, 5 s.

| Tabelle | VOR | NACHHER | Δ |
|---------|-----|---------|---|
| `pl_artifact` | 3432 | 3432 | 0 |
| `audit_entry` | 8148 | 8148 | 0 |
| `at_refresh_token` | 6292 | **6282** | **−10 (erklärt)** |
| `at_api_key` | 201 | 201 | 0 |
| `pl_artifact_version` | 4117 | 4117 | 0 |
| `we_item_state` | 3306 | 3306 | 0 |
| `pl_token_usage_record` | 39 | 39 | 0 |
| `pl_tenant` | 6 | 6 | 0 |
| `ad_workspace_definition` | 420 | 420 | 0 |
| `pl_requirement` | 2111 | 2111 | 0 |
| `pl_tracelink` | 2099 | 2099 | 0 |
| `icd_icd` | 105 | 105 | 0 |
| `mem_memory_entry` | 2 | 2 | 0 |
| `as_domain_event_outbox` | 6861 | 6861 | 0 |
| `django_migrations` | 294 | 294 | 0 |

Die **einzige** Abweichung ist `at_refresh_token` −10: VOR um 04:31 gemessen,
Backup von 03:41 — 50 Minuten, in denen die Parallel-Audits Tokens erzeugt
haben. Kein Datenverlust, sondern Snapshot-Abstand. `vector`-Extension im Ziel
korrekt erzeugt (`CREATE EXTENSION` im Log), `pl_requirement.embedding` =
`vector(384)`, pgvector 0.8.6 (Image-Patch; Funktion identisch).

**Damit ist der „ungetesteter Backup-Pfad" für die Sidecar-Mechanik
entkräftet** — er ist getestet und funktioniert.

**Aber: die dokumentierte Notfall-Wiederherstellung ist tot.** Es gibt
**drei** unabhängige Gründe, warum ein Operator im Ernstfall nicht
wiederherstellen kann:

1. `scripts/backup.sh` bricht **immer** mit `exit 1` ab
   (`:84-87`, verlangt eine Datei, die es nie gab).
2. `scripts/restore.sh` findet nichts: es sucht `*.dump|*.sql` in einem
   Host-Verzeichnis `./backups/` (**existiert nicht**), während der Sidecar
   **`.sql.gz` in ein Docker-Volume** schreibt.
3. Selbst mit passender Datei scheitert der Restore, weil das Skript die Datei
   **nie in den Container kopiert** — es leitet nur stdin um, während
   `pg_restore …/tmp/backup.dump` und `psql -f /tmp/backup.sql` **Dateipfade**
   lesen. Isoliert reproduziert:
   `psql: error: /tmp/backup.sql: No such file or directory`, exit 1.

Die einzige funktionierende Restore-Anleitung ist der eine Satz im
Compose-Kommentar (`:304`):
`gunzip -c <dump>.sql.gz | psql -h postgres -U $DB_USER -d $DB_NAME`.
Sie ist korrekt — und ich habe sie erfolgreich ausgeführt.

**Was NICHT getestet wurde:** das Abbruchverhalten eines Restores mitten drin
(die eigentliche Nicht-Atomizität) — das hätte die Live-Datenbank gefährdet.
**BLOCKED**, nicht als PASS gewertet.

---

## 3. Compose-Profile — valide und startbar

| Variante | `config --quiet` | Startbar | Dienste |
|----------|------------------|----------|---------|
| `deploy/docker-compose.yml` (Release) | **exit 0** | ja | 9 |
| Release + `deploy/docker-compose.override.yml` (Dev) | **exit 0** | ja | 9 (5 davon buildbar) |
| `deploy/docker-compose.minimal.yml` | **exit 0** | ja | 5 |
| Release + `testing/docker-compose.test.yml` | **exit 0** | ja | 11 |
| Profil `honcho` | **exit 0** | ja | 13 |
| Profil `bluepencil` | **exit 0** | ja | 10 |
| `honcho` + `bluepencil` kombiniert | **exit 0** | ja | 14 |

**Alle 5 realen Betriebs-Pfade und beide Profile sind valide. Kein defektes
optionales Profil.** Zwei *nicht*-validen Aufrufe sind by design (Overlays ohne
Basis).

**Stärkste Einzelstellen des Compose-Setups** (als PASS zu vermerken):

* **Jede** Default-`depends_on`-Bedingung trägt ein explizites
  `condition: service_healthy` bzw. `service_completed_successfully` — inklusive
  der ungewöhnlich korrekten Kette `postgres-backup → migrate:
  service_completed_successfully` (`:494-500`), die den #1074-Fall „erster Dump
  auf frisch migrierter, noch leerer DB" strukturell verhindert.
* **Kein** `privileged`, **kein** `network_mode: host`, Postgres/Redis
  **nicht** auf dem Host publiziert — konsistent mit der eigenen
  Sicherheitsregel (`:42`).
* **Keine Klartext-Secrets** in den Compose-Dateien (alle `${VAR}` /
  `env_file`); `deploy/.env` korrekt gitignored (`.gitignore:18`) und
  untracked.
* `pg_hba.conf`: `host all all all scram-sha-256` als Standardpfad.
* Least-privilege-Trennung: `backend`/`celery`/`celery-beat` als `DB_APP_USER`,
  nur `migrate` als Superuser.
* AOF an **und** `/data` auf benanntem Volume — sonst wäre die Queue bei jedem
  Recreate stillschweigend verloren.
* Log-Rotation auf 11 von 15 Services mit expliziter Begründung im Header.

---

## 4. PostgreSQL + pgvector

| Aspekt | Befund |
|--------|--------|
| Version | PG **16.15**, pgvector **0.8.5** ✔ |
| `shared_buffers` | **160 MB** = 42 % des 384-MB-cgroup-Limits; `effective_cache_size` sagt Postgres 5 GB (4-fach überzeichnet) → `147` |
| `max_connections` | 300, aber **nur** in `postgresql.auto.conf` (once `ALTER SYSTEM` im Volume), **kein** `command:` im Compose ⇒ nicht versioniert, `down -v` setzt auf 100 zurück → `147` |
| `statement_timeout` | Cluster-Default 0, **aber** Django setzt 30 s (`settings.py:359`), `migrate` bewusst 0 (`:774`) ⇒ **kein Befund**, sauber getrennt |
| `work_mem` 4 MB / `maintenance_work_mem` 64 MB | Defaults; 64 MB ist für HNSW-Indexbau in einem 512-MB-`migrate`-Container knapp → `147` |
| Embedding-Dimension | 4/4 Spalten `vector(384)`, konsistent, **keine Laufzeitfehler möglich** → `143` |
| Indizes | **633** gesamt, **4** HNSW (auf allen 4 Vektorspalten), im EXPLAIN **wirksam** ⇒ **kein** pauschaler Mangel |
| `pl_artifact` Listen-Query | `Sort` nötig (kein `created_at`-Index), vorhandener Composite-Index `idx_artifact_tnt_ws_type` **nicht gewählt**; 0,055 ms @ 3432 Zeilen ⇒ prognostisch, **kein** Engpass heute → `144` |
| `audit_entry` Listen-Query | `Index Scan Backward using idx_audit_tenant_ts` — **optimal**, 5 Buffers, kein Sort ⇒ **PASS** |
| Doppelindizes | 4 exakte Duplikate auf `pl_artifact` (`parent_id` ×2, `lifecycle_status` ×2, `priority` ×2) ⇒ Schreib-Overhead ohne Nutzen → `144` |

---

## 5. Redis

| Aspekt | Befund |
|--------|--------|
| Version | **7.4.11** ✔ |
| Trennung | Broker+Result = db0, Cache = db1 ⇒ **PASS** (`settings.py:862-864`) |
| **db0** | 5914 `celery-task-meta-*` (24-h-TTL, ungebremst) + **4 `mcp:session:*`** ⇒ Namespace-Kollision mit dem Broker → `132`, `133` |
| **db1** | 831 Keys, davon **649 ohne TTL**; 648 davon `llm_derivation_ver:{artifact_id}` mit `cache.set(…, None)`, **kein `cache.delete()`** im Repo ⇒ ein Key pro Artefakt, unbegrenzt → `130` |
| `maxmemory-policy` | `noeviction`@256 MB — für den Broker **richtig** begründet (`:510-514`), für den Cache ein **Nebeneffekt**: bei Volldruck scheitern `cache.set()` mit `OOM command not allowed`, und `CACHES` hat kein `TIMEOUT`, das das abfängt → `131` |
| `CACHES` | **kein** `SOCKET_TIMEOUT`, **kein** `TIMEOUT`, **kein** `KEY_PREFIX`, **kein** `KEY_FUNCTION` → `030` BESTAETIGT, `134` |
| Tenant-Sicherheit | Namespace enthält **keine** Tenant-Komponente. Heute **keine Kollision** (alle Keys UUID-PK), aber die Invariante ist **nicht kodiert** — ein Slug- oder Composite-Key kollidiert sofort → `134` |
| Fallback bei Ausfall | **keiner**: kein `DummyCache`, kein Sentinel/Cluster, kein Circuit-Breaker. Verhalten ist **Hängen**, nicht Fehlschlag |
| Hit-Rate | 35,4 % (5866 hits / 10714 misses) über 6 h Container-Lebensdauer — als Messwert festgehalten, kein Befund |
| `requirepass` | leer, `protected-mode no`, `bind *` — vertretbar, da **kein Host-Port** publiziert ist |

---

## 6. Celery

**Task-Inventar: 7 Tasks. 0 mit Retry/Backoff. 0 mit DB-Transaktionsgrenze.
0 mit Idempotenzschlüssel.**

| # | Task | Datei:Zeile | Queue | Retry | Idempotenz |
|---|------|-------------|-------|-------|------------|
| 1 | `application.dispatch_outbox_events` | `application/tasks.py:20` | events | ✗ (schluckt alles, `:36-38`) | `FOR UPDATE SKIP LOCKED` |
| 2 | `audit.archive_lifecycle_manager` | `audit/archive.py:448` | default | ✗ | fraglich (destruktiv) |
| 3 | `admin_ops.record_celery_beat_heartbeat` | `admin_ops/tasks.py:18` | default | ✗ | ja |
| 4 | `context_graph.rebuild_workspace_graph` | `context_graph/tasks.py:19` | default | ✗ | nein (Vollrebuild) |
| 5 | `llm_adapter.run_capability` | `llm_adapter/tasks.py:77` | llm | ✗ | nein (Kosten/Token-Usage) |
| 6 | `memory.consolidate_interaction` | `memory/tasks.py:305` | memory | ✗ | Dubletten-Dedup |
| 7 | `resilience.execute_optional_task` | `resilience/tasks.py:41` | default | ✗ | nein |

**Queue-Fan-out (Critical):** `celery.py:31-36` deklariert vier Queues ohne
expliziten `Exchange`/`routing_key`. Celery füllt für **alle vier** den
Default ein — live gemessen: `exchange=default, routing_key=default` ×4, im
Worker-Banner identisch, in Redis genau **ein** `_kombu.binding.default`.
Isolierter Beweis: **1 publizierte Nachricht → 4 Zustellungen → 4 Ausführungen.**

**Ack-Semantik (High):** `task_acks_late=False`, `task_reject_on_worker_lost=False`,
`worker_prefetch_multiplier=4`, `broker_transport_options={}` (kein
`visibility_timeout`). Ein `SIGKILL`/OOM-Kill im Taskfenster ⇒ Nachricht
**endgültig verloren**, inkl. bis zu 3 weiterer vorab bestätigter Nachrichten.
`stop_grace_period: 60s` deckt ordentliche Stops ab, **nicht** OOM-Kill.

**Verstärkungsfaktor:** 4 (Fan-out) × 2 (at-least-once) = **bis zu 8
Ausführungen** pro logischer Task.

**Beat (Critical):** `CELERY_BEAT_SCHEDULE` (3 Einträge) wird wegen
`DatabaseScheduler` **zur Laufzeit ignoriert** und nur per `post_migrate` in
`django_celery_beat_periodictask` gespiegelt — eine Code-Änderung am Takt wirkt
erst nach einem `migrate`. Die Tabelle hat 4 Zeilen. Trotzdem: **0× `Sending
due task`** im gesamten Beat-Log. Der Healthcheck (`pgrep -f 'celery.*beat'`)
prüft nur Prozessexistenz, deshalb `healthy` bei Totalfunktionslosigkeit.

**Registrierungslücke (High):** `audit.archive_lifecycle_manager` fehlt im
Worker-Task-Set, weil der Task in `audit/archive.py` statt `audit/tasks.py`
liegt und `autodiscover_tasks()` nur `<app>/tasks.py` importiert. Die monatliche
Audit-Archivierung ist ein garantiertes No-op — `audit_entry` hat bereits
**8148** Zeilen.

**Konfigurationsdrift (Low):** Release-Compose pinnt `--concurrency=4`, der
laufende Worker meldet `concurrency: 2 (prefork)`.

---

## 7. Release-/Deploy-Kette

* **`build.sh` ist ein No-op** (Critical-Kontext: Medium): `No services to
  build`, **exit 0**, Ausgabe „Build completed". 0 buildbare Services in der
  Release-Compose, 5 im Merge mit dem Override, 2 im Test-Overlay. Die drei
  Build-Metadaten werden exportiert, aber von keinem Service konsumiert.
* **Kein Test-vor-Image-Vertrag:** `ci.yml` löst **nicht** auf Tags auf;
  `docker-publish.yml` hat **null** `needs:`, `workflow_run`, `concurrency:`
  und **einen** Job. Ein Tag-Push auf einem Commit ohne CI-Status publiziert
  ein Image.
* **Scan ≠ Push-Artefakt:** Trivy (`:145`, `exit-code: 1` bei CRITICAL/HIGH —
  ein echtes Gate) läuft gegen ein per `load: true` geladenes Image; der Push
  (`:168`/`:183`) ist ein **zweiter, unabhängiger** `build-push-action`-Aufruf.
  Weder Scan- noch Push-Digest werden festgehalten oder weitergegeben.
* **Kein SBOM, kein Cosign, keine Provenance:** `sbom|cosign|provenance|attest|slsa`
  → **0 Treffer** in allen 5 Workflows.
* **Kein Digest-Pinning** auf der Konsumentenseite; `honcho:latest` ist der
  eine Ort, an dem ein Image-Update ohne Compose-Änderung einziehen kann.
* **MTTG:** Der einzige Vulnerability-Scan hängt an einem **Tag**-Trigger ⇒
  für normale Commits nicht erreichbar. Kein Dependency-Scan (`pip-audit`/
  `npm audit`) und kein SAST-Tool in `ci.yml`. Konkrete MTTG-Werte sind
  **BLOCKED** (kein CI-Lauf dieses Branches im Messfenster) — **nicht** als PASS gewertet.
* **`.env`-Drift:** 8 in Compose referenzierte Variablen fehlen in
  `.env.example`, darunter `CELERY_CONCURRENCY` — dessen Wert laut
  Compose-Kommentar (`:868-881`) das Memory-Limit **mitbestimmt** und daher
  niemals allein geändert werden darf.
* **Positiv:** `ci.yml` hat einen Ratchet-Job `requirements-drift-check`, und
  `deploy/verify-backup-command.sh` (#1074) existiert und ist konsistent
  verreferenziert.

---

## 8. Health / Readiness / Observability

**Es gibt genau einen Health-Endpunkt** (`/health/`,
`backend/reqogniloom/urls.py:28`), der zugleich Liveness **und**
Readiness-Proxy ist. Live: `200 {"status":"ok","warnings":[]}` — während
`celery-beat` seit 3+ Tagen nichts dispatcht.

| Abhängigkeit | geprüft? | Verhalten bei Ausfall |
|--------------|----------|-----------------------|
| PostgreSQL | **JA** | `degraded`, aber **HTTP 200** |
| Memory-Backend | JA | `degraded` |
| Embedding-Dimension | JA | nur `warnings` |
| LLM-Env / CSRF / Workflows | JA | nur `warnings` |
| **Redis / Cache** | **NEIN** | nicht erkannt |
| **Celery-Worker** | **NEIN** | nicht erkannt |
| **Celery-Beat** | **NEIN** | nicht erkannt |

Weil `curl -f` nur bei HTTP ≥ 400 fehlschlägt, bleibt der `backend`-Container
bei Datenbankverlust `healthy`, und `frontend` startet ebenfalls
(`depends_on: backend: service_healthy`).

**Empfehlung (nicht implementiert):** `/livez` (nur Prozess, keine externen
Calls) und `/readyz` (DB **+** Redis **+** Queue; 503 bei Fehler),
`/health/` als Detail-Diagnose.

**Observability-Stand:**

| Pillar | Status |
|--------|--------|
| Logging | **PASS** — `pythonjsonlogger`, `request_id` in jeder Zeile, Rotation 10m×3 auf 11/15 Services. Lücke: `LOG_LEVEL` hart auf `"INFO"` kodiert, kein Env-Hebel; 4 honcho-Services ohne Rotation |
| Metriken | **kein Exporter.** `/metrics/` existiert nicht (404). `/api/v1/metrics/` ist ein **authentifizierter** REST-Proxy auf `se_metrics.compute_metrics` (SE-Coverage pro Workspace) — **nicht** Prometheus. `grep prometheus\|opentelemetry\|sentry` in `requirements`/`pyproject`: **0 Treffer** |
| Tracing | **nicht vorhanden.** Kein OTel, kein `traceparent`. `request_id` ist Request-Korrelation, **keine** distributed Trace; die Celery-Task-ID erscheint nirgends in den Anwendungs-Logs |
| Alerting | **nicht vorhanden** (kein Alerting-Pfad im Stack) |
| Secrets in Logs | **kein Befund** (Stichprobe: Tenant-UUIDs, keine Keys; `PGPASSWORD` korrekt als Env statt in der Kommandozeile) |

WP-1ds „782 KB ungepaged" ist damit aufgeklärt: authentifiziert (401 ohne JWT),
aber es ist **Nutz**-Daten, kein Health- oder Monitoring-Signal.

---

## 9. Staging-Validierung

| Check | Methode | Ergebnis |
|-------|---------|----------|
| Staging-Umgebung existiert | Scan der Deploy-Definitionen | **NEIN** — es gibt `deploy/` (Release), `deploy/docker-compose.minimal.yml` und `deploy/docker-compose.override.yml` (Dev), aber **keine** Staging-Definition und **keine** CI-Staging-Pipeline. `docker-compose.test.yml` ist laut `AGENTS.md` ein CI-/Lokaler Test-Overlay, **kein** Deployment-File |
| DB-Migrationen gestaged | `migrate`-Service, 294 Migrationen | **TEILWEISE** — die Migrationen laufen in **jedem** Ziel inkl. Produktion über denselben `migrate`-Service. Kein Staging-Zwischenschritt, kein `migrate`-Gate zwischen Staging und Produktion. Bei einer fehlerhaften Migration ist Produktion direkt betroffen |
| Config-Parität Staging ↔ Produktion | Diff | **nicht anwendbar** (kein Staging) |
| Bypass-Erkennung (direkt nach Produktion) | Scan der Pipelines | **NEIN** — der einzige Deployment-Weg ist `docker compose up` gegen `deploy/docker-compose.yml`; es gibt **keine** Approval-Gate, **keinen** `environment:`-Schutz und **kein** Verbot des Direktpfads. `ci.yml`/`docker-publish.yml` enthalten **null** `concurrency:`- und **null** `environment:`-Blöcke |

⇒ **Staging-Validierung existiert nicht.** Das ist keine Konfigurations-
Abweichung, sondern eine fehlende Umgebungsstufe. Wird als
**`AUD-2026-09-149`** geführt (High).

---

## 10. Empfehlungen (priorisiert, nicht umgesetzt)

**Sofort (Betriebssicherheit)**

1. **Celery-Queue-Bindings explizit machen** — pro Queue ein eigener
   `Exchange` + `routing_key` (`celery.py:31-36`). Behebt die 4-fache
   Ausführung und stellt die in `celery.py:16-30` begründete Skalierbarkeit
   wieder her. *(`120`)*
2. **Beat-Dispatch überhaupt erst herstellen** und die Ursache im Log
   verifizieren. Danach `CELERY_BEAT_SCHEDULE` entweder auf den
   `Scheduler`-basierten Betrieb umstellen oder den Seed-Pfad explizit
   dokumentieren und testen. *(`121`)*
3. **`audit.archive_lifecycle_manager` nach `audit/tasks.py` verschieben** (oder
   `import_tasks` konfigurieren). *(`125`)*
4. **`/readyz` einführen** und es in `backend`'s und `frontend`'s
   `depends_on` verwenden; `degraded` auf HTTP 503 heben. *(`129`, `139`)*
5. **`scripts/restore.sh` entweder reparieren oder löschen** und durch eine
   einzige, getestete Anleitung ersetzen. Aktuell ist der dokumentierte
   Notfallpfad **nicht ausführbar**. *(`122`, `123`, `124`, `127`)*

**Kurzfristig (Härtung)**

6. `CACHES`: `SOCKET_TIMEOUT`, `TIMEOUT` und `KEY_PREFIX`/`KEY_FUNCTION`
   (tenantbewusst) setzen. *(`030`, `131`, `134`)*
7. `task_acks_late=True` + `task_reject_on_worker_lost=True` **oder** bewusste
   Begründung des Pre-acks; `broker_transport_options.visibility_timeout` setzen.
   *(`126`)*
8. `llm_derivation_ver` mit TTL versehen oder beim Artefakt-Löschen
   invalidieren. *(`130`)*
9. `SOCKET_TIMEOUT`/`OOM`-Fehler vom Cache behandeln, statt sie zu schlucken.
   *(`131`)*
10. MCP-Sessions aus db0 in eine eigene logische DB verschieben, damit
    `FLUSHDB` auf dem Broker sie nicht zerstört. *(`133`)*
11. `max_connections`, `shared_buffers` und `maintenance_work_mem` als
    versionierte Compose-`command:`-Argumente ausdrücken; `effective_cache_size`
    an die cgroup angleichen. *(`147`)*
12. `logging:`-Block auch für die 4 honcho-Services; `restart:` für
    `honcho`/`honcho-postgres`/`honcho-redis`. *(`135`)*

**Mittelfristig (Lieferkette)**

13. **Test-vor-Image-Vertrag** herstellen: `docker-publish` von
    `workflow_run`/`needs` auf CI-Erfolg abhängig machen **und** `ci.yml` auf
    Tags erweitern. *(`137`)*
14. **Scan und Push in einem `build-push-action`-Aufruf** vereinen
    (`push: true, scan: true`) und den erzeugten Digest als Artefakt sichern.
    SBOM (`sbom: true`) und keyless `cosign sign` ergänzen. Compose auf
    `@sha256:` umstellen. *(`136`, `137`)*
15. Dependency-/SAST-Scan in `ci.yml` ergänzen, damit MTTG auch für normale
    Commits erreichbar ist. *(`137`)*
16. `build.sh` entweder auf den Override-Merge umstellen oder entfernen; in
    jedem Fall darf es bei 0 gebauten Images **nicht** „Build completed"
    melden. *(`138`)*
17. Einen echten **Staging-Tritt** zwischen CI und Produktion einführen
    (Deployment-Runbook + Approval). *(`149`)*
18. `LOG_LEVEL` als Env, `exporter`/Metrics und Tracing ergänzen. *(`141`)*
19. Off-Host- und verschlüsselte Backup-Kopie; Retention zeit- statt nur
    anzahlbasiert; Medien-/Upload-Volume in die Sicherung aufnehmen. *(`128`)*
20. `.env.example` um die 8 fehlenden Variablen ergänzen, insbesondere
    `CELERY_CONCURRENCY`. *(`142`)*

---

## 11. Evidenz-Dateien

| Datei | Inhalt |
|-------|--------|
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-compose-validation.md` | Validierung je Profil, Compliance-Matrix, Ports/Privileges, Image-Pinning, `.env`-Drift |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-redis-config.md` | Redis-Identität, db0/db1, TTL-Verteilung, Tenant-Namespace, Ausfallverhalten |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-celery-config-and-tasks.md` | Live-`app.conf`, Queue-Fan-Out-Beweis, Beat-Nachweis, Task-Inventar, Ack-Semantik |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-restore-test-protocol.md` | **Restore-Test-Protokoll** mit Vorher/Nachher-Zahlen, `restore.sh`-Defektbeweise |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-postgres-pgvector-indexes.md` | Parameter, `pg_hba`, Embedding-Dimension, 3 EXPLAIN-Pläne, Index-Inventar |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-health-observability-matrix.md` | Live-Endpunkt-Proben, Health-Matrix, Liveness/Readiness, Logging, Tracing |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-release-deploy-chain.md` | `build.sh`-Quantifizierung, Compose-Drift, CI-Provenienz, MTTG |

---

## 12. Was NICHT geprüft werden konnte

| Punkt | Grund | Klassifikation |
|-------|-------|----------------|
| **Abbruchverhalten eines Restores mitten drin** (die eigentliche Nicht-Atomizität) | `pg_restore --clean --if-exists` zielt per `scripts/restore.sh:198/206` auf den **Live**-Postgres-Container; ein Abbruch hätte die von Parallel-Audits genutzte Datenbank halb abgeräumt | **BLOCKED** |
| **`scripts/restore.sh` end-to-end** | identischer Grund; der Defekt ist stattdessen statisch belegt und der Fehlermodus isoliert im Wegwerf-Container reproduziert | **BLOCKED** |
| **Celery-Doppelzustellung auf dem echten Broker** | ein Publish in db0 hätte den Worker der Parallel-Audits beeinflusst; der Fan-out ist stattdessen **vollständig isoliert** über kombu `memory://` bewiesen | **BLOCKED** |
| **`celery-beat`-Root-Cause des Nicht-Dispatchens** | erfordert Neustart des laufenden `celery-beat`-Containers bzw. Debugging im Live-Prozess | **BLOCKED** |
| **MTTG-Zeitwerte** | kein CI-Lauf dieses Branches im Messfenster; Trivy hängt ohnehin an einem Tag-Trigger | **BLOCKED** — **nicht** als PASS gewertet |
| **Last-/Skalierungsverhalten** (Mehr-Worker, `CONN_MAX_AGE=60` unter Last, 42 Redis-Clients, `max_connections=300`) | Lasttest gegen den von Parallel-Agenten genutzten Stack | **BLOCKED** |
| **Backup-Restore bei pgvector-Upgradepfad** (Quelle 0.8.5 → Ziel 0.8.6) | nur beobachtet, nicht systematisch getestet; Funktion identisch | **BLOCKED** |
| **Vollständige PII-/Secret-Prüfung aller Log-Aufrufe** | Stichprobe aus Live-Logs; statische Vollprüfung aller `logger.*`-Aufrufe nicht Teil des Auftrags | **BLOCKED** |
| **ASGI/nginx-Transport, Frontend-Reverse-Proxy** | `CR-29`, nicht WP-1c-Scope | **BLOCKED** |
| **E2E-Abdeckung gegen nginx/ASGI** | `CR-31`, nicht WP-1c-Scope | **BLOCKED** |
| **Honcho-Profil end-to-end (Memory-Write)** | Start des Profils hätte 4 zusätzliche Container auf demselben Host erzeugt; `config`-Validierung + Matrix wurden durchgeführt, ein Live-Start nicht | **BLOCKED** |
