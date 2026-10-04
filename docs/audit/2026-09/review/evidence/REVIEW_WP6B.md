---
type: REVIEW
scope: "WP-6b (Reliability/Concurrency/Observability) — adversarial second review"
status: final
date: 2026-10-01
author_agent: code-reviewer
branch: chore/audit-review-2026-09
head_observed: bf49b0f (Task-Kontext nennt 10dc620f; beide sind Vorfahren, Diff nur Doku)
method: "Adversariale Zweitprüfung, read-only. Produktcode neu gelesen; DB nur SELECT/EXPLAIN (kein Writing). Audit-eigenes AUDIT_EVIDENCE/* wurde NICHT als Beweis akzeptiert."
targets: [270,271,272,273,274,275,276,277,278,279,280,281,282,283,284,285,286,287,288]
---

# REVIEW_WP6B — Adversariale Verifikation der WP-6b-Findings (270–288)

> **Rolle.** Unabhängiger Gegenprüfer. Kein Vertrauen in `AUDIT_RELIABILITY.md` oder
> `AUDIT_EVIDENCE/wp6b-*` als Beleg. Jede Aussage wird aus Produktcode
> (`backend/...`) oder live aus PostgreSQL neu abgeleitet. AWS-/Tooling-/Prozess-
> Aussagen ohne Produktbezug werden als solche markiert.

## 1. Scope / Methodik

