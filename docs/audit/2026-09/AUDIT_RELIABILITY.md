---
type: REVIEW
scope: wp6b-concurrency-observability
status: complete
date: 2026-09-30
author_agent: code-reviewer
review_id: RVW-2026-09-019
iteration: 1
max_iterations: 3
target_req: WP-6b
---

# AUDIT_RELIABILITY — WP-6b

**Error Handling (Silent Failures) · Concurrency/Transaktionsgrenzen · Observability/Health · Performance (gemessen)**

Agent: `code-reviewer` · Datum: 2026-09-30 · Branch `chore/system-audit-2026-09` @ `441f48f3`
Modus: **read-only**. Keine Code-Änderung, keine Migration, kein `ANALYZE`,
kein `DROP`/`TRUNCATE`, kein Start/Stop des geteilten Stacks.
Sämtliche DB-Aussagen: `SELECT` / `EXPLAIN (ANALYZE, BUFFERS)` / Katalogabfragen.

## Finding-IDs

Vergeben: **270–288** (19 Findings). Die vergebenen Bereiche 001–025, 030–043,
050/051, 052–067, 070–093, 100–117, 120–129, 150–190, 170–206, 220–238, 240–264
sind unberührt. Keine Kollision.

## Ampel

| Dimension | Ampel | Begründung |
|---|---|---|
| **Error Handling / Silent Failures** | 🟡 **GELB** | Struktur gut (0 nackte `except:`, 0 PII in Logs, 1888 `except`-Klauseln mit breitem `pass` nur an 7 Stellen). Aber: der systematische Mangel ist die **Trennung von Fail-Closed und Telemetrie** — 5 Sites verschlucken Infrastrukturfehler korrekt, loggen sie aber auf `DEBUG`, das im Produktivbetrieb abgeschaltet ist. |
| **Transaktionsgrenzen** | 🟢 **GRÜN** | **12 von 12** geprüften fachlichen Multi-Write-Operationen sind atomar. In **jedem** Lock-pflichtigen Fall wird der Lock **vor** der Entscheidung genommen, nicht danach. Keine zu großen Transaktionen im Prod-Pfad. |
| **Concurrency** | 🔴 **ROT** | Zwei High-Befunde: `as_goal` ohne `UNIQUE`/`version` bei `max+1` unter keinem Lock (**281**), und 6 Transition-Service-Wrapper, die `expected_version` nicht weiterreichen, obwohl dieselben Services ihr `update_*` schützen (**282**). CR-08 selbst ist dagegen **behoben**. |
| **Observability** | 🔴 **ROT** | **Keine einzige Telemetriemetrik** im gesamten System. Korrelations-ID bricht vor dem Audit-Eintrag ab. `97.7 %` der 8167 Audit-Zeilen ohne `entity_version`. Orchestrator-Probe prüft 5 von 10 Abhängigkeiten. |
| **Performance** | 🟢 **GRÜN (gemessen)** | Alle 6 geprüften Hot-Path-Queries indexgestützt, **0,12–2,95 ms** bei realistischer Datenmenge. Kein Seq-Scan-auf-großer-Tabelle, kein Filesort, kein fehlender Index. Zwei **latente** Kostentreiber (Deep-Offset, `COUNT(*)`), die mit dem toten Retention-Job komponieren. |

**Gesamt: 🟡 GELB mit zwei roten Dimensionen.** Die Codequalität der
Transaktions- und Performance-Schicht ist hoch; die Lücke liegt in
**Absicherung (Concurrency)** und **Beobachtbarkeit (Observability)**.

---

## 1. Findings

