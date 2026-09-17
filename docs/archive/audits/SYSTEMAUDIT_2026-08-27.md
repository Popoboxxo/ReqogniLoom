# EXTREM DETAILLIERTES SYSTEM-AUDIT — ReqogniLoom

**Datum:** 27.08.2026
**Art:** Voll-Audit (read-only, keine Code-Änderungen)
**Umfang:** Alle Systemkomponenten — Backend (Layer 0/1, Layer 2 + Extension-Apps), REST API, MCP Server, Frontend/UI, Infrastruktur, Test-Landschaft, Fachlichkeit (SE/RE/MBSE)
**Methodik:** 8 parallele Spezialisten-Reviews; jeder Befund mit `Datei:Zeile` gegen den Quellcode verifiziert; Test-Landschaft inkl. tatsächlicher Testausführung (Backend-Collection + Lauf ohne Stack, Frontend-Vollaufruf).

---

## 1. Executive Summary

**Gesamturteil:** Solide, stellenweise exzellente Kernarchitektur mit außergewöhnlicher Testkultur — belastet durch massive Dokumentations-Drift, tote Feature-Pfade, Restrisiken im Ops-/Dependency-Bereich und einen fachlichen Zentrums-Konflikt (L0–L4-Mapping).

| Bereich | Note | Kernurteil |
|---|---|---|
| Architektur (Layer-Disziplin, ADRs) | **B+** | ADR-01/02/04/06/07 im Kern durchgesetzt; Layer-Verletzungen v.a. in auth_tenancy |
| Sicherheit / Multi-Tenancy | **C+** | Kernstark (2-Layer-Isolation, fail-fast), aber RLS-Lücken auf ~20 Tabellen, EOL-Dependencies |
| REST API | **B−** | 28 ViewSets + ~66 APIViews, konsistente RBAC; Fehlerhüllen-Divergenz, fehlende Schema-Pflege |
| MCP-Server | **B** | 171 Tools, fail-closed RBAC, Manifest-Drift-Guard; kein Throttling, Protokoll-Abweichungen |
| Frontend/UI | **B+** | httpOnly-Cookie-Auth (AGENTS.md-Doku dazu ist falsch!), Token-Ratchet, a11y stark; i18n-Backlog 145 Keys |
| Fachlichkeit (SE/RE) | **B−** | Governance-Kette (SE-Auditor, Baselines) exzellent; Traceability-Matrix ~3× veraltet, L0-L4-Konflikt |
| Infrastruktur | **C+** | 8 (nicht 5) Services, gute Defaults; Redis-Eviction-Risiko, keine Celery-Time-Limits, Static-Files broken |
| Tests | **A−** | 5.768 pytest- / 1.363 vitest- / 274 Playwright-Tests (README behauptet 1.400/111); 1.363/1.363 FE-Tests grün; Coverage nie erzwungen |

**Kein hartes kritisches Finden auf einem mounted Endpoint** — aber **~20 HIGH-Befunde**, davon mehrere vor dem nächsten Release fixbar.

---

## 2. Fakten-Abweichung: Doku vs. Realität (systematisch falsch)

AGENTS.md / README / Projektanspruch beschreiben das System falsch:

| Claim (AGENTS.md etc.) | Realität (verifiziert) |
|---|---|
| „5 Services" docker-compose | **8 Services** (postgres, postgres-backup, redis, backend, migrate, celery, celery-beat, frontend) — docker-compose.yml |
| „Django 4.2+" | **Django 5.2 LTS** (requirements.txt:16, CVE-begründet) — aber **requirements.lock schient noch 4.2.30 (EOL!)** |
| „16 ViewSets + 2 APIViews" | **28 ViewSet-Klassen + ~66 APIViews** (rest_api/views.py, 7.390 Zeilen) |
| „11 Tool-Gruppen, 40+ Tools" | **23 Gruppen-Instanzen / 27 Präfixe / 171 Tools** (tool_registry.py:555–600) |
| „8 Trace-Link-Typen" | **15** (traceability/types.py:25–59) |
| „Axios-Client mit auto Bearer-Token-Injection" | **fetch-Wrapper + httpOnly-Cookie-Auth** (api/client.ts) — Doku beschreibt ein altes/falsches Sicherheitsmodell |
| „17 Component-Bereiche" | **41** |
| „111 E2E-Tests" | **274** (`test()`-Aufrufe in 49 Specs) |
| „~1.400 pytest-Tests" | **5.768 gesammelte** (387 Dateien), 1.427 REQ-Referenzen |

→ **Fix:** Header-Regeneration aus Code-Buchhaltung (Tool-Manifest-Script erweitern, ViewSet-Zähler emittieren), README-Teststatistik aktualisieren.

---

## 3. Konsolidierte Top-Prioritäten (dedupliziert)

### P0 — vor dem nächsten Release

1. **[HIGH] Dependency-Lock ist EOL:** `requirements.lock` schient Django 4.2.30 (6 unpatched CVEs) + cryptography 49.0.0 (< geforderter PYSEC-2026-3552-Floor). → Lock neu erzeugen + Drift-Check in CI (requirements.txt ist korrekt auf 5.2).
2. **[HIGH] RLS-Lücken auf ~20 tenant-scoped Tabellen** (pl_stakeholder_need, pl_test_run(_result), pl_glossary_term(+version), pl_custom_field_*, audit_entry, we_*, bl_baseline_snapshot, diagram_*, icd_*, sm_*, …): ORM-Schicht schützt, DB-Backstop fehlt. → Nachzugs-Migration + Lint „TenantScopedModel ohne RLS-Migration = CI-Fehler".
3. **[HIGH] Toke EventBus-Pfad:**
   - (a) Subscriber-Fehler werden verschluckt → Retry/DLQ toter Code → **Lost Events** (application/event_bus.py:186–216);
   - (b) Outbox-Insert erst in `on_commit` → Crash zwischen Commit und Callback verliert Event dauerhaft (event_bus.py:152–168);
   - (c) WebhookDispatcher wird **nie registriert** → Webhooks produktiv tot (webhook_dispatcher.py:12–15, context_graph/apps.py:5–9).