| Aspekt | Wert |
|---|---|
| Prüfgegenstand | 19 Findings `AUD-2026-09-270 … -288` (WP-6b) |
| Register | `docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5; Report `AUDIT_RELIABILITY.md` (Basis `chore/system-audit-2026-09` @ `441f48f3`) |
| Geprüfter Code | `backend/application/**`, `backend/audit/**`, `backend/baseline/**`, `backend/workflow/**`, `backend/rest_api/**`, `backend/mcp_server/**`, `backend/reqogniloom/**` |
| Live-Quellen | Docker-Stack UP; `celery inspect registered` (read-only RPC); `psql` **nur** `SELECT`/`EXPLAIN (ANALYZE, BUFFERS)` |
| Nicht verwendet | `AUDIT_EVIDENCE/*` als Beweis (nur als Kontext), `git`-Mutation, Schreiboperationen |
| HEAD-Hinweis | Task nennt `10dc620f`; beobachtet `bf49b0f` (2 Doku-Commits davor, `636de7d4`, `bf49b0f`). Code-Diff zu `10dc620f` wurde für `audit/query.py` und `workflow_transitions.py` geprüft: identisch. |

**Werkzeug-Belege (live):**

```
$ docker exec ai-native-reqflow-poc-celery-1 celery -A reqogniloom inspect registered
 ->  celery@c83f04fea09b: OK
     * admin_ops.record_celery_beat_heartbeat
     * application.dispatch_outbox_events
     * context_graph.rebuild_workspace_graph
     * llm_adapter.run_capability
     * memory.consolidate_interaction
     * resilience.execute_optional_task
 1 node online.            # = 6 Tasks, KEIN audit.archive_lifecycle_manager
```

## 2. Gegenbeweis-Tabelle (19/19)

| ID | Sev (Report) | Verdikt | Gegenbeweis `<Pfad>:<Zeile>` | Zitat / Messung |
|---|---|---|---|---|
| **270** | High | **BESTAETIGT** | `backend/reqogniloom/celery.py:45`; `backend/audit/apps.py:36`; `backend/audit/archive.py:448` | `app.autodiscover_tasks()` importiert nur `<app>/tasks.py`; `backend/audit/tasks.py` **existiert nicht** (`Test-Path`=False); `apps.py:36` `from audit.writer import register_writer_on_event_bus` — kein `audit.archive`-Import. `archive.py:448` `@shared_task(name="audit.archive_lifecycle_manager")` wird daher nie importiert. Live: 6 Tasks, Task fehlt; Beat-Zeile `total_run_count=0`. |
| **271** | Medium | **BESTAETIGT** | `backend/baseline/version_reconstructor.py:191,210,227,244,295` | 5× wortwörtlich `except Exception:` / `pass` (Requirement-, ArchitectureElement-, Artifact-, GlossaryTerm-, AuditLogEntry-Probe). Fehler ⇒ Schleife läuft weiter ⇒ am Ende `return None` ⇒ `VersionNotFoundError`. |
| **272** | Medium | **BESTAETIGT** | `backend/application/settings_service.py:661-663` | `except Exception:` / `return None` ohne Log. `_apply_tier_floor` (`:718-722`) flort nur bei `tier == TIER_EXTENDED` ⇒ Fehler in `get_preset` ⇒ Extended-Workspace fällt lautlos auf `auto`/`review_changes` zurück (fail-open). |
| **273** | Medium | **UEBERZOGEN → Low** | `backend/application/attribute_migration_service.py:969-978` | Breites `except Exception: pass` als Existenzprobe bestätigt. **Aber**: `model._meta.get_field(name)` ist reine In-Memory-Metadaten-Introspektion, **kein I/O**; ein „Transient-Error“ ist nicht begründbar. Restrisiko real, aber nahe null. |
| **274** | Medium | **BESTAETIGT** | `backend/mcp_server/tool_registry.py:1382,1412,1520`; `settings.py:929` | `logger.debug("Role resolution failed…")`, `logger.debug("Global role resolution failed…")`, `logger.debug("Tenant-admin lookup failed…")`. Root-Logger hart `"level": "INFO"` ⇒ DEBUG unterdrückt ⇒ DB-Ausfall → 403 ohne Logzeile. |
| **275** | Medium | **BESTAETIGT** | `backend/reqogniloom/health.py:4` vs. `backend/reqogniloom/urls.py:28` | Docstring: `"Implements both /health/ready (readiness) and /health/live (liveness) patterns."`; einzige registrierte Route: `path("health/", HealthView.as_view(), name="health")`. Repo-weit **0** Routen für `health/ready|health/live`. |
| **276** | Medium | **BESTAETIGT** | `backend/reqogniloom/settings.py:899-953` | `LOGGING` mit hartkodierten `"level": "INFO"` (root/`django`/`reqogniloom`/`celery`). Repo-weit **0** Treffer für `LOG_LEVEL`/`LOG_FORMAT`-Env. |
| **277** | Medium | **BESTAETIGT** | `backend/rest_api/metrics_views.py:29-46`; Repo-weit | `MetricsViewSet` ruft `get_auth_context` → 401 ohne Auth; Proxy auf `se_metrics.compute_metrics`. **0** Treffer für `prometheus|opentelemetry|otel|statsd|datadog` in `settings.py`/`requirements.txt`/`pyproject.toml`. Keine Telemetriemetrik. |
| **278** | Medium | **BESTAETIGT** | `backend/rest_api/serializers.py:241-257`; `backend/reqogniloom/middleware.py:42-91` | `build_error_response` liefert nur `{"error":{code,message,details}}` — **kein** `request_id`. `rg "trace_id" backend frontend` → **0**; `rg "request_id" backend/audit` → **0**. Middleware setzt nur Header/Log-ContextVar. |
| **279** | Low | **BESTAETIGT** | `backend/workflow/signature_gate.py:140-157` | Gesamte Credential-Prüfung in `try` / `except Exception:` / `return False`, kein Log. Infra-Fehler ≡ falsches Passwort. Fail-closed. |
| **280** | Low | **TEILWEISE** | `icd_views.py:274` ✅, `mcp_server/tools/base.py:147,167` ✅, **`workflow_transitions.py:281` ❌** | `icd_views.py:274` `except TenantContextNotSetError: return {}` ✅; `base.py:147/167` setzen `None`/`{}` ✅. **Fehlzitat**: `workflow_transitions.py:281` ist `except (AttributeDefinitionNotFound, CrossTenantWorkspaceError): return None`; `TenantContextNotSetError` kommt dort nur im Kommentar `:135`. 1 von 3 Fundstellen falsch. |
| **281** | High | **BESTAETIGT** | `backend/persistence/models.py:3376-3381`; `backend/application/goal_service.py:134-149` | `Goal.Meta` hat `indexes=[Index(workspace_id,lineage_id)]`, **keine** `constraints`. Live `pg_indexes as_goal`: nur nicht-unique `as_goal_workspa_9319d2_idx`; **kein** `UNIQUE(lineage_id,sequence_number)`. `as_main_goal` hat `uq_main_goal_workspace_sequence` (asymmetrisch). `goal_service.py:134-139` liest `MAX(sequence_number)` per `.order_by("-sequence_number").first()` — **ohne** `select_for_update`. `as_goal` live 0 Zeilen (latent). |
| **282** | High | **UEBERZOGEN → Medium** (+ TEILWEISE) | `goal_service.py:659-668` **❗**, `adr_service.py:562`, `risk_service.py:686`, `issue_service.py:726`, `change_request_service.py:638`, `main_goal_service.py:556`; Impact: `workflow_transitions.py:482-491` | **1 von 6 Zitaten falsch**: `GoalService.transition_status` reicht `expected_version` **sehr wohl** weiter (`WorkflowFacade().transition(..., expected_version=expected_version)`), hinzugefügt in `6f145c87` (2026-09-26, Vorfahre des Audit-HEAD). Real ohne `expected_version`: `Adr`/`Risk`/`Issue`/`ChangeRequest`/`MainGoal` (5). **Impact überzogen**: die generische REST-Route `POST …/transitions/` (`WorkflowTransitionsMixin`) ruft `facade.transition(..., expected_version=expected_version)` **direkt** — sie geht gar nicht durch die Wrapper. Nur die Sonderrouten `/adrs/{pk}/supersede/` (`views.py:6063`) und `/change-requests/{pk}/transition/` (`views.py:7471`) laufen über die Wrapper; `RiskService`/`IssueService`/`MainGoalService.transition_status` haben **keinen** Aufrufer im Produktcode. |
| **283** | Medium | **FALSCH** | `backend/audit/writer.py:31,256`; `backend/audit/events.py:100-123`; `backend/audit/services.py:178-190`; `context_graph/apps.py:27-31` | **Klassen-Namens-Verwechslung.** `audit/writer.py:31` importiert `DomainEventBus` aus **`audit.events`** (in-process, statisch, `_subscribers`-Liste) — **nicht** aus `application.event_bus` (Transactional Outbox). `audit/services.py:189-190` schreibt den Audit-Eintrag **synchron direkt** (`writer.write(event)`), nicht über die Outbox. Outbox-Abonnenten sind laut `ready()`-Hooks: `WebhookDispatcher`, `MemoryProjector`, `ContextGraphProjector` — **nicht** `AuditLogWriter`. Beleg dafür, dass beide Busse bewusst getrennt sind: `context_graph/apps.py:27-31` „application.event_bus.DomainEventBus (Transactional Outbox), **NOT** audit.events.DomainEventBus (audit-only, no outbox)“. Der Satz „der **einzige** Abonnent“ ist zusätzlich doppelt falsch (3 Abonnenten, Audit keiner davon). `audit_entry` hat tatsächlich keine `event_id`-Spalte — für die Behauptung aber ohne Kausalkette. |
| **284** | Medium | **BESTAETIGT** | `backend/application/tasks.py:31-38` | `try: return poll_and_dispatch()` / `except Exception:` / `logger.exception(…)` / `return 0`. Kein Re-Raise ⇒ Celery verbucht Rückgabewert als Erfolg. Live `django_celery_beat_periodictask.dispatch-outbox-events.total_run_count=223773` (Report nannte 222 863 — zwischenzeitlich gewachsen). Outbox unpub=0, DLQ=0. „0 Fehlschläge“ ist per DB **nicht** belegbar (kein Result-Backend/Taskresult-Tabelle) — Mechanismus aber code-seitig eindeutig. |
| **285** | Medium | **BESTAETIGT** | `audit_entry` (live); `backend/audit/writer.py:197` | Live: `count(*)=8167`, `entity_version IS NULL=7979` ⇒ **97.70 %** (exakt). Differenz 188 nicht-NULL. Je `op`: `delete` 872/872, `transition` 175/175, `baseline.create` 38/38, alle `user.*` 100 % NULL. `writer.py:197` `entity_version=event.version` (Quelle setzt `version` oft nicht). |
| **286** | Medium | **BESTAETIGT** | `backend/reqogniloom/health.py:124-261`; `backend/admin_ops/health_rest.py:96-198`; `deploy/docker-compose.yml:642` | `/health/` prüft 5 Dinge: `database`, `memory_backend`, `embedding_dimensions`, `llm_provider_env`, `csrf_cookie_secure_matches_auth`. `health_rest.py` hat `_check_redis`(`:96`), `_check_celery_worker`(`:113`), `_check_celery_beat`(`:135`), `_check_mcp_server`(`:200`) — aber auf dem RBAC-geschützten Admin-Endpoint. Compose-Probe: `test: ["CMD-SHELL", "curl -f http://localhost:8000/health/ || exit 1"]`. Outbox-Check: Repo-weit **0** Treffer in `health_rest.py`. |
| **287** | Medium | **BESTAETIGT** | `backend/audit/query.py:146-148` | `total = qs.count()` + `entries = list(qs[offset:offset+page_size])`. Live (tenant-gefiltert): `Index Scan Backward using idx_audit_tenant_ts` … `rows=4050` für `LIMIT 50 OFFSET 4000` ⇒ **4050 gelesen** (Report exakt). `EXPLAIN … SELECT count(*)` = `Seq Scan … rows=8167`. Timings jetzt höher (5,3 ms / 0,75 ms statt 1,25 / 1,03) — Grössenordnung unverändert. |
| **288** | Low | **BESTAETIGT** | `pg_stat_user_tables` (live) | `pg_postmaster_start_time()=2026-10-01 16:53:10`, Uptime **29 min**; `last_analyze`/`last_autoanalyze` = NULL; `n_live_tup=0` für `pl_requirement` **und** `audit_entry`, obwohl `count(audit_entry)=8167`. ⇒ Zähler nur seit Postmaster-Start und `n_live_tup` bis `ANALYZE`/`VACUUM` unbrauchbar. (Report-„21,5 h“ war der damalige Lauf; Postmaster seither neu gestartet.) |

## 3. Register-Quercheck — AUD-270 vs. AUD-121 / AUD-125

**Frage:** Ein anderer Agent hat `AUD-121` (Teilaussage „Beat dispatcht nie“) als **falsch** entlarvt. Bleibt `270` unberührt?

**Ergebnis: Ja, 270 bleibt unberührt und unabhängig gültig.**

- `AUD-121` ist **dreiteilig** (`AUDIT_FINDINGS.md:196`): (a) Healthcheck prüft nur Prozessexistenz ✅, (b) `audit.archive_lifecycle_manager` nicht im Worker-Task-Set ✅, (c) „Beat dispatcht nie (0× Sending due task)“ = **NICHT VERIFIZIERBAR**. Der „Beat dispatcht doch“-Gegenbeweis trifft **nur (c)**.
- `270` ist ausschliesslich Aussage **(b)** — die **Worker-Task-Registrierung**. Sie ist struktureller Natur (`autodiscover_tasks()` importiert nur `<app>/tasks.py`; `audit/tasks.py` fehlt; `archive.py` wird nur vom Test importiert) und damit von Beat **unabhängig**. Live bestätigt: Worker kennt genau 6 Tasks, den Archive-Task nicht.
- Die Live-Beat-Zeile `audit-monthly-archive | total_run_count=0 | last_run_at=NULL` zeigt: Beat hat bislang **nicht** dispatcht (nächster Crontab-Termin: 1. des Monats, 00:00). Selbst wenn Beat künftig dispatcht, würde der Worker den unbekannten Task als „unregistered“ ablehnen — `270` bleibt wirksam.
- Register-Konsistenz: `AUDIT_FINDINGS.md:1835` (Zeile C9) und `:2337` bestätigen (b) bereits und markieren nur (c) als nicht verifizierbar. `AUD-125` (`:224`, `:976`) = dieselbe Aussage wie `270` im WP-1c-Block. **Kein Widerspruch zum Register.**
- **Präzisierung (kein Verdiktwechsel):** Der Report-Satz „`audit.archive` wird von nirgends importiert (0 Treffer repo-weit)“ ist minimal überzogen — `backend/audit/tests/test_sa39_append_guard_and_schedule.py:86` (`from audit import archive`) importiert es. Das ist ein **Test**-Import (registriert die Task nur im Testprozess) und ändert `270` nicht.

## 4. Verdikt-Zählung (19/19)

| Verdikt | Anzahl | IDs |
|---|---|---|
| **BESTAETIGT** | **15** | 270, 271, 272, 274, 275, 276, 277, 278, 279, 281, 284, 285, 286, 287, 288 |
| **TEILWEISE** | **1** | 280 |
| **UEBERZOGEN** | **2** | 273 (Medium→Low), 282 (High→Medium) |
| **FALSCH** | **1** | 283 |
| UNTERSCHAETZT / NICHT VERIFIKABAR / KEIN REQOGNILOOM-BEZUG | 0 | — |

**Schweregrad-Korrekturen:** `282` High → **Medium**; `273` Medium → **Low**. Alle übrigen Schweregrade stimmen mit Register/Report überein.

**Zahlen-Nachprüfung (Protokoll 6):**

| Zahl (Report) | Ergebnis |
|---|---|
| „8167 Zeilen“ | ✅ exakt (`count(*)=8167`) |
| „97,7 % NULL“ | ✅ exakt (`7979/8167 = 97.70 %`) |
| „222 863 Läufe“ | ⚠️ plausibel, heute `223773` (gewachsen); Aussage nicht falsch |
| „12/12 atomar“ | ✅ Stichproben bestätigt (T1 `workflow/services.py:306`, T5 `authorization.py:986/1027`, T8 `interview_service.py:960`); **nicht** vollständig unabhängig re-deriviert |
| „6/6 indexgestützt“ | ⚠️ Q2b (tenant-gefiltert) + Q2c reproduziert; übrige nicht erneut gemessen. Q2b nutzt Index weiterhin |
| „4050 Zeilen / 1,25 ms“ | ✅ Zeilen exakt; Timing heute 5,3 ms (Umgebung) |
| „248 kollidierende Audit-Tupel“ | ❌ mit getesteten Gruppierungen nicht reproduziert (144 bzw. 124). Report flaggt es selbst als **UNGEKLÄRT**, nicht als Finding — daher unkritisch |
| „0 Fehlschläge (Outbox)“ | ⚠️ per DB nicht verifizierbar (kein Result-Backend); Mechanismus code-seitig bestätigt |

## 5. Key-Verdikte (Diskussion)

### 5.1 AUD-283 ist falsch — Busse gleichen Namens verwechselt
Der Report führt `audit/writer.py:207` und `application/event_bus.py:314,477-479` in **einem** Kausalstrang und schliesst auf Redelivery-Duplikate im Audit-Log. Code zeigt zwei getrennte Mechanismen:
1. `audit.events.DomainEventBus` — in-process, statische `_subscribers`-Liste (`events.py:96-123`), benutzt von `AuditLogWriter` (`writer.py:31,256`).
2. `application.event_bus.DomainEventBus` — Transactional Outbox (`event_bus.py`), Abonnenten `WebhookDispatcher` (`application/apps.py`), `MemoryProjector` (`memory/apps.py`), `ContextGraphProjector` (`context_graph/apps.py`).

`record_audit` ruft `writer.write(event)` **direkt** (`services.py:189-190`) — genau einmal, synchron in der Business-Transaktion. Outbox-Redelivery erreicht den Audit-Writer nicht. Die im Finding behauptete Duplikat-Kette existiert nicht. **Korrigierter Schweregrad: entfällt (FALSCH).**

### 5.2 AUD-282 ist überzogen und enthält ein Fehlzitat
- 1 von 6 Zitaten (`goal_service.py:659`) ist falsch: `GoalService.transition_status` reicht `expected_version` **weiter**.
- Die **generische** REST-Transitions-Route ist geschützt (`workflow_transitions.py:482-491` ruft den Facade direkt). Last-writer-wins verbleibt nur auf den **Sonderrouten** `/adrs/{pk}/supersede/` (`views.py:6063`) und `/change-requests/{pk}/transition/` (`views.py:7471`) sowie potenziell auf ungenutzten Service-Wrappern. **High → Medium.**

### 5.3 AUD-270 hält — unabhängig von AUD-121(c)
Siehe §3. Worker-Registrierung ≠ Beat-Schedule. Live: 6 Tasks, Archive-Task fehlt; `settings.py:801-809`-Kommentar suggeriert fälschlich eine registrierte `shared_task`. Der Test `test_sa39_append_guard_and_schedule.py` prüft nur den Schedule-Dict + Import im Testprozess — er kann den Worker-Defekt nicht fangen. **P0-Fix korrekt priorisiert.**

### 5.4 AUD-288 ehrlich bestätigt
`n_live_tup=0` bei 8167 realen Zeilen und `last_analyze=NULL` nach nur 29 min Uptime belegen: `pg_stat_user_tables` ist als Evidenzbasis wertlos. Der Report hat seine eigene Ersthypothese („nie ANALYZE“) bereits zurückgenommen — das ist methodisch sauber.

### 5.5 AUD-273 zu hoch bewertet
`_meta.get_field()` ist In-Memory-Introspektion ohne I/O. Der Report konstruiert einen „Transient-Error“, der real nicht auftritt. Der breite `except` bleibt ein Code-Smell (Low), ist aber kein Medium-Datenkorrektheitsrisiko.

## 6. NEU-AUDIT-LUECKE

Aus der Widerlegung von 283 und der Präzisierung von 282 entstehen **zwei echte Lücken**, die WP-6b nicht abdeckt:

1. **Idempotenz der *tatsächlichen* Outbox-Abonnenten (hoch).** `application/event_bus.py:476-479` fordert at-least-once + idempotente Abonnenten (REQ-072). Die realen Abonnenten sind `ContextGraphProjector`, `MemoryProjector`, `WebhookDispatcher` — keiner davon wurde in WP-6b auf Idempotenz geprüft (Report (h) #2 nennt nur die 6 Celery-Tasks). Ein `event_id`-Dedup-Fenster bzw. `get_or_create` je Projektor ist der zu prüfende Punkt. **Fehlender Prüfschritt:** für jeden der drei Abonnenten nachweisen, dass eine Doppel-Zustellung desselben `event_id` keinen zweiten Schreibeffekt erzeugt.
2. **Optimistic-Locking der Sonderrouten (mittel).** `/adrs/{pk}/supersede/` und `/change-requests/{pk}/transition/` umgehen die geschützte generische Route; `AdrService.transition_status`/`ChangeRequestService.transition_status` akzeptieren kein `expected_version`. Der Register-Text zu 282 sollte auf diese zwei Routen verengt werden (nicht „REST-Transitions“ pauschal). Candidat-Fix: `expected_version` additiv in die beiden Wrapper + `resolve_expected_version` in den beiden Sonderrouten.

**Empfehlung ans Register:** `AUD-283` auf `FALSCH`/`zurückgezogen` setzen (oder in die neue Lücke 1 überführen), `282` auf Medium mit korrigierter Reichweite, `273` auf Low.

---

*Erstellt 2026-10-01 durch `code-reviewer`, adversarial second review, read-only.*