| ID | Sev | Klassifikation | CR-Track / Issue | Ort | Kurztitel |
|---|---|---|---|---|---|
| `AUD-2026-09-270` | **High** | Error Handling / Task-Registrierung | **#125 (BESTÄTIGT)** · CR-10 | `audit/archive.py:448`, `reqogniloom/celery.py:45`, `audit/apps.py:36`, `settings.py:822` | `audit.archive_lifecycle_manager` ist **nicht** im Worker-Task-Set — monatliche Retention läuft nie, `audit_entry` wächst unbegrenzt |
| `AUD-2026-09-281` | **High** | Concurrency / Lost Update | CR-06 (neu) | `application/goal_service.py:134-149`, `persistence/models.py:3342-3381` | `as_goal` ohne `UNIQUE(lineage_id, sequence_number)` und ohne `version` → `max+1` unter keinem Lock forkt die Lineage |
| `AUD-2026-09-282` | **High** | Concurrency / Lost Update | CR-08 (Rest) | `application/adr_service.py:562`, `risk_service.py:686`, `issue_service.py:726`, `change_request_service.py:638`, `main_goal_service.py:556`, `goal_service.py:659` | 6 Transition-Wrapper reichen `expected_version` nicht weiter ⇒ REST-Transitions bleiben last-writer-wins, obwohl dieselben Services `update_*` schützen |
| `AUD-2026-09-277` | Medium | Observability / Metriken | CR-33 (Teil) · WP-6a **relativiert** | repo-weit; `rest_api/metrics_views.py:29` | **Keine Telemetriemetriken existieren** (kein Prometheus/OTel). `/api/v1/metrics/` ist ein authentifizierter Domänen-Proxy, **kein** Scraper-Endpunkt |
| `AUD-2026-09-278` | Medium | Observability / Tracing | **#077 (bestätigt+verschärft)** | `rest_api/serializers.py:241-257`, `reqogniloom/middleware.py:42-91`, `audit/*` | Korrelations-ID endet nach dem Log — Fehlerkörper ohne ID, **kein `request_id` in Audit-Einträgen**, `trace_id` repo-weit 0 Treffer |
| `AUD-2026-09-285` | Medium | Observability / Audit-Trail | neu (Bereich #169) | `audit_entry` (live), `audit/writer.py:190-215` | `entity_version` in **97.7 %** von 8167 Audit-Zeilen `NULL`; `delete`/`transition`/`user.*` zu 100 % ⇒ Trail nennt keine resultierende Revision |
| `AUD-2026-09-286` | Medium | Observability / Health | **#031/#129 (verschärft)** | `reqogniloom/health.py:100-315`, `admin_ops/health_rest.py:113-198`, `deploy/docker-compose.yml:642` | Orchestrator-Probe prüft 5 von 10 Abhängigkeiten; Redis/Worker/Beat/Outbox fehlen, während die **vollständige** Prüfung admin-authentifiziert existiert |
| `AUD-2026-09-287` | Medium | Performance (latent) | **#074/#234 (bestätigt+quantifiziert)** | `audit/query.py:142-150` | Deep-Offset liest **4050** Zeilen für 50 (1,25 ms) + `COUNT(*)`-Seq-Scan pro Seitenaufruf (1,03 ms) — **komponiert mit #270** |
| `AUD-2026-09-283` | Medium | Concurrency / Idempotenz | CR-06 (neu) · REQ-072 | `audit/writer.py:207`, `application/event_bus.py:314,477-479` | Outbox ist at-least-once, der **einzige** Abonnent ist nicht idempotent: nackter INSERT, `audit_entry` ohne `event_id` |
| `AUD-2026-09-284` | Medium | Error Handling / Observability | neu | `application/tasks.py:31-38` | Outbox-Task verschluckt `Exception` und gibt `0` zurück ⇒ Celery verbucht **Erfolg**; live 222 863 Läufe, 0 Fehlschläge |
| `AUD-2026-09-274` | Medium | Error Handling / Silent Failure | neu | `mcp_server/tool_registry.py:1381,1411,1520` | 3 Fail-closed-Sites loggen auf `DEBUG`, das in Produktion hart abgeschaltet ist ⇒ DB-Ausfall ⇒ 403 für alle, **null Logzeilen** |
| `AUD-2026-09-275` | Medium | Observability / Health | neu | `reqogniloom/health.py:4` vs. `reqogniloom/urls.py:28` | Docstring verspricht `/health/ready` + `/health/live` — **beide existieren nicht**; Liveness/Readiness nicht trennbar |
| `AUD-2026-09-276` | Medium | Observability / Logging | neu | `reqogniloom/settings.py:899-953` | Log-Level und Format hartkodiert, **keine** Env-Steuerung; Level je Umgebung nicht konfigurierbar |
| `AUD-2026-09-271` | Medium | Error Handling / Silent Failure | neu | `baseline/version_reconstructor.py:191,210,227,244,295` | 5× `except Exception: pass` in der Entity-Probe ⇒ Artefakte verschwinden **still** aus rekonstruierten Baselines ⇒ falscher Diff |
| `AUD-2026-09-272` | Medium | Error Handling / Silent Failure | neu | `application/settings_service.py:661-663` | Preset-Tier still `None` bei jedem Fehler, **ohne Log** ⇒ Review-Policy fällt lautlos auf Default |
| `AUD-2026-09-273` | Medium | Error Handling / Silent Failure | neu | `application/attribute_migration_service.py:966-978` | Breiter `except` als Existenzprobe ⇒ Transient-Error liest Feld am **falschen Carrier** ⇒ falsche Migrationsdaten |
| `AUD-2026-09-279` | Low | Error Handling / Silent Failure | neu | `workflow/signature_gate.py:156-157` | Infra-Fehler ist vom falschen Passwort nicht unterscheidbar; kein Log (ADR-konform, aber ohne Telemetrie) |
| `AUD-2026-09-280` | Low | Error Handling / Silent Failure | neu | `rest_api/icd_views.py:274`, `mcp_server/tools/base.py:148,167`, `rest_api/mixins/workflow_transitions.py:281` | `TenantContextNotSetError → {}` maskiert Tenant-Context-Fehlkonfiguration vollständig |
| `AUD-2026-09-288` | Low | Performance / Methodik | **PERF-001/003**, CR-33/CR-35 | `pg_stat_user_tables` (live) | Zähler sind **nur seit Postmaster-Start** (21,5 h) und `n_live_tup` ist bis zum nächsten `VACUUM` bedeutungslos ⇒ N+1-Hypothesen ohne tragfähige Evidenzbasis |

### Verteilung

| Schweregrad | Anzahl | IDs |
|---|---|---|
| Critical | 0 | — |
| **High** | **3** | 270, 281, 282 |
| **Medium** | **13** | 271–278, 283–285, 287 |
| **Low** | **3** | 279, 280, 288 |

| Klassifikation | Anzahl |
|---|---|
| Error Handling / Silent Failure | 6 (270, 271, 272, 273, 279, 280) |
| Observability | 6 (275, 276, 277, 278, 285, 286) |
| Concurrency | 4 (281, 282, 283, 284) |
| Performance | 2 (287, 288) |

### Blocker für den Merge

Keine. Kein Finding betrifft die Datensicherheit, und es wurde nichts
destruktives ausgeführt. **270, 281, 282** sind vor dem nächsten Release zu
beheben, blockieren aber kein Merge in einen Feature-Branch.

---

## 2. Pflichtaufgabe #4 — Widerspruch #125: eindeutiges Ergebnis

> ### `audit.archive_lifecycle_manager` ist **NICHT** im Worker-Task-Set registriert.
> ### **WP-1c hat recht. WP-5 hat die falsche Stelle zitiert. #125 ist BESTÄTIGT.**

**Beleg 1 — Worker-Task-Set (live, read-only Broadcast-RPC):**
```
$ docker exec …-celery-1 celery -A reqogniloom inspect registered --timeout=15
->  celery@c83f04fea09b: OK
    * admin_ops.record_celery_beat_heartbeat
    * application.dispatch_outbox_events
    * context_graph.rebuild_workspace_graph
    * llm_adapter.run_capability
    * memory.consolidate_interaction
    * resilience.execute_optional_task
1 node online.
```
**6 Tasks. `audit.archive_lifecycle_manager` ist nicht dabei.**

**Beleg 2 — Beat dispatcht es sehr wohl (live):**
```
audit-monthly-archive | audit.archive_lifecycle_manager | enabled=t | total_run_count=0
dispatch-outbox-events| application.dispatch_outbox_events| enabled=t | total_run_count=222863
```

**Root Cause:** `@shared_task` in `audit/archive.py:448`; `backend/audit/tasks.py`
existiert **nicht**; `celery.py:45` `autodiscover_tasks()` importiert nur
`<app>/tasks.py`; `audit/apps.py:36` importiert nur `audit.writer`;
`audit.archive` wird von **nirgends** importiert (0 Treffer repo-weit).

**Warum WP-5 falsch lag:** `settings.py:822` ist der Eintrag in
**`CELERY_BEAT_SCHEDULE`** — *Beat-Konfiguration*, nicht *Worker-Task-Registrierung*.
Beides ist nötig; vorhanden ist nur (1). Der Kommentar `settings.py:801-809`
behauptet ausführlich das Gegenteil und hat den Defekt **aktiv verdeckt** —
er ist sehr wahrscheinlich die Ursache der Fehlklassifikation. Genau dieselbe
Verwechslung steckt in `backend/audit/tests/test_sa39_append_guard_and_schedule.py`,
das den Schedule-Dict prüft, nicht die Worker-Registrierung.

**Latenz-Hinweis:** Der Fehler ist latent (monatliche Crontab; 22 h Laufzeit
überschritten den 1. 00:00 nie). `docker logs … | Select-String unregistered`
→ 0 Treffer ist **kein** Gegenbeleg.

→ **270 (High)**

---

## 3. Antwort auf die Detailfragen

### (a) Ampel WP-6b

**🟡 GELB** — siehe Ampel-Tabelle oben. Zwei rote Dimensionen (Concurrency,
Observability), zwei grüne (Transaktionen, Performance), eine gelbe
(Error Handling).

### (b) Findings je Schweregrad / Klassifikation

Siehe Finding-Tabelle und Verteilungs-Tabellen in Abschnitt 1.
**3 High, 13 Medium, 3 Low, 0 Critical.**

### (c) Zahl der echten Silent Failures

| | |
|---|---|
| **Mechanische Kandidaten (Inventar gesamt)** | **≈ 65 Sites** (`except Exception: pass` = 7; `except → return None/[]/{}/True/False` ≈ 52; breites `except` mit geloggtem Fallback = 6) |
| **Bewertet (einzeln gelesen und klassifiziert)** | **31 hochsignale Sites** (aus 1888 `except`-Klauseln, 3.4 %) |
| **Echte Silent Failures** | **14 Sites in 10 Klassen** |
| Fail-closed **ohne** Telemetrie (FBO) | 5 Sites in 2 Klassen |
| Vertretbare Fallbacks (FB) | 4 Sites |
| Fehlalarme (FA) | ~34 Sites |
| Nacktes `except: pass` | **0** (PASS) |
| PII/Secrets in Logs | **0** (PASS, Fehlalarm bei der Suche) |

**Echte Silent Failures (die 14):** `version_reconstructor.py:191,210,227,244,295`
(5 Sites, 1 Klasse) · `settings_service.py:662` · `attribute_migration_service.py:977`
· `tool_registry.py:1381,1411,1520` (3 Sites, 1 Klasse) · `signature_gate.py:156` ·
`icd_views.py:274` + `base.py:148,167` (3 Sites, 1 Klasse) ·
`users.py:452` · `pdf_report_generator.py:121` · `interview_multi_protocol.py:116` ·
`ai_derivation_service.py:444`.

**Der systematische Kern:** Fehler-Unterdrückung in diesem Repo ist
fast durchgängig **fail-closed und dokumentiert** — handwerklich gut. Der
Mangel ist die **Trennung von Fail-Closed und Telemetrie**: `DEBUG` ist im
Produktivbetrieb hart abgeschaltet (`settings.py:929`), also sind
`logger.debug`-Fehlerpfade unsichtbar.

### (d) #125-Auflösung

Siehe Abschnitt 2. **Eindeutig: Task existiert NICHT im Worker-Task-Set.
WP-1c korrekt, WP-5 falsch zitiert. #125 BESTÄTIGT.** Beleg: `celery inspect
registered` (live, 6 Tasks) + `django_celery_beat_periodictask` (live,
`enabled=t`, `total_run_count=0`) + Root Cause in
`audit/archive.py:448` / `celery.py:45` / `audit/apps.py:36`.

### (e) EXPLAIN-Ergebnisse

| Query | auffällig? | Execution Time | Buffers |
|---|---|---|---|
| **Q1** Requirement-Liste (Join + Filter + top-N) | **unkritisch** | 2,95 ms | 623 |
| **Q2a** Audit Seite 1 | **unkritisch — Vorzeigepfad** (`Index Scan Backward using idx_audit_tenant_ts`) | **0,12 ms** | **6** |
| **Q2b** Audit `OFFSET 4000` | **auffällig** — 4050 Zeilen gelesen für 50 (81× Read-Amplification); Index weiter genutzt, Preis derzeit klein | 1,25 ms | 144 |
| **Q2c** Audit `COUNT(*)` (pro Seitenaufruf) | **auffällig** — voller `Seq Scan`, 8133 Rows | 1,03 ms | 196 |
| **Q3b** Trace-Link-Fan-out `LIMIT 200` | **unkritisch** (`Nested Loop` + `Memoize`) | 2,10 ms | 845 |
| **Q3c** Trace-Link-Count | **unkritisch** (`Index Only Scan`) | 1,03 ms | 413 |

**Auffällig:** nur **Q2b** (Deep-Offset) und **Q2c** (`COUNT(*)`) — beide in
`audit/query.py:142-150`, beide **latent**, beide **komponiert mit #270**
(tote Retention ⇒ unbegrenztes Wachstum ⇒ linear steigende Kosten).

**Unauffällig: Q1, Q2a, Q3b, Q3c.** Das ist ein **ehrlicher PASS-Beleg**, kein
„nicht geprüft": alle indexgestützt, kein Seq-Scan-auf-großer-Tabelle-Problem,
kein Filesort-auf-großer-Tabelle, kein fehlender Index. Auch: **alle 38 Indizes
der 4 Hot-Tabellen sind live deployed** — keine Drift „nur in der
Migrationsdatei".

**Methodischer Nachtrag (288):** Meine erste Hypothese („Tabellen nie
`ANALYZE`d ⇒ Planner ohne Statistik") war **falsch und wird zurückgenommen** —
`pg_stats` enthält Spaltenstatistiken für 38 Tabellen, `pg_class.reltuples` ist
realitätsnah. `pg_class`/`pg_statistic` liegen on-disk und überleben den
Postmaster-Neustart, die `pg_stat_user_tables`-Zähler nicht (Postmaster-Start
2026-09-29 21:36). **Für den Planner ist alles gut; für die Beweislage der
Vor-Audits ist das fatal** — `n_live_tup` meldet für `pl_requirement` den
Wert `1` bei 2112 echten Zeilen.

### (f) Fehlende Health-Checks, priorisiert

| Prio | Fehlender Check | Wo er hingehört | Begründung der Priorität |
|---|---|---|---|
| **1** | **Celery-Worker** (`inspect ping`, begrenzt) | `/health/` **oder** Compose-`healthcheck` | Ein toter Worker bedeutet: kein Outbox-Drain ⇒ **Audit-Log schreibt nicht mehr**, ohne dass irgendein Signal es meldet. Die Information existiert bereits fertig in `health_rest.py:113-132`. |
| **2** | **Outbox-Backlog** (`published=false`, `retry_count≥5`, DLQ-Zähler) | `/health/` als Warning **und** `/metrics/` | Direktster Vorlauf zu stillem Audit-Ausfall; live trivial abfragbar (aktuell 0/0/0). |
| **3** | **Redis / Cache** (PING) | `/health/` | `CACHES` ist Redis-gestützt (`settings.py:879-884`); Cache-Ausfall trifft Preset-Gates, `_preset_cache`, Beat-Heartbeat. Existiert fertig in `health_rest.py:96-110`. |
| **4** | **Celery-Beat** (Cache-Heartbeat-Age) | `/health/` | Existiert fertig (`health_rest.py:135-198`) inkl. `admin_ops.record_celery_beat_heartbeat`. Ohne ihn ist der geplante Job aus **270** unsichtbar. |
| **5** | **Getrenntes `/health/live` + `/health/ready`** | neue Routen | Docstring verspricht sie (`health.py:4`), sie fehlen. Ohne Trennung kann die 503-Semantik des einen Endpoints Liveness **oder** Readiness nicht korrekt bedienen. |
| **6** | **LLM-Provider-Erreichbarkeit** (nur Env-Präsenz wird geprüft) | `/health/` als Warning | `health.py:233-254` prüft nur, ob die Variable *gesetzt* ist, nicht ob der Endpoint antwortet. |
| 7 | DB-Pool-Auslastung (`pg_stat_activity`) | `/metrics/` | erst relevant bei mehreren Backend-Workern. |
| 8 | MCP-Server | `/health/` | existiert fertig (`health_rest.py:200`); geringste Priorität, weil MCP im selben Prozess läuft. |

**Meta-Befund (286):** Die Checks 1, 3, 4 und 8 sind **bereits implementiert** —
aber auf `/api/v1/admin/health/`, das RBAC-geschützt ist
(`rest_api/urls.py:383-385`). Die Compose-Probe
`curl -f http://localhost:8000/health/` (`deploy/docker-compose.yml:642`)
nutzt die schwache Variante. **Das ist kein Implementierungs-, sondern ein
Verdrahtungsfehler** — der billigste mögliche Fix.

### (g) Top-5

| # | ID | Titel | Warum Top-5 |
|---|---|---|---|
| **1** | **270** | `audit.archive_lifecycle_manager` nicht im Worker-Task-Set | Einziges Finding mit **klarer, belegter Fehlklassifikation durch einen anderen Audit** (WP-5) — muss explizit korrigiert werden. Retentions-Job läuft nie ⇒ unbegrenztes Audit-Wachstum **und** die Voraussetzung für 287. Root Cause ist einzeilig. |
| **2** | **281** | `as_goal` ohne `UNIQUE`/version, `max+1` unter keinem Lock | Echter Lost Update mit **asymmetrischer** Abdeckung: `as_main_goal` hat `UNIQUE(workspace_id, sequence_number)`, `as_goal` nicht — ein bereits bekanntes Muster, unvollständig angewandt. Live latent (Tabelle leer), aber sobald das Feature an ist, forkt jede Lineage. |
| **3** | **282** | 6 Transition-Wrapper ohne `expected_version` | CR-08 ist behoben — aber nur auf dem MCP-Pfad. Dieselben Services schützen `update_*` und lassen `transition_status` ungeschützt. Ein REST-Client bekommt nie ein 409. |
| **4** | **277** | Keine Telemetriemetriken im gesamten System | Multiplikator für alle anderen Findings: `036`, `284`, `287` und der Ausfall von Worker/Beat sind im Betrieb **nicht** messbar auffällig. |
| **5** | **285** | `entity_version` in 97.7 % der Audit-Zeilen `NULL` | Der Audit-Log ist das einzige forensisch belastbare Artefakt des Systems und beantwortet die zentrale Frage „in welche Revision führte diese Operation" in 97.7 % der Fälle nicht. |

Ehrliche Einordnung: **270, 281, 282** sind Korrekturen an der Absicherung,
**277, 285** Korrekturen an der Beobachtbarkeit. Kein Finding erfordert ein
Architektur- oder Datenmodell-Neuwerk.

### (h) Was ich NICHT prüfen konnte

| # | Nicht geprüft | Grund | Status |
|---|---|---|---|
| 1 | **N+1 auf Request-Ebene (PERF-001/PERF-003)** | Erfordert Query-Zählung pro HTTP-Request (Django `CaptureQueriesContext`) **mit** gültigem Auth-Token. Ein Token-Erzeugen wäre ein **schreibender** Vorgang auf dem geteilten Stack. Die **Plan-Ebene** sagt N+1 nicht aus (keine zusätzlichen Queries in Q1/Q3) — das ist ein **Negativbeleg auf Plan-Ebene, kein Beweis**. | **BLOCKED** |
| 2 | **Idempotenz von `llm_adapter.run_capability`, `memory.consolidate_interaction`, `context_graph.rebuild_workspace_graph`, `resilience.execute_optional_task`** | Code-Pfade nicht gelesen (Scope-Budget); `run_capability` verdoppelt bei 4× Ausführung (bekanntes `120`) mutmaßlich **Billing** — das ist eine Kosten-, keine Korrektheitsfrage. | **BLOCKED** |
| 3 | **Tatsächliches Rollback-Verhalten** (hält ein Fehler in Schritt 3 die Schritte 1–2 zurück?) | Live-Verifikation wäre **schreibend** (Fehler induzieren). Statisch belegt über Transaktionsgrenzen und Dekoratorreihenfolge (Evidence 02, 12/12 PASS). | statisch belegt |
| 4 | **Ob `as_goal` in einer anderen Umgebung bereits beschädigt ist** | `as_goal` ist hier leer (0 Zeilen). Andere Deployments wurden nicht untersucht. | **BLOCKED** |
| 5 | **Ob die 248 kollidierenden Audit-Tupel Redelivery-Duplikate sind** | Ohne `event_id`-Spalte nicht entscheidbar; `entity_version` ist zu 97.7 % `NULL` und diskriminiert nicht. Ich behaupte es **nicht**. | **UNGEKLÄRT** |
| 6 | **Transaktions-Timeouts / `statement_timeout`** | `DB_TRANSACTION_TIMEOUT_SECONDS` wird laut Docstring „vom Aufrufer aufgelöst" — ob der Wert in diesem Deployment gesetzt ist, habe ich nicht verifiziert. | **BLOCKED** |
| 7 | **Drittanbieter-`mcp-honcho`-Backend** | `memory/honcho_backend.py` (10 breite `except`) nicht im Detail gelesen. | **BLOCKED** |
| 8 | **Ob `ANALYZE` die Lage verbessern würde** | `ANALYZE` ist schreibend (ändert `pg_statistic`) — **nicht ausgeführt**. Da die Statistiken aber on-disk valide sind, ist der Bedarf gering. | n/a |

---

## 3. Reconciliation mit den Vor-Audits (Pflicht)

| Vor-Audit-Befund | WP-6b-Ergebnis | Beleg |
|---|---|---|
| **#125** (Audit-Archivierung nicht im Worker-Task-Set) — WP-1c: ja / WP-5: „nicht reproduzierbar" | **BESTÄTIGT. Widerspruch zugunsten von WP-1c aufgelöst.** | `celery inspect registered` live; `settings.py:822` = Beat-Schedule, nicht Worker-Registrierung → **270** |
| **#031 / #129** — *„`/health/` liefert bei `degraded` HTTP 200"* | **WIDERLEGT** (dieser Teilsatz). `degraded` ⇒ **503** (`health.py:135,161`); `warning` ⇒ 200 (Z. 312-313), sauber begründet. **Restbefund bleibt:** kein Cache/Worker/Beat-Check. | `reqogniloom/health.py:135,161,312-313` → **286** |
| **CR-06 / CR-08** — Transition validiert nach dem Lock | **WIDERLEGT / behoben.** Reihenfolge ist `atomic()` (306) → `lock_item_state` (308) → Lesen aus der gesperrten Zeile (310) → Validierung → Schreiben. Revisions-Prüfung zuerst (312-317). Bestätigt WP-4. | `workflow/services.py:306-318`, `workflow/lifecycle_manager.py:278-288` |
| **CR-09** — Global-Definition-Propagation nicht atomar | **WIDERLEGT (weitgehend).** Check **und** Graph-Write liegen in **einem** `transaction.atomic()` mit `select_for_update()` auf der Global-Row. Ein **Residuum** ist dokumentiert begründet: die `WorkflowItemState`-Zeilen, die nur gezählt werden, sind nicht sperrbar. | `workflow/global_definition_store.py:364-366` (Z. 330-337 zur behobenen Zwei-Block-Form, Z. 341-360 zum Residuum) |
| **#077** — kein `trace_id` in Fehlerantworten | **BESTÄTIGT und VERSCHÄRFT.** Nicht nur fehlt die ID im Fehlerkörper — sie wird auch **nicht in den Audit-Eintrag geschrieben**; `trace_id` kommt repo-weit nicht vor. Die Kette bricht nach dem Log. | `rest_api/serializers.py:241-257`; `rg "request_id" audit/` → 0 → **278** |
| **#074 / #234** — ungebrochene Pagination | **BESTÄTIGT als Mechanismus, QUANTIFIZIERT, derzeit kein Incidens.** 4050 Zeilen gelesen für 50, 1,25 ms. | `EXPLAIN` Q2b → **287** |
| **PERF-001 / PERF-003** (N+1-Hypothesen) | **UNGEKLÄRT — und die Beweislage der Vor-Audits ist methodisch unbrauchbar.** `pg_stat_user_tables` zählt nur seit 21,5 h; `n_live_tup` meldet 1 statt 2112. Plan-Ebene liefert **keine** N+1-Indizien (Negativbeleg, kein Beweis). | `pg_stat_user_tables` live → **288** |
| **CR-33 / CR-35** (Performance-Hypothesen) | **WIDERLEGT für die geprüften Hot-Paths.** 6/6 Queries indexgestützt, 0,12–2,95 ms, alle 38 Indizes live deployed. | `EXPLAIN` Q1–Q3 → **287** |
| **WP-6a** — `/metrics/` unauthentifiziert | **RELATIVIERT.** `MetricsViewSet` ist **authentifiziert** (401 ohne Auth, Z. 40-46) und ist ein Domänen-Metrik-Proxy, kein Scraper-Endpunkt. Der reale Befund ist der **Wegfall** jeglicher Telemetriemetriken. | `rest_api/metrics_views.py:29-102` → **277** |
| **#120** (4 Queues identischer Routing-Key) · **#121** (Beat dispatcht nie) · **#122** (Ack-Semantik) · **#124** (nicht-atomarer Restore) · **#169** · **#036** · **#057** · **#070/#071** · **#089** | **Nicht Gegenstand von WP-6b**, nicht neu bewertet, nicht widerlegt, nicht verschärft. Wo WP-6b berührend Belege liefert: `169` (Audit-Korrelation fehlt → **278**; `entity_version`/`entity_id` NULL → **285**), `124` (nicht verifiziert → Evidence 02 E3, **BLOCKED**), `120`/`121` (Idempotenz-Audit der 6 registrierten Tasks → Evidence 03 B.4; 2 von 6 als idempotent belegt, 4 **BLOCKED**). | — |
| **#237** (`Server: uvicorn` verrät Technologie) | Berührt: `EXPLAIN`-Beleg (`curl`-Probe zeigte Header-Echo) — **nicht Gegenstand**, nicht bewertet. | — |

**Nicht neu erfunden:** Jedes Finding 270–288 entweder (a) verschärft einen
Vor-Audit-Befund mit neuem Beleg, (b) relativiert/widerlegt einen
Vor-Audit-Befund, oder (c) ist eine eigenständige Messung mit
Pfad:Zeile-Beleg. Kein Finding wiederholt eine Vor-Audit-Nummer.

---

## 4. Blast Radius

**SIGNIFICANT (3).** Keine Änderung an Datenmodell, Architektur oder
öffentlichen Schnittstellen wurde vorgenommen (read-only). Der *analysierte*
Blast Radius der Findings ist begrenzt und lokal:

| Finding | Betroffene Dateien | Radius | Risiko eines Fixes |
|---|---|---|---|
| 270 | 2–3 (`audit/tasks.py` neu, `settings.py`-Kommentar, Test) | **MODERATE** | niedrig — Dekorator verschieben, sonst nichts |
| 281 | 1–2 (`goal_service.py`, neue Migration) | **MODERATE** | **mittel** — Migration auf einer evtl. befüllten Tabelle braucht Dedup-Vorlauf |
| 282 | 6 Service-Wrapper + ggf. Mixin | **MODERATE** | niedrig — Parameter durchreichen, Signatur additiv |
| 277/285 | neue Telemetrie / Audit-Spalte | **SIGNIFICANT** | mittel — Telemetrie-Infrastruktur neu; `entity_version` rückwirkend füllen ist nicht sinnvoll |
| 286 | 1 (`health.py`) oder `docker-compose.yml` | **TRIVIAL–MODERATE** | niedrig — Checks existieren bereits in `health_rest.py`, nur verdrahten |

Kein Finding erfordert eine Entscheidung von `se-architect`. `281` (Migration
auf befüllter Tabelle) und `277` (Telemetrie-Infrastruktur) sollten vor
Umsetzung mit `database-reviewer` bzw. `se-architect` abgestimmt werden.

---

## 5. Empfehlungen (priorisiert, nicht umgesetzt)

| Prio | Empfehlung | Findings |
|---|---|---|
| **P0** | `backend/audit/tasks.py` anlegen, `@shared_task` dorthin verschieben; Kommentar `settings.py:801-809` korrigieren; Test auf **Worker-Registrierung** statt Schedule-Dict ergänzen | 270 |
| **P0** | `UNIQUE (lineage_id, sequence_number)` auf `as_goal` + `select_for_update` beim `max+1`, analog zu `main_goal` | 281 |
| **P0** | `expected_version` in den 6 `transition_status`-Wrappern durchreichen (der `WorkflowTransitionsMixin` löst es bereits auf) | 282 |
| **P1** | `logger.debug` → `logger.warning` in den 3 RBAC-Fail-closed-Pfaden; `LOG_LEVEL` als Env konfigurierbar machen | 274, 276 |
| **P1** | `/health/live` + `/health/ready` routen; Celery-Worker-, Redis- und Outbox-Backlog-Check in die Orchestrator-Probe aufnehmen (Code existiert in `health_rest.py`) | 275, 286 |
| **P1** | `request_id` als Spalte auf `AuditEntry` **und** in `build_error_response` aufnehmen — schließt die Kette Log→Antwort→Audit | 278 |
| **P2** | `event_id` auf `audit_entry` + `get_or_create` im `AuditLogWriter` (macht den Abonnenten REQ-072-konform) | 283 |
| **P2** | `dispatch_outbox_events` bei Fehler re-raisen (Celery verbucht dann `task_failure`) oder `task_always_eager`-frei explizit `self.retry` nutzen | 284 |
| **P2** | Keyset-Paging für die Audit-Liste; `COUNT(*)` aus dem Seitenpfad nehmen (oder cache'n) | 287 |
| **P2** | `broad except` in `version_reconstructor` und `_field_carrier` auf die konkrete Exception verengen und mindestens `logger.warning` ergänzen | 271, 273 |
| **P3** | Telemetrie-Grundstock (M1–M5 aus Evidence 05) — Queue-Tiefe und Outbox-Backlog zuerst | 277, 284 |
| **P3** | `entity_version` befüllen, wo die Entität eine `version` hat (188 von 8167 Zeilen heute); LLM-Calls mit echter `entity_id` statt Null-UUID loggen | 285 |

---

## 6. Artefakte

| Datei | Inhalt |
|---|---|
| `docs/audit/2026-09/AUDIT_RELIABILITY.md` | dieser Bericht |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp6b-01-silent-failure-inventar.md` | 65 Kandidaten → 14 echte; 31 Sites klassifiziert; Negativbelege |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp6b-02-transaktionsgrenzen-matrix.md` | 12/12 fachliche Einheiten atomar; Lock-vor-Entscheidung; Negativbefunde |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp6b-03-race-analyse-und-125.md` | **#125-Auflösung mit Live-Belegen**; `select_for_update`-Analyse; CR-08-Verifikation; Idempotenz; Outbox |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp6b-04-explain-output.md` | 6× `EXPLAIN (ANALYZE, BUFFERS)` live; Index-Deployment-Nachweis; Methodik-Korrektur |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp6b-05-observability-matrix.md` | Logging/PII; Health-Abdeckungsmatrix; Metriken-Lücke; Audit-Kanal-Messung |