4. **[HIGH] Kein Throttling auf irgendeinem MCP-Endpoint** (mcp_server/views.py): Brute-Force auf `reqlo_`-Keys, DoS via SSE-Session-Erstellung, unbegrenzter LLM-Aufwand pro Key.
5. **[HIGH] MCP-Dispatch-Catch-all leakt `str(exc)`** (protocol_handler.py:518–522, CWE-209) — widerspricht der eigenen Maskierungsrichtlinie (fix #108). Gleiches Muster in rest_api/metrics_views.py:81 + icd_views.py (8 Stellen).
6. **[HIGH] Keine Celery-Task-Time-Limits** (settings.py/celery.py): dokumentierte Env-Vars (llm_adapter/dispatcher.py:26–27) werden nie gelesen → hängender LLM-Task blockiert Single-Worker inkl. 5s-Outbox.
7. **[HIGH] Redis-Eviction-Policy kann Broker lahmlegen:** `volatile-lru` + Queue-Messages ohne TTL + 256mb maxmemory == 256M cgroup (AOF-Rewrite-OOM). Healthcheck (`ping`) bleibt dabei grün. → Broker/Cache trennen oder `noeviction` für Broker, cgroup ≥ 2×.
8. **[HIGH] Test-Settings kontaminiert durch Root-`.env`:** `LLM_SYNC_TIMEOUT=240` und CSRF-LAN-IPs leaken via decouple in settings_test → 2 deterministisch rote Tests; `test_mcp_api_key_roles.py:400` macht Live-HTTP ohne Stack (kein skipif).
9. **[HIGH] Dead unauthenticated Endpoints in se_metrics/views.py** (`_check_auth` prüft nur Header-Präsenz, hardcoded `DEFAULT_TENANT_ID=1`, unscoped Queries) — nicht gemounted, aber „one `path()` away" vom Auth-Bypass. → löschen oder reparieren.

### P1 — zeitnah

10. **[HIGH fachlich] Traceability-Matrix ~3× veraltet und behauptet trotzdem 100 %** („REQ-L1 33/33, REQ-L2 142/142, lückenlos"): real 97 REQ-L1, ~293 REQ-L2 in 20 Systemen. SN-Implementation-States ebenso falsch („Not Implemented" für implementierte Features). → Matrix-Regeneration automatisieren.
11. **[HIGH fachlich] L0–L4-Mapping-Konflikt:** Enum 0=System…4=Material (persistence/models.py:188–192) vs. Kaskaden-Schema REQ-L0=Needs…REQ-L3=Component/L4=Presentation; `decompose()` setzt child.level gar nicht (requirement_service.py:833–839) → REQ-153-Feld ist dekorativ. → ADR-Entscheid + Level-Progression-Audit-Regel.
12. **[MEDIUM] Layer-Verletzungen:** auth_tenancy (Layer 0) importiert systematisch `application` (9 Fundstellen, z.B. services/authorization.py:27); workflow status-mirror kennt Layer-2-Modelle (lifecycle_manager.py:445–449); persistence→workflow-Import (models.py:1168, 1220); presets/gate.py:91–102 nutzt `unscoped` mit fremder workspace_id ohne Tenant-Check.
13. **[MEDIUM] REST-Fehlerhüllen divergieren** (3 Formen: build_error_response vs. `{"error","message"}` vs. Auth-Doc-URL-Form) + 9 Write-Handler umgehen Serializer-Validierung (FreeTextSanitization-Docstring); Glossary antwortet mit rohem `term.__dict__` (views.py:6818–6834).
14. **[MEDIUM] sync-LLM-Pfad:** `input_tokens=0` → Token-Budget blind für den Sync-Pfad (ai_derivation_service.py:1779–1783); LLM-Call innerhalb `@atomic_transaction` (main_goal_service.py:113–191); Mock-Fallback in AI-Derivation-Drafts **nicht markiert** (nur requirement_bundle surfen `is_mock_fallback` sauber).
15. **[MEDIUM] Cache-/Consistency-Defizite:** PermissionCache-Invalidierung nur pro Thread (bis 60s stale Allow-Entscheidungen nach Revoke, permission_cache.py:125–128); presets-Prozess-Cache ohne Cross-Worker-Invalidierung; MainGoal-`sequence_number`-Race (read-then-write ohne Lock); PolicyEngine-Timeout blockt bis zum realen Ende (kein Wallclock-Cutoff).
16. **[MEDIUM] Prod-Gaps:** Static-Files für /admin//Swagger broken (collectstatic gebacken, nichts served); fehlende Cookie-Hardenings (SESSION_COOKIE_SECURE etc.); kein Connection-Pooling (CONN_MAX_AGE=0); kein Request-ID-Logging; keine Metrics/Tracing; keine Image-Scans/SBOM/Signierung im Release; `frontend: user: root` konterkariert Non-Root-Hardening; INFRA-03-Regression (concurrency nicht gepinnt in ghcr.yml).
17. **[MEDIUM] CSV-Formel-Injektion im Workspace-Export** (export_service.py:211 `_csv_cell` — Bundle-Pfad neutralisiert, dieser nicht) + Refresh-Rotation ohne Reuse-Detection (auth_views.py:330–345).

### P2 — Hygiene

i18n-145-Key-Backlog (#619) · data-testid-Lücken (DiagramGraphEditor, PageHeader, Dialoge) · 9 hardcoded-Farben · 3 Tree-Implementierungen parallel · `supersedes`-Phantom-Link-Typ (Audit-Regeln filtern einen Typ, der im Produkt nie existiert) · Soft-Delete-Semantik inkonsistent je Entitätstyp · Custom-Presets nur in-memory · stdio-Transport tot · doppelt gemountete tracelinks-Routen · OpenAPI `COMMON_ERROR_RESPONSES` tot · Coverage-Gates fehlen (backend & frontend).

---

## 4. Detail-Sectionen

### 4.1 Backend Layer 0/1 (persistence, auth_tenancy, presets, audit, llm_adapter, traceability, workflow, baseline)

**ADR-Konformität:**

| ADR | Verdict | Evidenz |
|---|---|---|
| ADR-02 LLM-Provider-Abstraktion | ✅ conforms | interface.py:90–227, router.py:121–144/290–344; klein: Fehlerklassifizierung per Message-String-Matching („429" in msg, router.py:321–331) — fragil |
| ADR-03 TenantContext + RLS | ✅ conforms (Escape-Hatch-Resten) | tenancy.py:73–80/135–143; RLS-Migrationen 0003/0010/0061; db_roles.py; SET-vs-SET-LOCAL dokumentiert (middleware.py:40–47) |
| ADR-04 3 Rigor-Presets | ✅ conforms | presets/registry.py:61–206, gate.py; WorkspacePresetConfig als OneToOne-Companion |
| ADR-06 State-Machines | ✅ conforms | workflow/models.py:94–178; Global-Defaults je (tenant, item_type, preset); Materialized-Copy + reset_to_global |
| ADR-07 3 Baseline-Scopes | ✅ conforms | baseline/models.py:52–70; Preset-Gate (delta_index_builder.py:466–483); Hinweis: `BaselineDeltaIndexEntry` bewusst non-tenant, jeder Zugriff mit tenant-Guard (store.py:154/268) |
| 15 Trace-Link-Typen | ✅ conforms | types.py:25–59 inkl. diagram-ref als Reconciler-only-Typ (types.py:69–79) |

**Stärken (verifiziert):**

1. Zweistufige Tenant-Isolation mit Fail-fast: Filter als einziger Enforcement-Punkt + PostgreSQL-RLS-Backstop + Least-Privilege-Rolle; fehlender Kontext bricht **vor** SQL-Generierung ab (`TenantContextNotSetError`).
2. Append-only **doppelt erzwungen** (AuditEntry, WorkflowHistoryEntry, Baselines): Application-Layer-Guards UND DB-Trigger; Export-before-Drop-Archivierung fail-safe.
3. Race-Sicherheit an kritischen Pfaden: `select_for_update` + version-CAS im Workflow-Transition (lifecycle_manager.py:286–330), Last-Admin-Invariante sperrt alle Admin-Zeilen (authorization.py:768–847), Tenant-Zeilen-Mutex für PromptTemplate/PromptVariable-Scope-Uniqueness (models.py:1973–2021), IntegrityError-Retry bei `ensure_item_state`.
4. Ausnahmelose Nachvollziehbarkeit: nahezu jede Zeile trägt REQ-/ARCH-/Issue-Referenz mit Begründung.
5. Graceful degradation konsequent: LLM-Mock-Default ohne Credentials, strukturierte Fehler-Dicts, fail-open Token-Accounting, fail-closed `shadow_decide`.

**Befunde (17):**

| # | Schwere | Ort | Titel |
|---|---|---|---|
| 1 | HIGH | auth_tenancy (9 Fundstellen: services/authorization.py:27, item_permission.py:38, preference_service.py:25, permission_definition.py:26, rest_workspace_members.py:40, rest_item_permission.py:56, bootstrap_admin.py:42, seed_demo.py:33, seed_toothbrush.py:32–42) | Systematische Layer-0→2-Import-Verletzung (`application`-Importe: NotFoundError, ServiceBase) — Zyklenrisiko, widerspricht eigener Architektur-Doku → Basisklassen heben oder Interface extrahieren |
| 2 | MEDIUM | workflow (lifecycle_manager.py:80–95/445–449, backfill-Kommandos) | Layer-1→2-Importe: Status-Mirror-Kern kennt `application.models` → Mirror-Registry invertieren |
| 3 | MEDIUM | traceability/service.py:190/511, baseline/state_capture.py:247/404 | Lazy `application`/`icd`-Importe verletzen Schichtenmodell → Provider-Schnittstelle |
| 4 | MEDIUM | llm_adapter (resilient_transport.py:26–34, embedding_service.py:101) | Ext-Layer-Importe (resilience, memory) → resilient_call hinter Interface kapseln |
| 5 | MEDIUM | persistence/models.py:1168/1220 | Layer-0→1-Import (`workflow.services.outdated_item_ids` in annotate_roles/get_role) — im Code als deliberate dokumentiert → Status-Provider injizieren |
| 6 | MEDIUM | presets/gate.py:91/102 | Cross-Tenant-Pfad: `Workspace.unscoped` + `WorkspacePresetConfig.unscoped` mit caller-gelieferter workspace_id ohne Tenant-Check → Tenant-Abgleich erzwingen |
| 7 | MEDIUM | auth_tenancy/services/permission_cache.py:125–128 | PermissionCache-Invalidierung nur pro Thread → bis 60s stale Allow-Entscheidungen nach Revoke → Redis-Generation-Counter oder TTL senken |
| 8 | MEDIUM | presets/gate.py:54–57/161–170 | Multi-Worker-Cache-Stale (`_tier_cache`/`_profile_cache` prozess-lokal) → Redis-basierte Invalidierung |
| 9 | MEDIUM | audit/archive.py:446–450 + settings.py:568–573 | Archivierungs-Task `audit.archive_lifecycle_manager` nicht in CELERY_BEAT_SCHEDULE → monatliche Archivierung läuft nie automatisch |
| 10 | LOW | llm_adapter/router.py:371–408 | Sync-Timeout-Thread ohne RLS-Session-Var (nur `TenantContext.set_tenant()`, kein `SET app.current_tenant`) — Kontrast: tasks.py:133–146 fixt dieses Muster für Celery (#444) |
| 11 | LOW | auth_tenancy/services/authentication.py:301–318 | API-Key-Max-TOCTOU (count-then-create ohne Lock) → kosmetisch |
| 12 | LOW | baseline/views.py:72–146 | `scope_preview` mit AllowAny — kein Cross-Tenant-Leak (leer ohne Kontext), aber anonyme Aufrufer erhalten 200 statt 401; Cookie-Auth zählt nur Staff-Check → IsAuthenticated + Workspace-RBAC |
| 13 | LOW | presets/gate.py:251–269 | switch_preset lost-update (read-modify-write ohne select_for_update) |
| 14 | LOW | audit/models.py:315–327, writer.py:206 | Redundanter EXISTS-Query je Insert + unidiomatisches Save → Guard nur bei `adding is False` |
| 15 | INFO | traceability/models.py:1–20 | Reine TODO-Stub-Datei; TraceLink gehört persistence → Doku-Debt |
| 16 | INFO | audit/models.py:153–193 | op-Vokabular als dokumentierte, wiederkehrende Fehlerquelle (#265/#539/#573/#626): REST-Pfad scheitert mit 500 nach erfolgreicher Mutation, MCP-Pfad schweigend ohne Audit-Zeile; Schutznetz existiert (test_op_vocabulary.py) |
| 17 | INFO | persistence N+1-Management | Systematisch adressiert: Bulk-CTE-Alternativen annotate_levels/annotate_roles (1 Query), Composite-Indizes (#127/#130/REQ-039) |

**Offene Fragen an den Lead:** (1) `application`-Importe in auth_tenancy — akzeptierte Ausnahme oder Refactor? (2) Archivierungs-Task via Beat oder DB-Eintrag binden? (3) presets-Gate `unscoped` — bewusster Verzicht? (4) scope_preview AllowAny gewollt? (5) `makemigrations --check` als CI-Gate?

### 4.2 Backend Layer 2 + Extension-Apps (application ×34 Services, diagram, icd, se_metrics, resilience, admin_ops, test_runs, context_graph, memory)

**ADR-01 Single-Entry-Point: durchgesetzt für alle Write-Pfade.** Ratchet-Test erzwingt 0 direkte ORM-Zeilen in rest_api/views.py (test_views.py:1331–1334). Verbleibende Non-Test-Bypasses (read-only/Enum):

1. rest_api/diagram_views.py:143 — `Diagram.objects.filter` in `list()` trotz Fassade
2. rest_api/diagram_canvas_views.py:94 — `Diagram.objects.get`
3. rest_api/icd_views.py:175 — `Icd.objects.filter` in `list()`
4. rest_api/serializers.py:39/465 — Enum-/Validator-Nutzung (kein Query)
5. mcp_server/tools/cross_cutting.py:1269–1404 — read-only Queries, explizit tenant-gefiltert
6. mcp_server/tools/users.py — read-only, dokumentiert (users.py:70–93); Writes delegieren korrekt
7. mcp_server/tool_registry.py:1032–1038 — Existenz-Check

**Invarianten (validators.py):** I1 Zyklus (200–227), I2 Level-Ordering (233–254), I3 dangling/cross-workspace (260–291), I4 allocated-to≠Ancestor (297–325), I5 single Root (331–362); rigor-gated via RIGOR_INVARIANT_PRESETS (minimal={I3,I5}, standard={I1,I2,I3,I5}, extended=alle); Enforcement in ArchitectureService (148/285), TraceLinkService (802–805), REST-Serializer (744–748). Vollständig und fail-safe.

**Resilience-Implementierung:** Policy (exponentieller Backoff, capped) → PolicyEngine (timeout+retry+breaker+degradation) → CircuitBreaker (State in DB, UniqueConstraint tenant+target, select_for_update, Half-Open-Single-Probe, fail-safe) → AsyncDispatcher (broker-optional) → DegradationManager. Applied ausschließlich auf LLM-HTTP-Calls (providers.py:889). **WebhookDispatcher nutzt Resilience NICHT.**

**LLM-Flow:** Mock-Fallback immer markiert & nie gecached; Cache-Keys tenant+provider-namespaced mit Generations-Invalidierung; Cache-Eviction bei unusable Antworten; Retry-Loop; pro-purpose Timeouts; vollständiger Audit-Trail; Thread-Safety-Fix #552. Async-Wiring via Celery mit Tenant-Restore (#444) und Teardown-Guard (#522).

**Befunde (14):**

| # | Schwere | Ort | Titel |
|---|---|---|---|
| 1 | HIGH | application/event_bus.py:186–216 (+284–320) | Subscriber-Fehler verschluckt → Retry/DLQ toter Code → Events als published markiert trotz Totalversagen → **Lost Events** trotz at-least-once-Doku |
| 2 | HIGH | application/event_bus.py:152–168 | Outbox-Insert erst in on_commit — kein echtes Transactional-Outbox; Crash zwischen Commit und Callback verliert Event |
| 3 | HIGH | application/webhook_dispatcher.py:12–15 + context_graph/apps.py:5–9 | WebhookDispatcher nie registriert (subscribe_to_events existiert, wird nie gerufen) → Webhooks produktiv tot |
| 4 | MEDIUM | event_bus.py:264–291 + webhook_dispatcher.py:55–57 | Sync-HTTP im Outbox-Claim-TX → Row-Lock + offene Connection über externe I/O blockiert Poll-Zyklus |
| 5 | MEDIUM | resilience/policy_engine.py:112–134 | Timeout ohne Wallclock-Garantie: nach Timeout blockt `shutdown(wait=True)` bis zum realen Ende; Worst-Case (retries+1)×Dauer; Docstring-Claim „hard timeout" unzutreffend |
| 6 | MEDIUM | application/main_goal_service.py:225–230 | Race bei sequence_number (read-then-write ohne Lock/Constraint) |
| 7 | MEDIUM | application/main_goal_service.py:113–191 | LLM-Call innerhalb @atomic_transaction → Connection-/Lock-Haltezeit |
| 8 | MEDIUM | ai_derivation_service.py:1779–1783 + bundle_compression_service.py:666–670 | Sync-LLM-Spend unsichtbar fürs Budget (`record_token_usage(input_tokens=0)`); nur Async-Pfad approximiert real |
| 9 | MEDIUM | rest_api/diagram_views.py:143, diagram_canvas_views.py:94, icd_views.py:175 | Direkte Model-Queries in DRF-Views trotz Fassade (ADR-01-Buchstabenverstoß) |
| 10 | LOW | resilience/circuit_breaker.py:155–178 | `_locked_or_create`-Race: IntegrityError ungefangen → 500 statt Retry |
| 11 | LOW | circuit_breaker.py:126–151 | failure_count ohne Zeitfenster — alter Fehlercluster trippt Breaker beliebig viel später |
| 12 | LOW | event_bus.py:293–312 | DLQ-Umzug innerhalb der Claim-TX — schlägt fehl → Row ewig published=False |
| 13 | LOW | rest_api/serializers.py:39 | persistence.models.ElementType-Import im Serializer-Layer (Enum) |
| 14 | INFO | mcp_server/tools/users.py:857 | user.list direkte User-Queries dokumentiert (User nicht TenantScoped, expliziter tenant_id-Filter) |

**Offene Fragen:** (1) Ist `application.dispatch_outbox_events` in Beat registriert (ja: settings.py:568–573, Outbox alle 5s)? (2) Optimistic Locking nur bei ArchitectureService — Absicht oder Lücke (Requirement/TestCase bumpen version ohne expected_version-Check)? (3) I2 nur direktes Element oder Teilbäume? (4) Webhook-Async-Umbau priorisiert? (5) Budget-Blindheit des Sync-Pfads akzeptiert?

### 4.3 REST API (28 ViewSets, ~66 APIViews) + MCP Server (171 Tools)

**REST-Standardkonfiguration** (settings.py:394–437): AuthTenancyAuthentication (Bearer JWT **oder** X-API-Key/Bearer `reqlo_`) + SessionAuthentication (CSRF-Gate) + RbacPermission (HTTP-Methode→Operation: GET→READ, sonst WRITE; per-View überschreibbar via required_operation) + globale Throttles user 600/min, anon 120/min (prod) + kanonischer Error-Envelope.

**REST-Inventar (Auszug, vollständige Tabelle im Teil-Report):** 25 Router-Registrierungen / 24 Ressourcen — artifacts, requirements (+8 @actions), needs, architecture (+requirement-bundle), testcases, tracelinks **doppelt gemountet** (urls.py:162+169), traceability, baselines, workflows, workspaces, adrs/risks/issues, goals, main-goals, change-requests, test-runs (+results/bulk), search, api-keys, diagrams, icds, metrics, attribute-visibility-configs, glossary, interviews. WorkflowMixin-Aktionen auf 12 ViewSets (transitions/reactivate/workflow-history). ~90 explizite Routen (auth/login|refresh|logout|me, CSV/ReqIF-Import/Export, users, admin_ops, llm-settings, prompt-templates/variables, workflow-defaults, permission-defaults/mismatches, memory, system/*). Öffentliche Fläche: login, refresh, public banner, schema/swagger-ui, /health/, /api/v1/version/, GET /mcp/. **Kein Endpoint ohne Permission-Klasse.**

**MCP-Inventar:** 171 Tools / 27 Präfixe / 23 Gruppen-Instanzen — requirement(10), needs(8), architecture(9), test(12), cross_cutting(12), workspace(4), permissions(4), admin(3), audit/events(4), user(9), GenericCrud ×5 adr/risk/issue/glossary/change_request(35), prompt_template(4), prompt_variable(4), ai_derivation(6), diagram(6), custom_field(2), review(4), baseline(4), goal/main_goal(15), requirement_bundle(3), interview(10), memory(3). Zugriffssteuerung 5-schichtig: API-Key-Pflicht (`reqlo_`, JWT bewusst abgelehnt) → workspace-scoped Role-Resolution → **fail-closed RBAC** (unbekanntes Tool = WRITE) → Preset-Feature-Gate (TTL-LRU 5min) → Ausführung. Audit für Writes via write_mcp_audit (Key nur SHA-256).

**MCP JSON-RPC 2.0-Konformität: WESENTLICH KONFORM (2024-11-05), 4 Abweichungen:**

| Aspekt | Urteil | Beweis |
|---|---|---|
| Error-Codes -32700/-32600/-32601/-32602/-32603 + Server-Bereich | ✅ | protocol_handler.py:100–111 |
| Tool-Fehler → `isError:true` (Protokollfehler bleiben JSON-RPC-Fehler) | ✅ | :539–558 + Tests |
| `initialize` Handshake | ⚠️ fixe Version 2024-11-05, keine Negotiation | :441–453 |
| Benachrichtigungen | ⚠️ id-lose Frames ≠ `notifications/initialized` erhalten INVALID_REQUEST-**Antwort** (verletzt JSON-RPC 2.0 „MUST NOT reply"); 0 Notification-Tests | :181–184/:423–430 |
| Batching | ⚠️ Arrays → INVALID_REQUEST (MCP 2024-11-05 verlangt keine Batches — dokumentieren) | :175–176 |
| Auth | ✅ Header-only (query/body-Keys abgelehnt), JWT abgelehnt mit klarer Meldung | registry:802–818 |
| SSE-Session | ✅ Redis-gebunden TTL 8h, hmac.compare_digest, Last-Event-ID-Replay, SESSION_EXPIRED unterscheidbar (#427) | views.py:446–612, sse_pubsub.py |
| HTTP-Status-Abbildung | ⚠️ PARSE_ERROR/INVALID_REQUEST → **401** (400 erwartet) | views.py:186–206 |
| Fehlerform | ⚠️ numerisch `code` vs. String `error_code` am selben Interface | protocol_handler.py:210–216 vs. views.py:322–329 |
| stdio-Transport | ⚠️ Adapter + Tests vorhanden, **kein Laufzeiteinstieg** (dead) | protocol_handler.py:288–306 |

**REST-Design-Bewertung:** Statuscodes stark (400/401-Ordnungstest #271, 409 OptimisticLock, 400 SE_AUDITOR_BLOCKED, 503 Preset-unavailable, JSON-handler404) · Fehlerhülle: kanonisch, aber **3 abweichende Formen** · Paginierung: PageNumber 25/max100 (Docstring sagt fälschlich „offset-based") · Filterung: handgerollt; globale OrderingFilter/SearchFilter (settings.py:412–415) **weitgehend ungenutzt/tot** · Versionierung: URI-Präfix only, kein Deprecation-Sunset · Idempotenz: kein Idempotency-Key; DELETE=Soft-Delete; PATCH mit expected_version (409) · OpenAPI: drf-spectacular + BearerAuth, aber `COMMON_ERROR_RESPONSES` toter Code, nur ~10/200 Operationen mit extend_schema · Mass-Assignment: niedriges Risiko (explizite Serializer + FreeTextSanitizationMixin) — aber 9 Write-Handler lesen `request.data` direkt, TestCaseSerializer (#580) einer von nur 2 mit unbekannt-Felder-Ablehnung.

**REST↔MCP-Parität:**
- Nur MCP: context.query/related/change_impact/test_coverage, review.approve/reject/request_changes, events.dlq_*, workspace.llm_system_prompt, artifact.get_tree, ai_derivation.glossary/adr, interview.set_target, memory.*, requirement.check_consistency
- Nur REST: **ICDs komplett ohne `icd.*`-Tools** (MBSE-Kernfähigkeit!), CSV/ReqIF-Import/Export, PDF-Report, Diff/versions für 7 Entitätstypen, metrics, llm-settings, Banner/Themes, workflow-defaults, attribute-visibility, custom-field-writes, workspace.clone, interview chat/by-artifact
- Verhaltensdivergenzen: Auth-Modell (REST=JWT+API-Key, MCP=API-Key-only, bewusst), Workflow-Transitions (REST generisch, MCP nur outdate/reactivate + Review-Tools), Fehlerform-Spaltung

**Befunde (19):**

| # | Schwere | Ort | Titel |
|---|---|---|---|
| F-01 | HIGH | mcp_server/views.py (alle 3 Views) | Kein Throttling/Rate-Limit auf irgendeinem MCP-Endpoint (DRF-Defaults greifen nicht für plain Django-Views) |
| F-02 | HIGH | protocol_handler.py:518–522 | Dispatch-Catch-all gibt `str(exc)` an Client (CWE-209, widerspricht fix #108-Maskierung) |
| F-03 | HIGH | api_key_views.py:112–115, user_management_views.py, auth_tenancy/rest.py:104–119 | Divergierende REST-Fehlerhüllen (3 Formen) — Frontend-`extractErrorMessage` erwartet `error.details[…]` |
| F-04 | HIGH | mixins/free_text_sanitization.py-Docstring + views.py:6822–6834 | 9 Write-Handler umgehen Serializer-Validierung; Glossary antwortet mit rohem `term.__dict__` (verlässt deklarierten Vertrag, `_state`-Leak möglich) |
| F-05 | MEDIUM | views.py:191–196 | MCP HTTP-Status: PARSE_ERROR/INVALID_REQUEST → 401 → falsche Client-Retry/Re-Auth-Schleifen |
| F-06 | MEDIUM | protocol_handler.py:181–184/:423–430 | Antworten auf Notifications; 0 Notification-Tests |
| F-07 | MEDIUM | protocol_handler.py:45/441–453 | Protokollversion fix 2024-11-05, keine Verhandlung, Streamable-HTTP-Ära nicht abgedeckt |
| F-08 | MEDIUM | openapi.py:71–98 | COMMON_ERROR_RESPONSES toter Code; extend_schema nur ~10/200 → generisches Schema für Custom-Aktionen |
| F-09 | MEDIUM | rest_api/metrics_views.py:45–46 | TenantContext-Hygiene: set_tenant ohne finally/clear (Kontrast: tool_registry try/finally 712–787) → Thread-Local-Leak über Poolworker |
| F-10 | MEDIUM | diagram_views.py:60, icd_views.py:63, interview_views.py:97 | Plain ViewSets umgehen BaseEntityViewSet-Guards (malformed-UUID-400, FreeTextSanitization, Preset-Gate) |
| F-11 | MEDIUM | protocol_handler.py:210–216 vs. views.py:322–329 | MCP-Fehlerform-Spaltung (numerisch vs. String) |
| F-12 | LOW | global | Keine JSON-Bulk-/Idempotency-Mittel (N-Anfragen-Sync; Retries können Duplikate erzeugen) |
| F-13 | LOW | AGENTS.md/Anspruch | Interface-Doku massiv veraltet (16/11/40+ vs. real 28/66/23/171); test_e2e_all_tools.py:1–33 Docstring „40 tools total" |
| F-14 | LOW | protocol_handler.py:288–306 | stdio-Transport tot zur Laufzeit (kein Serve-Einstieg; Modul-Docstring „stdio, SSE und HTTP" überverkauft) |
| F-15 | LOW | tool_registry.py:133 | `_WRITE_TOOL_PREFIXES` listet nicht existierendes prompt_template.delete (harmlos, fail-closed, aber Katalog-Drift) |
| F-16 | LOW | urls.py:162/169 | tracelinks + trace-links doppelte Registrierung → OpenAPI-Duplikate |
| F-17 | LOW | settings.py:412–415 vs. views.py:719–729 | Globale OrderingFilter/SearchFilter konfiguriert, aber auf ViewSet-Architektur wirkungslos (tote Konfiguration) |
| F-18 | INFO | urls.py:656–667 | Öffentliches Schema/Swagger-UI (durch REQ-L3-RA005-001, akzeptiertes Risiko) |
| F-19 | INFO | reqogniloom/urls.py:51–52 | MCP doppelt gemountet /mcp/ + /api/v1/mcp/ (harmlos, Catch-all danach korrekt geordnet) |

**Offene Fragen:** (1) MCP-Throttle pro API-Key oder IP; LLM-Aufwand-bewusst? (2) Protokoll-Zielversion (frozen 2024-11-05 vs. Streamable-HTTP 2025-03-26+)? (3) ICD-Parität gewollt? (4) Diff/versions als MCP-Tools? (5) Serialisierer-Vollendung getrackt? (6) Frontend abhängig von Glossary-Roh-`__dict__`? (7) `interview.grounding_context` durch Write-Gate für Viewer versteckt — gewollt? (8) Baseline-Gate 404-vs-403-Semantik bestätigen.

### 4.4 Frontend/UI (41 Component-Areas, ~35 Routen)

**Architektur:** App.tsx:55 Provider-Kaskade (Theme → QueryClient → Router → Auth → Workspace → NavigationShell); ~35 Routen, alle `lazy()` mit Suspense+ErrorBoundary; 4 Contexts (Auth, Workspace, Theme, EntityType) + TanStack Query (staleTime 30s, retry 3× exp. Backoff, auth-errors nicht retry, mutations nie retry) + 5 handgerollte Data-Hooks (Inkonsistenz) + ~60 API-Domain-Wrapper. **Kein Axios** — zentraler fetch-Wrapper api/client.ts (getList/getAllPages mit Pagination-Follow + 100-Seiten-Cap + Truncation-Warnung).

**Auth-Flow (besser als dokumentiert):** httpOnly-Cookie `reqflow_access` (REQ-052) — **nie** in JS/sessionStorage (Regressionstest verifiziert: AuthContext.test.tsx:89–120); X-CSRFToken aus csrftoken-Cookie auf allen unsafe Methods (client.ts:213–218); 401 → single-flight silent refresh + Retry einmalig, parallele 401s teilen Refresh, Notify-Guard max 1×/Session (client.ts:42–109/262–282); 403→ForbiddenError ohne Logout, 422→typed Error; Timeouts 30s default / 180s LLM (130–169); Login ignoriert Body-Token (Phase-1-Compat); Session-Restore mit „restoring"-State gegen Login-Flash; Redirect-Back nach Login. Storage sauber: sessionStorage nur workspace_id + Listen-Filter, localStorage nur Theme-Palette-Cache. Rollen-Gating UI-seitig (6 Bereiche admin, isTenantAdmin für UserManagement) — Enforcement serverseitig (korrektes Muster).

**i18n:** i18next, lng=Browser-Sprache, fallback en; Workspace-Sprache nach Load re-appliziert mit 3 Schutz-Guards (WorkspaceContext.tsx:324–341); Accept-Language an API. **DE/EN-Parität: vollständig (0 fehlende Keys), maschinell erzwungen** (test/i18n-parity.test.ts:48–59, beide Dateien exakt 1826 Zeilen). **ABER: 145 Keys im Code referenziert, die in BEIDEN Locales fehlen** (Ratchet-Baseline, Historie 174→180→145); aktive Gaps: VersionPanel.tsx:206/225/240 (3× TODO(i18n), `sidebar.version.retry` etc.); Impact: `t(key,"default")` leakt Englisch im DE-UI.

**Design-Tokens:** styles/tokens.css (~1500+ Zeilen), 2-Layer (Primitives --palette-* / Semantics --color-*), **5 Themes** (dark=default, light, bauhaus, nordic, sepia) via data-theme; Compliance maschinell erzwungen (test/ui-ratchet.test.ts, 672 Zeilen: raw-hex nur in tokens.css; theme-contrast.test.ts: WCAG AA 4.5:1). Verstoßzählung: **9 Fundstellen in 7 Dateien + 1 Rest-Hex** (MetricsDashboard.tsx:245/547/565–566, MismatchReviewTable.tsx:226, LoginPage.tsx:223, CanvasEditor.tsx:491 [canvas-API], BackupRestoreSection.tsx:270, EnforcementModePanel.tsx:148, ApiKeysSection.tsx:369, workspace-tree.tsx:53 `#06B6D4` dokumentiert „no matching token yet").

**data-testid:** sehr hohe Dichte (>100 Matches nur in components/); Formulare/Listen/Dialoge durchgehend. **Lücken:** GraphToolbar.tsx:45–103 (6 Buttons), GraphInspectorPanel.tsx:107–424 (4), DiagramGraphEditorPage.tsx:309–422 (6), TraceabilityView.tsx:212/927, TraceLinksForm.tsx:326/583, PageHeader.tsx:186–252 (4), RightSidebar.tsx:282–348 (6), TraceSpine.tsx (4), EmptyState.tsx (3), ConfirmDialog.tsx:43–51 — mehrheitlich mit aria-label/i18n-Title statt testid (Playwright-Mandat verletzt).

**A11y stark:** Dialog.tsx — role=dialog + aria-modal + labelledby/describedby, Focus-Trap, Escape, Focus-Restore, Scroll-Lock, Portal (vollständiger Vertragstest Dialog.test.tsx:80–374); aria-busy/expanded/invalid/live, role=alert/status/listbox; Form-Errors mit aria-invalid+describedby; eslint-plugin-jsx-a11y; dedizierte a11y-Tests (WorkflowEditorCanvas-a11y.test.tsx); semantische Buttons überall. **Gap:** hardcoded-EN aria-labels (SidebarNavigation.tsx:439/471/599, MismatchReviewTable.tsx:149–188, InterviewWidget.tsx:115).

**TypeScript:** strict + noUnusedLocals/Parameters (tsconfig.json:18–21); `as any` fast nur in Tests (~60 Fundstellen); **kein** @ts-ignore/@ts-nocheck in src; Typen spiegeln Serializer mit Drift-Guards (#344, types/index.ts:85–90).

**Befunde (13):**

| # | Schwere | Ort | Titel |
|---|---|---|---|
| 1 | MEDIUM | test/i18n-parity.test.ts:137 | 145 i18n-Keys in keiner Locale — Ratchet-Baseline gefroren; Englisch-Leak im DE-UI (VersionPanel TODO(i18n)) → Backlog #619 abbauen |
| 2 | MEDIUM | GraphToolbar.tsx:45–103 u.a. | Buttons ohne data-testid — Playwright-Mandat → testids ergänzen |
| 3 | LOW | AGENTS.md Entry-Point | „Axios + auto Bearer token injection" falsch — Code ist fetch-Wrapper + httpOnly-Cookie → AGENTS.md korrigieren |
| 4 | LOW | 9 Stellen (s.o.) | Hardcoded Farben in TSX-Inline-Styles → Tokens ergänzen (grün 22,163,74 ×3 → Badge-Token-Kandidat) |
| 5 | LOW | SidebarNavigation.tsx:439/471/599 u.a. | Hardcoded-EN aria-labels → t()-Aufrufe |
| 6 | LOW | ui-ratchet.test.ts:492–519 | 3 Tree-Implementierungen parallel (WorkspaceTree, RequirementTreeNode, GoalsTree) — dokumentiertes Duplikat → Konsolidierung |
| 7 | LOW | hooks/use*Data.tsx vs. queries/ | Geteiltes Data-Fetching-Paradigma: 5 Domains handgerollt, 2 react-query → inkonsistente Cache-/Invalidation-Semantik → Migration auf react-query |
| 8 | INFO | workspace-tree.tsx (1130 Z.), TraceabilityView.tsx (999), audit-dashboard.tsx (815), BaselinesView.tsx (755+), types/index.ts (954) | Größte Dateien (>500-Zeilen-Kriterium) |
| 9 | INFO | AuthContext.tsx:57–63 | `LoginResponse.token` typisiert, bewusst ignoriert (Phase-1-Compat) — dead field, dokumentiert |
| 10 | INFO | types/index.ts:46–53 | `Workspace.ai_prompts` @deprecated („no longer read or written by the UI") |
| 11 | INFO | index.tsx:33 | `(window as any).React = React` Global-Injection (esbuild-Workaround, begründet) |
| 12 | INFO | 6 TODOs gesamt (RequirementList.tsx:15, TestRunDetailEditor.tsx:12, i18n/index.ts:7, VersionPanel.tsx:206/225/240) | Kein FIXME/HACK; TODOs klein und dokumentiert |
| 13 | INFO | — | Performance-Basics: volle Route-Lazy-Loading, Virtualisierung (@tanstack/react-virtual: workspace-tree + Issue/TestCase/Adr-Listen), memo an 6 Hot-Spots |

**Offene Fragen:** (1) E2E-Exact-Count via `playwright test --list` (grep-Cap erreicht — „111" plausibel veraltet, 274 zählt `test()`-Aufrufe). (2) Unit-Test-Datei-Gesamtzahl (~170+, Globs gecapped). (3) `Workspace.theme` serverseitig noch konsumiert? (4) use*Data-Familie bewusst auf react-query-Rückstand?

### 4.5 Fachliche Prüfung (SE/RE/MBSE) — vertieft

**Domain-Modell:**

- **V-Modell-Mapping — der zentrale Konflikt:** Zwei nicht-vereinbare L0-L4-Semantiken gleichzeitig: SE-Kaskade (L0=Needs…L3=Component, L4=Presentation; AGENTS.md, docs/se/*, REQ-ID-Schema) vs. `Requirement.level` (0=System…4=Material; persistence/models.py:188–192, MCP-requirement.create-Schema). Keine verbindliche Zuweisungsregel: `decompose()` erzeugt Kinder **ohne** level-Argument (requirement_service.py:833–839), create nimmt level=None (196), Migration 0040 backfillt bewusst nicht; laut coverage_consistency.py:30 ist `level IS NULL` „the overwhelming majority". **Keine Audit-Regel prüft Level-Progression.** REQ-153 umgesetzt, aber fachlich dekorativ.
- **Link-Typ-Graph (15 Typen, types.py:25–59):** Verifizierte Richtungen — derives-from (child→parent; Matrix), decomposes (parent→child; hardcoded Output von decompose; TRACE-P5-Paar mit derives-from), satisfies (Arch→Req; Req→Need), verifies (TC→Req/Arch; Rule 7 + TRACE-P6 + Rule 6 nutzen dieselbe Richtung ✓), implements (Arch→Req; fachlich fragwürdig), refines (gleichartig ✓), allocated-to (Req→Arch; Ancestor-Invariante + „exactly one allocation" in allocate()), documents (Diagram→*), parent-child/copy-of (gleichartig), traces/realizes/uses-term (uneingeschränkt), decides (ADR→Element; **auch ADR-Supersession** REQ-150, adr_service.py:495–525), diagram-ref (Reconciler-owned, Manual-CRUD blockiert trace_link_service.py:371–376 — sauber gelöst). **Zyklen-Prävention konform:** Tarjan-SCC (CycleDetectedError bei create), Tarjan im Batch-Create, validate_graph_integrity, Audit-seitig hierarchy.py.
- **Workflow-Präsets (definition_store.py):** minimal (draft→done, editor), standard (draft→approved→deprecated, Approver-Gate), extended (…→implemented→verified, REQ-151). Pro Entitätstyp: need/adr (Title Case)/risk/issue/testcase (lowercase GH-453)/architecture/icd/diagram/glossary/goal+main_goal (**Entwurf/Freigegeben/Archiviert**)/interview/ccb_approval. Approval-Gates approver/admin-only; auto_approve_target/is_outdated_equivalent via state_meta (Phase 3); Review-Tools deterministisch (GH-370-Fix).

**Docs↔Code-Konsistenz-Matrix (20 geprüfte Claims):** 12 ✅ conforms (Link-Typen 15, Baseline-Scopes, Rigor-Presets + 14 Entity-Presets, ADR-06 real editierbar + UI, REQ-143 Mirror, REQ-169, REQ-157 CCB + SoD, REQ-012/GH-403, GH-513-Override-Kette, SE-Semantik-Matrix enforcement, V&V §3 = Rule 6 exakt, Deep-Audits vorhanden aber teils veraltet) · 3 ❌ violates (Tool-Zahlen 3× under-claim; „8 Link-Typen"; V-Modell-Mapping-Konflikt) · 5 🟡 partial (LLM-Fallback-Flag im Hauptnutzpfad fehlend; „successfully migrated"-Kopf täuscht; Matrix stale + 100 %-Behauptung falsch; SN-States grob veraltet; L0-Gap-Beschreibung halb veraltet).

**Workflow/Baseline/Rigor-Kohärenz:** Strukturell kohärent mit drei definierten Reibungspunkten: (1) Workflow kohärent — 4(+3)-Regel-Gateway, Rollen-Gates, change_reason kombiniert (REQ-169), SignatureGate, Global-Default→Override→Reset (REQ-178–183), Konfigurierbarkeit real (Edit-Endpunkte + WorkflowEditorPage.tsx). (2) Soft-Delete inkohärent — 4 parallele Mechanismen (outdate→„outdated"; is_outdated_equivalent-States je Preset; ArchitectureElement/GlossaryTerm/Icd/Diagram ohne Status-Mirror, „dead" lifecycle_status-Spalte; Adr Rejected/Superseded + Risk Closed OHNE is_outdated_equivalent-Markierung) → Cross-Entity-Abfragen brauchen typspezifisches Wissen. (3) Baseline robusteste Governance-Kette des Projekts — tier-gesteuerte Scopes, SE-Auditor als Gate, Blocker fail-closed, Override explizit+justifiziert+autorisiert+auditiert (GH-513), Auditor-Malfunction nicht übersteuerbar (GH-400); Delta-Index als freies entity_type-CharField (pragmatisch, keine Typsicherheit).

**Rigor (ADR-04): meaningful, nicht kosmetisch** — Pflichtfelder am Approval-Gate (Rule 5), Feature-Flags wirken (baselines, global_baselines, approval_workflows, custom_workflows, change_reason_mandatory), Scope-Gates, Terminologie schaltet SE-Semantik-Enforcement (se_mode), Downgrade-Policy. **Aber:** Custom-Presets in In-Memory-Dict (registry.py:236/401), nicht persistiert; `approval_workflows=False` im Standard-Tier trotz Approver-Gate im Standard-Schema (Flag-Konsument unauffindbar); Doppel-Bedeutung des preset-Feldes (Tier ODER Entity-Preset-Key, transition_validator.py:53–55) sauber kommentiert, bleibt Fallstrick.

**AI-Derivation-Methodik:** Draft/Accept-Vertrag überall (mode=preview default, persistiert nichts) = korrektes Human-in-the-Loop-RE. Trace-Links richtungskorrekt und vollständig (derives-from/decomposes+derives-from/allocated-to/verifies/traces); SE-Semantik-Verstoß rollt Entity zurück („no orphaned, un-linked entity", _write_derived_entity:1105–1109). Anti-Halluzination: Artefakt-Inhalt in Prompts (REQ-046), ID-Whitelisting (553–559), Enum-Clamping (771–823), empty-decomposition-Note (#311), Prompt-Hash-Caching ohne Mock-Fallback-Caching (REQ-105), Tenant-namespaced (#122), Token-Budget + Purpose-Timeout + Audit (#115). policy=auto läuft durch echte Workflow-Transitions und stoppt an Approval-Gates — keine AI-Selbstfreigabe. **Schwächen:** Mock-Fallback in Derivation-Drafts nicht ausgewiesen (Marker gestript, Drafts ohne Flag; nur requirement_bundle surfen is_mock_fallback sauber); Decompose setzt Level-Kette nicht fort; check_consistency/validate rein informativ.

**Befunde (17):**

| # | Schwere | Ort | Titel |
|---|---|---|---|
| 1 | HOCH | persistence/models.py:188–192 + docs/se/** | L0-L4-Level-Mapping-Konflikt — ADR-Entscheid nötig (Enum re-mappen ODER ID-Schema deklarieren); decompose() soll child.level = parent.level+1 setzen; Level-Progression-Audit-Regel ergänzen |
| 2 | HOCH | docs/se/traceability-matrix.md | Zentrale Matrix ~3× veraltet, behauptet trotzdem 100 % („lückenlos" falsch); REQ-L1-034..047 fehlen, REQ-L0-031 existiert nirgends → Regeneration automatisieren, Versionsstamp gegen Drift |
| 3 | HOCH | docs/se/L0/SN_Stakeholder_Needs.md | Implementation-States grob veraltet (falsche „Not Implemented" für implementierte Features) → Bulk-Neubewertung + State-Ownership |
| 4 | MITTEL-HOCH | docs/REQUIREMENTS.md:1 | „Successfully migrated"-Kopf täuscht; 188 Kampagnen-REQs mit Solution-Creep; zwei parallele ID-Schemata ohne Abbildungsregel → Kopf korrigieren; neue REQs direkt im Tool (Dog-Fooding) |
| 5 | MITTEL | coverage_consistency.py:100/187–198 + precondition_rules.py:444 | „supersedes"-Phantom-Link-Typ: Audit-Regeln filtern eine Kantenklasse, die im Produkt nie existiert (nicht im 15er-Enum, nur Tests per ORM) → Typ offiziell aufnehmen (16., Reconciler-Regel: nur AdrService) oder Regeln auf `decides` umstellen |
| 6 | MITTEL | definition_store.py (adr_default:696, risk_default:706) + workflow/services.py:284–329 | Soft-Delete/„outdated"-Semantik zwischen Entitätstypen inkohärent → jedem Entity-Preset explizit is_outdated_equivalent-State, lifecycle_status-Spalten entfernen, outdated_item_ids() als einzige Filter-API |
| 7 | MITTEL | workspace_context_service.py:51–76 | open_requirements_count zählt implemented/verified als „offen" (status != approved) → Definition auf „nicht terminal-positiv laut Preset" ändern |
| 8 | MITTEL | ai_derivation_service.py:1980–1983 vs. bundle_compression_service.py:88–99 | Mock-Fallback inkonsistent ausgewiesen — Derivation-Drafts ohne Flag → provider/is_mock_fallback-Feld ergänzen; besser: bei echten Workspaces auf echten Provider-Fehler hart failen (REQ-078-Alternative) |
| 9 | MITTEL | AGENTS.md | Mehrere Fakt-Claims veraltet → Header-Regeneration |
| 10 | NIEDRIG | presets/registry.py:236/354–402 | Custom-Presets nicht persistiert (In-Memory-Dict; get_preset_config wirft für Custom-Namen) → persistieren oder Custom-Pfad bis v2 sperren |
| 11 | NIEDRIG | SN:98–122 vs. transition_validator.py:312–353 | L0-Gap-Beschreibung halb veraltet (Rule 6/7 prüfen Graphen inzwischen; fehlend korrekt: Top-Down-Approval-Enforcement + No-Orphan-Rule) |
| 12 | NIEDRIG | registry.py:171–181 | approval_workflows=False im Standard-Tier trotz Approver-Gate → Flag-Konsument definieren oder entfernen |
| 13 | NIEDRIG | docs/se/test_coverage_report.md | Coverage-Metrik konflatiert Needs mit Testbarkeit (alle REQ-L0 „Missing/Not Specified" — Needs per Definition nicht Unit-testbar) → Report auf L1+ beschränken |
| 14 | NIEDRIG | L2_architectural_decomposition.critic.final.md:6 | se-critic-Verdict „approved_with_fixes" außerhalb des Schema-Vokabulars (approved|rejected|blocked) |
| 15 | NIEDRIG | L2_ApplicationServiceSystem_Requirements.md:7 | „LEAF (terminal)" widerspricht existierenden L3-Component-Docs (19 L3_COMP-AS-*) — Formulierung präzisieren |
| 16 | INFO | TestRun-Domäne | Stimmig: Lifecycle in_progress→passed/failed/partial/closed (GH-403/GH-584), Execution-vs-Lifecycle-Status getrennt; nur Tool-Katalog-Text „completed/failed" nutzt nicht existierenden Status-Namen |
| 17 | INFO | REQ-155 | Functional/physical architecture separation korrekt als Proposed geführt (deklarierte Lücke, keine Doku-Lüge) |

**Offene Fragen:** (1) Level-Entscheidung (Enum vs. ID-Schema)? (2) `supersedes` als 16. Typ oder Migration auf `decides`? (3) Wer pflegt L0-States und Matrix (ohne Automatik wiederholt sich der Drift)? (4) Warum approval_workflows=False trotz Gate; wird das Flag gelesen? (5) L4-Ausnahme bei Level-Umstellung mitwandern? (6) Kampagnen-REQs bewusst außerhalb des Tools? (7) Extended-Preset produktiv im Einsatz (Level-Felder fast alle NULL; Rule 5/6/7 extended-only — ist die rechte V-Modell-Seite unverifiziert im echten Betrieb?)

### 4.6 Sicherheit & Multi-Tenancy

**Tenant-Isolation: STRONG core, RLS-Backstop mit Lücken.** Kern verifiziert: Thread-local TenantContext, Fail-fast `TenantContextNotSetError` **vor** SQL, `TenantManager.get_queryset()` als einziger Enforcement-Punkt, grep-bare `UnscopedManager`-Escape-Hatch, `SET app.current_tenant` + RESET in finally (Session-scoped, dokumentiert vs. SET LOCAL #110/#522), Teardown-Backstop mit unset→set-Nesting-Guard, Celery-Propagation exemplary (beide Layer, whitelist, nesting-safe teardown), Tenant authoritativ aus DB, nie aus Token. **Bypass-Liste:** (1) RLS fehlt auf ~20 tenant-scoped Tabellen (Liste s. P0-2); (2) workflow/lifecycle_manager.py:449 — pk-keyed UPDATE ohne Tenant-Prädikat, Tabelle ohne RLS; (3) se_metrics/aggregator.py:226–259 unscoped (gemildert durch Workspace-Ownership-Check am Mount); (4) baseline/views.py:148–157 Tenant-Fallback zu None auf AllowAny-Endpoint. Keine Raw-SQL-Injection-Bypasse (search_service.py voll parameterisiert mit `tenant_id = %s`), kein Thread-Local-Leak (finally in beiden Middlewares + Celery-Task).

**AuthN/AuthZ: STRONG.** Hand-rolled JWT-HS256-Verifier diszipliniert (constant-time, alg gepinnt, exp Pflicht, nbf/iss/aud, Refresh als Access abgelehnt — jwt_tokens.py:96–131); Login constant-time mit Dummy-Hash (keine Enumeration), Failure-Counting-Throttles (IP+username) + IP-Spray-Cap (throttling.py:146–285); API-Keys SHA-256 at rest + hmac.compare_digest + Revocation + Max-Key-Cap; RBAC method→operation, workspace-scoped Role-Resolution ignoriert JWT-Claims (#103 Escalation-Fix), Shadow-Verify fail-closed; MCP header-only (Body/Query-Keys bewusst abgelehnt); Cookies httpOnly/SameSite=Lax/path-scoped, CSRF auf allen Cookie-Authed-Unsafe-Methods inkl. Refresh; CORS-Allowlist ohne Credential-Reflection; CSP, HSTS, APPEND_SLASH=False; DEBUG production-gated (settings.py:65–68); SECRET_KEY/JWT/Fernet/DB-Password fail-fast ohne Defaults. **Unguarded (verifiziert):** public-by-design OK (login/refresh/health/schema/version/banner); Fälle: baseline scope-preview (F4), se_metrics dead views (F3), Django-Admin cross-tenant nur is_staff (F13).

**Injection/Secrets:** PDF escaped via _escape_xml (253–437); SVG _escape_xml_attr mit Regressionstests (GH-353); ReqIF-Import über lib + Size-Guards; CSV-Import _MAX_ROWS=1000 + atomarer Rollback; **CSV-Export-Formel-Injektion-GAP** (export_service.py:211 `_csv_cell` ohne Neutralisation — Bundle-Pfad neutralisiert, dieser nicht); Prompt-Injection-Surface inherent (per-Tenant-Budget limitiert); SSRF via Admin-LLM-base_url (admin-gated, URLField-validiert, API-Key Fernet) — private-CIDR-Block fehlt. Secrets: keine hardcoded, compose `${VAR}`-only, .env.example CHANGE-ME, Least-Privilege-Rolle reqogniloom_app.

**Audit-Log: GOOD.** Append-only 3-fach (ORM save/delete-Guards audit/models.py:315–337, DB-Trigger 0002, read-only-Admin); Tenant-scoped mit base_manager unscoped für Writes; api_key_hash gehasht, nie Plaintext (284–290); MCP-Writes funnel durch audit.services.log_write. Gaps: audit_entry ohne RLS (ORM-only), actor als Freitext-CharField (bewusst), CSV-Batch-Import audited 1×/Batch (per-Row-Lineage bewusst geopfert, REQ-L3-IMP-004).

**Dependency-Risiken:** Django==4.2.30 im Lock (EOL, 6 CVEs) — HIGH; cryptography==49.0.0 unter PYSEC-2026-3552-Floor — HIGH; anthropic 0.120.2 stale vs. Floor >=0.122 — LOW/MED; DRF 3.17.1, drf-spectacular 0.30.0, celery 5.6.3, psycopg2, redis, reportlab>=4 — OK.

**Befunde (21):** F1 lock/EOL (high) · F2 RLS-Lücken (high) · F3 se_metrics dead views (high) · F4 scope-preview AllowAny+tenant-None (medium) · F5 CSV-Formel-Injektion (medium) · F6 str(exc) in metrics/icd-Views (medium) · F7 Refresh ohne Reuse-Detection (medium) · F8 lifecycle_manager unscoped UPDATE (medium) · F9 LLM-base_url SSRF (medium) · F10 hand-rolled JWT (low) · F11 API-Keys bare SHA-256 ohne Pepper (low) · F12 SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE unset (low) · F13 Admin cross-tenant (low) · F14 sm_* raw tenant_id ohne TenantManager (low) · F15 csrf_exempt auf MCP ohne Cookie-Auth-Assertion (low) · F16 ~80× message=str(exc) ungeprüft (low) · F17 CSV-Kommentar-Strip vor Parsing (low) · F18 SET-Discipline-Invariante (info) · F19 Optimistic Locking opt-in (info) · F20 Import-Row-Länge nur Titel (info) · F21 Prompt-Injection-Inherent (info).

**Top-10-Quality-Hotspots:** rest_api/views.py 7.390 Zeilen (God-File, 20+ ViewSets) · ai_derivation_service.py 2.097 · llm_adapter/providers.py 2.017 · rest_api/serializers.py 1.803 · cross_cutting.py 1.646 · definition_store.py 1.503 · ~80× duplizierte str(exc)-Mapping · 2 parallele Metrics-Surfaces (dead vs. live) · password_authentication.py:91–96 doppelte Zuweisung · inkonsistenter Authz-Stil (permission_classes vs. manuelle has_role-Checks).

### 4.7 Infrastruktur

**Topology (8 Services):** postgres (pgvector:pg16, kein Host-Port, 384M, Healthcheck), postgres-backup (Sidecar, pg_dump|gzip täglich, Retention 7, kein Healthcheck), redis (7-alpine, 256M), backend (ghcr pinned 1.7.0, 8001→8000, Healthcheck /health/, 512M), migrate (One-Shot, restart:no, 512M), celery (Healthcheck inspect ping, 384M), celery-beat (pgrep-Check, 256M), frontend (pinned, 5173→8080 nginx, Healthcheck /healthz, 128M). Deploy-Ordering korrekt (service_completed_successfully). Root-Compose = Prod-Modus (ADR-08); Dev via override.yml; Varianten ghcr/minimal/test/honcho/unraid.

**Celery:** 4 Queues (default/llm/events/memory) sauber geroutet — aber **ein Worker konsumiert alle** (dokumentierter v1-Tradeoff). Beat: DatabaseScheduler; Outbox-Dispatch alle 5s (settings.py:568–573). Concurrency gepinnt auf 4 im Root-Compose (mit gemessener RSS-Begründung) — **aber nicht** in ghcr.yml:268–269 (INFRA-03-Regression). **Fehlend:** keine TASK_TIME_LIMIT/soft_time_limit (dokumentierte Env-Vars werden nie gelesen), kein acks_late/prefetch_factor/worker_max_tasks_per_child/visibility_timeout.

**Redis:** eine Instanz für Broker (db0) + Cache (db1), gemeinsames 256mb-maxmemory und Eviction-Domain; `volatile-lru` + appendonly: Queue-Messages ohne TTL → nicht evictable → OOM-Error auf Publish bei vollem Speicher, Healthcheck bleibt grün; cgroup 256M == maxmemory → AOF-Rewrite-OOM-Risiko; Passwort optional (Dev unauthentifiziert), Passwort in cmdline/Healthcheck sichtbar (`redis-cli -a`).

**Postgres:** vorbildliche Rollen-Trennung (migrate=Superuser, Runtime=Least-Privilege reqogniloom_app, RLS greift real). **Kein Pooling:** CONN_MAX_AGE unset (0) → neue Connection pro Request; keine connect_timeout/statement_timeout-Defaults (SET LOCAL nur in Ausnahmepfaden). 384M knapp für pgvector/HNSW-Spikes.

**Settings-Readiness:** Stark — DEBUG-Gate (DJANGO_ENV default production, True wird hart erzwungen auf False), Fail-Fast-Secrets, CORS/CSRF-Allowlists, env-aware Rate-Limits, JWT 1h/30d, HSTS 1y, strukturierte JSON-Logs in Prod. Gaps — Gunicorn in Prod korrekt (UvicornWorker ×4), aber kein --timeout/graceful/max-requests + kein Config-File; **Static-Files-Lücke:** collectstatic im Build, aber nichts served /static/ (kein WhiteNoise; nginx proxied nur /api/ + /mcp/) → Django-Admin/Swagger-Assets im Prod-Setup broken; SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE/SECURE_SSL_REDIRECT/SECURE_PROXY_SSL_HEADER unset; AUTH_COOKIE_SECURE default True in Prod kollidiert mit dokumentiertem HTTP-Quickstart; kein Request-ID/Correlation; keine Metrics/Tracing/Alerting; TLS ausgelagert (kein Terminator im Stack); MEDIA_ROOT fehlt trotz 100M nginx-Limit. **Verdict: Dev ready · Staging nicht existent · Prod bedingt ready** (hinter externem TLS-Proxy; Blocking-Candidates: Findings 1–4).

**CI/CD:** ci.yml (FE-ESLint, Backend-Pytest 4 Shards mit pgvector+Redis-Service-Containern, pip-audit fail gate, FE-Vitest, npm audit high, agent-templates, Hermes-Plugin) · playwright.yml (E2E 4 Shards, migrate+seed, Backend via runserver, FE via Vite, FE-Prod-Docker-Smoke, Report if:always) · docker-publish.yml (Tag v*.*.*, GHCR, SemVer+latest, Build-Args, GHA-Cache — **ohne Scan/SBOM/Signierung**) · version-drift-check.yml (Cron, opt-in) · dependabot. **Lücken:** kein Backend-Lint/Typecheck (ruff/mypy), keine Image-Scans, kein SBOM, keine Signierung, kein main-Build-Automat, keine Deploy-Automation.

**Befunde (17):** 1 keine Celery-Time-Limits (HIGH) · 2 Redis-Eviction (HIGH) · 3 Redis cgroup==maxmemory (HIGH) · 4 kein Image-Scan/SBOM/Signierung (HIGH) · 5 kein DB-Pooling/Timeouts (MED-HIGH) · 6 Admin/Swagger-Static broken (MED) · 7 kein stop_grace_period (MED) · 8 ghcr-Concurrency-Regression (MED) · 9 frontend user:root (MED) · 10 fehlende Cookie/TLS-Hardenings (MED) · 11 keine Request-IDs (MED) · 12 keine Metriken/Alerting/Tracing (MED) · 13 Backups lokal/ohne Monitoring (LOW) · 14 Redis-Passwort in cmdline (LOW) · 15 PG 384M ohne Reservation (LOW) · 16 kein Backend-Lint in CI (LOW) · 17 AGENTS.md-Doku-Drift (INFO: „Django 4.2+, 5 Services" vs. real 5.2 LTS, 8 Services).

**Stärken:** Security-Defaults, die man nicht falsch machen kann · RLS-korrekte DB-Rollen-Architektur · deterministisches Deploy-Ordering + Healthchecks inkl. pgrep-Fallback (#171) · Build-Hygiene (Multi-Stage, Non-Root, Torch-Slimming, Version-Stamping /api/v1/version/, Dummy-Secrets nur Buildzeit) · dokumentierte Betriebs-Erfahrung direkt am IaC.

### 4.8 Test-Landschaft + Ausführung

**Backend-Inventar (pytest 9.1.1 + pytest-django 4.14, PostgreSQL bewusst — RLS/ADR-03, settings_test.py):**

| App | Dateien | Tests | App | Dateien | Tests |
|---|---|---|---|---|---|
| application | 85 | 1332 | memory | 9 | 130 |
| mcp_server | 50 | 886 | persistence | 21 | 111 |
| rest_api | 88 | 838 | baseline | 4 | 106 |
| diagram | 14 | 311 | se_metrics | 8 | 98 |
| auth_tenancy | 24 | 251 | presets | 4 | 84 |
| llm_adapter | 11 | 208 | icd | 2 | 62 |
| traceability | 15 | 170 | resilience | 6 | 31 |
| workflow | 17 | 149 | audit | 2 | 31 |
| admin_ops | 13 | 141 | tests/ + reqogniloom/ + context_graph + test_runs | 14 | 71 |

**Summe: 387 Dateien, 5.010 def test_ → 5.768 gesammelte Tests** (inkl. Parametrisierung). Fixtures: 14 pro-App-conftest + Root (autouse TenantContext-Cleanup #360); nur eine Factory (persistence/tests/factories.py) — sonst manuell, kein factory_boy. Mocks: unittest.mock in 133 Dateien. REQ-Trace: 1.427 Referenzen. Coverage: konfiguriert, aber **kein fail_under, kein --cov** → nie erzwungen.

**Frontend:** vitest 4.1.10 + jsdom + Testing Library — **176 Dateien / 1.363 Tests** (292 describe); Komponenten (src/test/ ~45), Hooks, API-Wrapper (9 inkl. client.test.ts), i18n-Parity, Theme-Contrast, Design-Tokens, Sanitizer; vi.mock/spyOn in 132, fetch-Mocks in 108, kein MSW; CI-Job läuft.

**E2E:** Playwright/Chromium — **49 Specs / 274 test()** (README „111" veraltet); Flows: Auth/JWT, Editoren, Review-Workflow (REQ-144), Baselines+Diff, Diagramme (Mermaid/Canvas/Node-Graph), Traceability, Search, PDF, Metrics, Visual Regression, A11y-Followup, SE-Kaskaden (waterkettle, toothbrush), API-Completeness; workers 1, retries 2, globalTimeout 10min (CI); TESTING.md dokumentiert strukturelle Blind Spots.

**Ausführung (heute, ohne Docker-Stack):**

| # | Befehl | Ergebnis |
|---|---|---|
| 1 | backend `pytest --collect-only` | CRASH exit 120 — Host-Python: pytest-homeassistant-custom-component ↔ pyOpenSSL/cryptography inkompatibel (Host-Problem, nicht projektseitig) |
| 2 | `-p no:homeassistant --collect-only` | ✅ exit 0 — 5.768 Tests in 13s |
| 3 | `-p no:homeassistant` (Lauf) | exit 1, 80s: **3 failed, 1.998 passed, 6 skipped, 3.761 errors** (Errors = PostgreSQL nicht erreichbar, erwartbar ohne Stack) |
| 4 | frontend `npm test` | ✅ exit 0 — **176/176 Dateien, 1.363/1.363 Tests** (166s) |
| 5 | E2E | Nicht ausgeführt (Stack aus, Browser-Start ausgeschlossen) |

**Die 3 Failed (alle nicht DB-bedingt):** (1) llm_adapter/tests/test_long_running_timeout.py:49 — `LLM_SYNC_TIMEOUT=240` aus Root-.env leakt in settings_test (decouple); (2) tests/test_csrf_trusted_origins.py:24 — erwartet localhost:3000, erhält .env-CSRF-LAN-Liste — identische Ursache; (3) mcp_server/tests/test_mcp_api_key_roles.py:400 — echter Live-HTTP-Call (urlopen) ohne skipif/Marker. **6 Skips:** kompletter MCP-SSE-Transport (test_e2e_sse_transport.py) — deklarierte Capability **ohne aktive Regression**.

**Kritische Pfade getestet vs. nicht:**

| Pfad | Status |
|---|---|
| Tenant-Isolation | ✅ getestet (43 Dateien cross_tenant/TenantIsolation, autouse Cleanup) — Echtverifikation nur unter PostgreSQL (bewusst) |
| Workflow-Transitions | ✅ stark (lifecycle_manager, presets, Optimistic Locking, Signature-Seal) |
| Baseline-Immutability | ✅ 106 Tests (diff value-based, scope-preview, 8 Immutability-Referenzen) |
| MCP-Protokoll | ✅ umfassend (886) — **außer SSE-Transport (6 geskippt)** |
| MCP-SSE-Transport | ⚠️ Lücke |
| context_graph / test_runs / audit / icd | ⚠️ dünn (20/13/31/62) |
| Frontend-Komponenten | ⚠️ 269 .tsx vs. ~45 zentrale Testdateien (teils via E2E abgedeckt) |

**Befunde (9):** [HIGH] .env-Kontamination der Test-Settings · [HIGH] Live-HTTP-Integrationstest in Unit-Suite · [MED] SSE-Transport dauerhaft ungetestet · [MED] Coverage nie erzwungen (pyproject.toml:13–21) · [MED] test_e2e_*-Integrationstests ohne Klassifizierungs-Marker in App-Testdirs · [LOW] keine FE-Coverage-Konfig · [LOW] README-Testzahlen veraltet (836: „~1.400/111") · [LOW] keine einheitliche Factory-Strategie · [INFO] Host-Umgebung crasht ohne -p no:homeassistant (CI/Container nicht betroffen).

**Stärken:** Umfang + REQ-Traceability (5.768/1.427) · ehrliche, dokumentierte Suite (PostgreSQL-Entscheidung mit Begründung, TESTING.md, Skips mit Ticket-Referenz statt stillem Entfernen) · systematische Test-Isolation (Root-conftest #360, pro-Prozess-Fernet-Keys, --strict-markers, CI-Matrix 4 Shards).

---

## 5. Empfehlungs-Roadmap

### Sprint „Release-Gate" (P0)

1. Lock-Regeneration (`pip-compile`) + Lock-vs-requirements-Drift-Check in CI
2. RLS-Nachzugs-Migration für ~20 Tabellen + Lint „TenantScopedModel ohne RLS = CI-Fehler"
3. EventBus-Rework: Outbox-Row **innerhalb** der mutierenden TX, Subscriber-Fehler propagieren, Webhook-Registrierung oder Feature-Entfernung
4. MCP-Throttling (Redis-basiert, pro API-Key) + `str(exc)`-Maskierung (protocol_handler.py, metrics/icd-Views)
5. CELERY_TASK_TIME_LIMIT/SOFT_TIME_LIMIT setzen
6. Redis: Broker/Cache-Trennung oder `noeviction` für Broker, cgroup ≥ 2× maxmemory
7. settings_test gegen Root-.env härten (config()-Werte pinnen); Live-HTTP-Tests mit `@pytest.mark.integration`/skipif markieren
8. se_metrics/views.py löschen oder echte Auth wired

### Sprint „Fachlichkeit" (P1)

9. ADR „L0–L4-Mapping" + `decompose()` setzt child.level + Level-Progression-Audit-Regel
10. Traceability-Matrix + SN-States automatisiert regenerieren (skriptgenerierte Tabelle, Versionsstamp)
11. Mock-Fallback-Flag (`provider`/`is_mock_fallback`) in AI-Derivation-Drafts
12. Layer-Refactor auth_tenancy (Basis-Typen heben oder Interface extrahieren)
13. Error-Envelope-Vereinheitlichung (alle expliziten Fehler durch build_error_response)
14. Sync-Token-Budget-Approximation; LLM-Call aus @atomic_transaction heraus
15. `supersedes`-Entscheidung (16. Typ, nur AdrService, ODER Audit-Regeln auf `decides`)
16. Soft-Delete-Konvention (is_outdated_equivalent für alle Entity-Presets, lifecycle_status entfernen)

### Sprint „Betrieb & Hygiene" (P2)

17. Static-Files (WhiteNoise oder nginx-Proxy) + Cookie-Hardenings + CONN_MAX_AGE/OPTIONS-Timeouts
18. Request-ID-Middleware + Log-Propagation
19. Image-Scan (trivy/grype) + SBOM im docker-publish.yml; ruff+mypy-Job in CI
20. Coverage-Gates (backend `fail_under`, frontend coverage-Block)
21. i18n-145-Key-Backlog abbauen (#619), Baseline senken
22. data-testid-Ergänzungen (DiagramGraphEditor, PageHeader, RightSidebar, ConfirmDialog)
23. OpenAPI-Pflege (extend_schema_view auf Basis-Klassen, COMMON_ERROR_RESPONSES wired, tracelinks-Deprecation)
24. AGENTS.md/README-Regeneration (Buchhaltung aus tool_registry.py/types.py + ViewSet-Zähler)
25. ICD-MCP-Parität entscheiden (icd.*-Tool-Gruppe für Agent-Workflows?)

---

## Anhang A: Bewertungsskala

- **critical:** Ausnutzbarer Schaden auf mounted Endpoint oder Datenverlust im Normalbetrieb — nicht gefunden.
- **high:** Vor Release zu fixen (Sicherheitsrestriktion, Datenverlust-Pfad, blindes Budget, toter Kernpfad).
- **medium:** Funktional/Betrieblich relevant, zeitnah; keine akute Gefahr.
- **low:** Hygiene/Konsistenz/Performance.
- **info:** Dokumentiertes Verhalten, bewusste Trade-offs, Doku-Debt.

## Anhang B: Teil-Audit-Quellen

1. Backend Layer 0/1 — 17 Befunde, 6 ADR-Verdicts
2. Backend Layer 2 + Extensions — 14 Befunde, ADR-01-Bypass-Liste, Resilience/LLM-Assessment
3. REST + MCP — 19 Befunde, volle Endpoint-/Tool-Inventare, JSON-RPC-2.0-Compliance-Verdict
4. Frontend/UI — 13 Befunde, Auth/i18n/Token/testid/a11y-Assessments
5. Fachlichkeit — 17 Befunde, 20er-Claims-Matrix, Link-Graph-Richtungen, Workflow/Baseline/Rigor-Kohärenz
6. Sicherheit — 21 Befunde, Isolation/AuthN-Injection/Secrets/Audit/Dependencies, Top-10-Hotspots
7. Infrastruktur — 17 Befunde, Topology/Celery/Redis/Postgres/Settings/CI
8. Tests — 9 Befunde, Inventar 5.768/1.363/274, Ausführungsergebnisse, Coverage-Gaps

*Ende des Berichts. Alle Pfadangaben relativ zum Repo-Root. Stand des Codes: Arbeitsverzeichnis zum Audit-Zeitpunkt (uncommittete Änderungen inklusive).*
