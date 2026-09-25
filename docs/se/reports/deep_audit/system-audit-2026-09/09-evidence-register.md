---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: documenter
revision: e3df119e52c0cbcc18df02f708567207c0374826
branch: feat/1031-bluepencil-host-bridge
---

# Systemaudit 2026-09 — Evidenzregister

**Zweck:** Dieses Register ist die kanonische, deduplizierte Evidenzkarte der Themenberichte `01`–`07` und `10`, reconciliert durch [`docs/se/reports/deep_audit/system-audit-2026-09/11-consistency-review.md`](11-consistency-review.md). Es ist ausdrücklich **keine bloße Dateiliste**: Jede Zeile beschreibt eine Tatsache oder Hypothese, einen Primärbeleg, vorhandene Test-/CI-Evidenz, Severity, Confidence, Verifikationsplan und Status.

**Auditstand:** `e3df119e52c0cbcc18df02f708567207c0374826` auf `feat/1031-bluepencil-host-bridge`, 2026-09-24.  
**Änderungsgrenze:** nur dieses Register wurde für die Abschluss-Synthese ergänzt; keine Anwendungs-, Test-, CI- oder bestehende Auditdatei wurde geändert.  
**Wichtig:** Codezeilen sind der Zeilenstand der jeweiligen Themenberichte. Wenn ein Bericht eine ältere Revision nennt, wird die Aussage als historischer Beleg und nicht als frische HEAD-Messung geführt.

## 1. Quellen und Evidenzklassen

### 1.1 Berichtsschlüssel

| Kürzel | Bericht | Revision laut Bericht | Verwendung |
|---|---|---|---|
| R01 | [`docs/se/reports/deep_audit/system-audit-2026-09/01-architecture-and-boundaries.md`](01-architecture-and-boundaries.md) | `94a3737a...` | Architektur, RLS, Outbox, Deployment; Runtime-Anteil historisch. |
| R02 | [`docs/se/reports/deep_audit/system-audit-2026-09/02-agents-plugins-mcp.md`](02-agents-plugins-mcp.md) | nicht angegeben | MCP, Agenten, Plugins, Hermes, Bluepencil; überwiegend statisch. |
| R03 | [`docs/se/reports/deep_audit/system-audit-2026-09/03-api-ui-data-contract-drift.md`](03-api-ui-data-contract-drift.md) | `66e21f56...` | REST/MCP/UI-/ORM-Verträge; begrenzte Tests/Schema-Erzeugung. |
| R04 | [`docs/se/reports/deep_audit/system-audit-2026-09/04-workflow-state-machines-and-se.md`](04-workflow-state-machines-and-se.md) | `66e21f56...` | Workflow, Traceability, SE-Dokumente; pytest-Umgebungsfehler. |
| R05 | [`docs/se/reports/deep_audit/system-audit-2026-09/05-security-resilience-and-operations.md`](05-security-resilience-and-operations.md) | `e3df119e...` | Security, Costs, Operations, CI; keine Runtime/CVE-Läufe. |
| R06 | [`docs/se/reports/deep_audit/system-audit-2026-09/06-frontend-ux-accessibility-and-design-system.md`](06-frontend-ux-accessibility-and-design-system.md) | `66e21f56...` | Frontend/UX/A11y; fokussierte Vitest-/Lint-Evidenz, keine vollständige Browser-/AT-Matrix. |
| R07 | [`docs/se/reports/deep_audit/system-audit-2026-09/07-testing-ci-performance-and-dependencies.md`](07-testing-ci-performance-and-dependencies.md) | `e3df119e...` | Tests, CI, E2E, Performance, Backup; statisch. |
| R10 | [`docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md`](10-dependencies-supply-chain-and-release.md) | `e3df119e...` | Dependencies, Lockfiles, SBOM, Lizenzen, Release; externe Angaben `E`. |
| R11 | [`docs/se/reports/deep_audit/system-audit-2026-09/11-consistency-review.md`](11-consistency-review.md) | `e3df119e...` | Maßgebliche Deduplizierung, Severity und offene Messungen. |

### 1.2 Klassen und Status

| Klasse | Bedeutung |
|---|---|
| **S** | statische Tatsache aus Code, Migration, Manifest, Konfiguration oder Dokumentation. |
| **T** | begrenzter Testlauf oder generiertes Schema; nur der genannte Umfang gilt. |
| **R** | historische Runtime-Beobachtung; nicht automatisch auf den Prüf-HEAD übertragen. |
| **H** | aus S/R abgeleitete Hypothese über Auswirkung oder Laufzeitlast. |
| **E** | externe Registry-/Vendor-/CVE-Aussage, in dieser Synthese nicht unabhängig verifiziert. |
| **O** | offene Messung; vor einem Release-Gate auszuführen. |

Status `OFFEN` bedeutet: In den Quellberichten bestätigt, aber im Register nicht als behoben oder am HEAD verifiziert dokumentiert. `BEDINGT` bedeutet: Exposition hängt von einem expliziten Profil/Feature ab. `HISTORISCH` bedeutet: Der Bericht nennt eine Runtime-Beobachtung, nicht den aktuellen Zustand. `EVIDENZ-LÜCKE` bedeutet: Der Vertrag behauptet mehr als die vorhandene Evidenz.

### 1.3 Zählung und Deduplizierung

- Die acht Quellberichte enthalten nach `R11:20,52–56` **109 Quellbefunde**: 33 P1, 69 P2, 7 P3, 0 P0. Die frühere/initial Dateifassung von `R04` nannte in ihrer Summary acht statt neun P2; die aktuelle Quelldatei [`R04:19`](04-workflow-state-machines-and-se.md#1-management-summary) nennt bereits **neun P2**. Der frühere Hinweis bleibt ausschließlich Audit-Trail, kein aktiver Widerspruch und kein neuer Produktbefund.
- Nach Deduplizierung und Severity-Kalibrierung bleiben **47 kanonische Tracks** `CR-01` bis `CR-47`.
- Im Default-Basisszenario: 0 P0, 20 P1, 26 P2, 1 P3. `CR-25` wird bei aktivem Bluepencil-Profil zu P1; `CR-41`/`CR-42` enthalten P3-Subteile, werden aber als je ein P2-Track gezählt.
- `S`/`D`/`C` in der Quellspalte bedeuten: separater Subbefund, echtes Duplikat/gleiche Maßnahme oder Konflikt, der durch `R11` entschieden wurde.

## 2. Kanonisches Finding-/Trackregister

### 2.1 Architektur-, Application- und Datengrenzen

| ID | Quellenbefund(e) | Primärbeleg (Pfad:Zeile/Symbol) | Test-/CI-Beleg | Severity | Confidence | Tatsache / Hypothese | Verifikationsplan | Status |
|---|---|---|---|---|---|---|---|---|
| CR-01 | R01/AB-001; R07/OPS-003 | `deploy/docker-compose.override.yml:70–72`; `deploy/docker-compose.yml:251–260,330–371` | R01:641–645: historischer Restart-/Migrationsfehler; R07:378–380: Compose-v1/v2-Drift | P1 | Hoch für Config; Runtime-Anteil historisch | S+H: Backend-Entrypoint führt DDL mit App-Rolle aus; zusätzlich inkonsistente Compose-CLI. | Maskiertes `docker compose config`, frischer Stack mit pending Migration; DDL darf nur `migrate` ausführen. | OFFEN; Runtime-Anteil HISTORISCH |
| CR-02 | R01/AB-002 | `backend/context_graph/projector.py:75–109,163–185`; `backend/context_graph/admin_ops.py:45–57`; RLS-Migration `backend/context_graph/migrations/0001_initial.py:27–45,134–135` | `backend/context_graph/tests/test_rls_policies.py:66–104` prüft Policy-Metadaten, nicht `SET ROLE` ohne GUC; R01:643–645: kein grüner Lauf | P1 | Hoch für Codepfad | S+H: Settings-/Workspace-Lookup vor RLS-Arming; reale Worker-Auswirkung offen. | Zwei Tenants, App-Role ohne `app.current_tenant`, Projector über `poll_and_dispatch()`; nur korrekter Tenant darf projizieren. | OFFEN; O |
| CR-03 | R02/F-02; R03/CD-004; R05/SR-006 | `backend/auth_tenancy/models.py:153–162`; `backend/rest_api/api_key_views.py:285–365`; `frontend/src/api/api-keys.ts:15–45` | `backend/rest_api/tests/test_api_key_agent_fields.py:45–55` pinnt Legacy-Defaults; kein sicherer Neuschlüssel-Paritätstest | P1 für neue Agent-/UI-Keys; P2 für Legacy-Härtung | Hoch | S+H: fehlende Felder erben `write`/Admin, leeren Fence und `expires_at=NULL`. | REST/MCP-Key mit explizitem Scope/Fence/Expiry; Legacy-Key nur inventarisieren/rotieren, nicht still ändern. | OFFEN |
| CR-04 | R02/F-01 | `backend/mcp_server/workspace_scope.py:173–176`; `backend/application/comment_service.py:151–173`; `backend/application/models.py:233–253` | `backend/mcp_server/tests/test_mcp_workspace_scope.py:411–460` deckt Read-Tools, nicht `comment.resolve` Write-Fence | P1 | Hoch | S+H: Zielworkspace wird nicht über `comment → artifact → workspace` aufgelöst; tenantinterner Cross-Workspace-Write plausibel. | Editor nur in A, Kommentar in B: `PERMISSION_DENIED`; Editor in B: Erfolg; fenced Key bleibt sicher verweigert. | OFFEN; Negativtest offen |
| CR-05 | R03/CD-005 | `backend/mcp_server/tools/interview.py:181–202,408–427`; `backend/application/interview_service.py:1149–1169` | `backend/rest_api/tests/test_interview_views_multi.py:21–46` belegt REST-Multi; kein MCP/REST-Paritätstest | P1 | Hoch | S+H: MCP-Schema/Handler reichen `confirmed_proposal` nicht durch; Multi-Formalize scheitert kontrolliert. | MCP-Multi mit Proposal, mehreren Artefakten und `created`; fehlendes Proposal als `VALIDATION_ERROR`. | OFFEN |
| CR-06 | R02/F-04; R01/AB-006 | `backend/application/interview_service.py:448–492,900–1147,1680–1747` | R02:137–163 und R04:253: vorhandene Tests schützen Multi bzw. History, nicht Single-Race/atomaren Fehlerpfad | P1 (Race); P2 (Chat-Atomizität) | Hoch für Race; mittel für Häufigkeit | S+H: Single-Pfad ohne Initial-Lock; Chat schreibt Felder in Einzeltransaktionen. | Zwei unabhängige Requests und Fehler nach erstem Feld; genau ein Abschluss, gemeinsamer Transcript/Outbox-Stand. | OFFEN |
| CR-07 | R04/WF-004 | `backend/application/interview_service.py:1092–1129,1250–1268,1316–1349`; `backend/application/workflow_facade.py:124–155` | `backend/application/tests/test_interview_service.py:1117–1160` prüft State/History, nicht verpflichtenden Audit-/Outbox-Seam | P1 | Hoch | S+H: direkte Engine-Aufrufe und breites Exception-Catch können Audit/Event-Zustand und Erfolgsantwort entkoppeln. | Erfolg erzeugt History + AuditEntry + Outbox; Engine-Fehler liefert keinen erfolgreichen Status. | OFFEN |
| CR-08 | R04/WF-001 | `backend/workflow/services.py:273–327`; `backend/workflow/lifecycle_manager.py:295–341` | `backend/workflow/tests/test_lifecycle_manager.py:431–461` testet `expected_version` nur am Manager; kein öffentlicher Facade-Race-Test | P1 | Hoch für Codepfad; mittel für Häufigkeit | S+H: fachliche Validierung vor Lock; zweiter Request kann veraltete Kante persistieren. | Zwei DB-Verbindungen/Threads, exakt ein Erfolg und 409; History enthält nur tatsächlich akzeptierte Kante. | OFFEN |
| CR-09 | R04/WF-002 | `backend/workflow/global_definition_store.py:126–317`; `backend/rest_api/global_default_views.py:233–449` | `backend/workflow/tests/test_global_definition_store_cache_invalidation.py:43–100` prüft Cache/Propagation, nicht Orphan/Fault-Atomicity | P1 | Hoch | S+H: Global zuerst, nicht atomar; abgeleitete Live-Items werden nicht vollständig geprüft. | Item in nicht-customized Workspace, State-Delete und injizierter zweiter Propagation-Fehler; kein Orphan/Teilupdate. | OFFEN |
| CR-10 | R04/WF-003 | `backend/workflow/management/commands/provision_workflow_definitions.py:10–100`; `backend/workflow/definition_store.py:1180–1206`; `backend/workflow/migrations/0009_backfill_global_workflow_defaults.py:61–100` | Kein Repair-Test für bestehende Legacy-Zeilen; R04:207–211 dokumentiert offenen REQ-170-Vertrag | P2 | Hoch | S+H: `get_or_create()` erzeugt fehlende, repariert aber bestehende Datensätze nicht. | Vorher/Nachher-Fixture mit Legacy und vollständigem Workspace; Report muss Nicht-Reparierte ausweisen. | OFFEN |
| CR-11 | R03/CD-001 | `backend/rest_api/error_envelope.py:18–37`; `backend/rest_api/openapi.py:43–64`; `frontend/src/types/index.ts:699–709`; `frontend/src/components/shared/ArtifactForm/field-errors.ts:41–77` | `backend/rest_api/tests/test_error_envelope.py:30–38` prüft Native-ValidationError, nicht alle Error-Pfade/Frontend-Parität | P2 | Hoch | S+H: Runtime kann `details` als Objekt liefern, Schema/Frontend erwarten Array. | Native ValidationError, NotFound und `build_error_response` auf einen kanonischen Vertrag bringen. | OFFEN |
| CR-12 | R03/CD-002 | `backend/rest_api/openapi.py:68–98`; `backend/rest_api/views.py:7467–7565`; Interview-/TestRun-Action-Schemata laut R03:164–171 | `backend/rest_api/tests/test_openapi.py:19–112` prüft Serializer/Parameter, nicht die genannten Actions vollständig | P1 | Hoch | S+H: 437 Operationen, fehlende Fehler-/Action-Schemata; generierter Client kann Interview/TestRun falsch aufrufen. | Schema-Snapshot und Runtime/Schema-Paritätstest für `interviews`, `results`, `bulk`, UUID-Parameter und Fehler. | OFFEN |
| CR-13 | R03/CD-003 | `backend/persistence/models.py:719–760`; `backend/application/workspace_service.py:171–177,639–748`; `backend/rest_api/views.py:4895–4932` | `backend/rest_api/tests/test_workspace_preset_normalization.py:43–100` prüft Preset-Normalisierung, nicht AI/MCP/Memory-Sprachparität | P1 | Hoch | S+H: Service schreibt `preset.language`, AI/MCP/Memory lesen ORM-Spalte. | Create/GET/PATCH `de`, danach AI-/MCP-/Memory-Read im selben Tenant/Workspace; Altbestandsmatrix. | OFFEN |
| CR-14 | R03/CD-006 | `backend/rest_api/views.py:3024–3165`; `frontend/src/api/artifactRefs.ts:7–23`; R03:328–330 | Kein Route-/OpenAPI-Paritätstest für TraceLink-Detail-GET/PATCH oder ID-Echo | P2 | Hoch | S+H: Schema verspricht GET/PATCH, Runtime 404/405; ID-Raum bleibt UI-spezifisch. | Jede generierte Operation gegen View-Status/Schema; Requirement-/Artifact-ID und gemischte Abfrage testen. | OFFEN |
| CR-15 | R04/TR-001; R04/TR-002 | `backend/traceability/trace_link_manager.py:463–583`; `backend/application/trace_link_service.py:273–347`; `backend/link_types/catalog.py:1–171` | `backend/traceability/tests/test_services_facade.py:55–63` und Manager-Tests pinnen alte CRUD-Semantik; kein Cross-Type-/Catalog-Gate | P2 | Hoch | S+H: Update/Batch umgehen Workspace-Katalog; Single-/Batch-Zyklusvertrag uneinheitlich. | Deaktivierter Typ, `diagram-ref`, Endpoint-Paar, Tenant-Fence, Batch und Cross-Type-Zyklus. | OFFEN |
| CR-16 | R04/TR-003; R01/AB-012 | `backend/traceability/coverage_calculator.py:216–262`; `backend/traceability/vcrm_report_generator.py:65–90`; `backend/baseline/diff_engine.py:109–177` | `backend/traceability/tests/test_coverage_calculator.py:491–534` pinnt Baseline-Ablehnung; kein Failure-Injection-/Snapshotvergleich | P2 | Hoch | S+H: `baseline_id` wird akzeptiert, aber nicht als Snapshot unterstützt; DiffEngine verschluckt Store-Fehler. | Zwei Zeitstände und getrennte `OperationalError`/`BaselineNotFoundError`/Legacy-Stub-Fälle. | OFFEN |
| CR-17 | R01/AB-007; R05/SR-014 | `backend/baseline/models.py:116–187`; `backend/baseline/migrations/0006_baseline_snapshot_rls.py:20–35`; `backend/application/models.py:44–182` | `backend/persistence/tests/test_rls_coverage.py:133–162` erfasst nur `TenantScopedModel`; kein Plain-Child-/App-Role-Test | P2 | Hoch für Gap; niedrig für Leak | S+H: Plain-Modelle/Kinder ohne eigene RLS; aktuelle Service-Pre-Checks schützen bekannte öffentliche Pfade. | Zwei Tenants, direkter Kindquery unter App-Role ohne passenden Tenant-Kontext; Ergebnis muss leer/policygefiltert sein. | OFFEN |
| CR-18 | R01/AB-004; R05/SR-013 | `backend/application/event_bus.py:232–275,458–557`; `backend/application/webhook_dispatcher.py:12–15,201–301`; `backend/reqogniloom/settings.py:833–838` | Kein Test mit langsamem Endpunkt, Worker-Kill und Retry/DLQ; R01/05 liefern nur Verifikationsplan | P2 | Hoch für Mechanik; mittel für Event-Semantik | S+H: synchrone HTTP-/Backoff-Kette kann Poller/Claim/Celery-Grenzen überschreiten. | Langsame und dauerhaft fehlerhafte Subscription; Taskdauer, Claim, DLQ, Backlog und Worker-Kill messen. | OFFEN; O |
| CR-19 | R01/AB-005; R01/AB-008; R05/SR-007 | `backend/llm_adapter/url_guard.py:149–197`; `backend/memory/memory_rest.py:176–227`; `backend/application/webhook_dispatcher.py:303–338`; `backend/llm_adapter/providers.py:2037–2068` | Kein gemeinsamer E2E-Test für private/Redirect-/DNS-Wechselziele; LLM-Guard-Test deckt nicht Webhook/Memory/Honcho | P2 | Hoch für Kontrolllücke; mittel für Ausnutzbarkeit | S+H: Validierung am Settings-Schreiber statt am Ausführungs-/HTTP-Rand; Provider-SDK kann neu auflösen. | Loopback/RFC1918/Link-local/IPv4-mapped/Redirect/DNS-Wechsel für Webhook, LLM, Ollama, Honcho. | OFFEN; O |
| CR-20 | R05/SR-008 | `backend/reqogniloom/settings.py:747–753`; `backend/llm_adapter/token_tracking.py:211–243`; `backend/mcp_server/tools/cross_cutting.py:132–179`; `backend/memory/tasks.py:91–97` | Kein Test, der Viewer-`context.change_impact`, Memory- und Health-Providerkosten gegen dasselbe Budget prüft | P1 | Hoch (98/100 im Quellbericht) | S+H: Default `None`; read-only Compute und Background-/Health-Pfade umgehen zentrale Quota. | Mit gesetztem Budget read-only MCP, Memory-Task und Health-Probe; nach Limit kein Provider-Request. | OFFEN |
| CR-21 | R01/AB-010; R02/F-06; R02/F-09; R02/F-13 | `docs/agent-templates/tool-manifest.json:2–4`; `backend/mcp_server/urls.py:18–25`; `backend/mcp_server/views.py:405–431`; `README.md:1050–1073,1154–1188` | `backend/mcp_server/tests/test_tool_manifest_drift.py:83–157` und `backend/mcp_server/tests/test_server_info.py:29–47` schützen Manifest/Discovery, nicht README/Prompts/stdio-Behauptungen | P2 | Hoch für Drift; Runtime-Anteil offen | S+H: Toolzahlen/Transporte/Versionen laufen auseinander; stdio nicht als Serverroute belegt. | Generierter README-/Prompt-Snapshot; CI-Smoke `GET /mcp/`, Key, `tools/list`, read-only Call. | OFFEN; O für Runtime |
| CR-22 | R02/F-03; R02/F-08; R02/F-11 | `.agent-meta/config/plugin-catalog.yaml:273–286`; `backend/mcp_server/views.py:176–190,281–304,480–612`; `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts:52–70` | `backend/mcp_server/tests/test_server_info.py` prüft Discovery; kein Header-/Batch-/Hermes-Timeout-Kontrakttest | P2 | Hoch | S+H: dekorative Header, unterschiedliche Batchfehler und unbegrenzte TS-Requests; Header ändern keine Identität. | Beliebige `X-Workspace-ID`-Werte ändern keine Claims; Array/Timeout/Retry mit gemeinsamem Contract prüfen. | OFFEN |
| CR-23 | R02/F-10 | `.agent-meta/config/plugin-catalog.yaml:243–261`; `.agent-meta/scripts/lib/registry_query.py:177–192`; `.agent-meta/scripts/lib/mcp_provider_config.py:152–175` | `docs/agent-templates/test_role_tools_exist_in_manifest.py:81–159` prüft Rollen, nicht serverseitige/Provider-Allowlist-Erzwingung | P2 | Hoch | S+H: Blocklisten sind Prompt-Guidance; Providerkonfigurationen divergieren. | Adversarialer Prompt plus Key/Host-Allowlist; sichtbare Toolmatrix je Provider archivieren. | OFFEN |
| CR-24 | R02/F-12; R10/DEP-006 | `integrations/hermes-plugin/reqogniloom/src/hermes-sdk-types.ts:2–19`; `integrations/hermes-agent-plugin/README.md:7–23`; `integrations/hermes-plugin/reqogniloom/package.json:13–29` | `.github/workflows/ci.yml:284–319` testet nur TS; Python-Plugin-Tests sind im Workflow nicht referenziert | P2 | Hoch für Governance; Hostvertrag offen | S+H: zwei nicht live verifizierte Hermes-Verträge; E-Hauptvertrag nicht behauptet. | Supported-Surface-Matrix, beide Varianten kompilieren/testen; Host-SDK-/Install-Smoke dokumentieren. | OFFEN; E/O |
| CR-25 | R02/F-05; R10/DEP-007 | `deploy/bluepencil/README.md:1–20,178–195`; `deploy/bluepencil/server.js:1678–1746`; `frontend/src/bluepencil/loader.ts:277–305`; `frontend/public/bluepencil/latest/latest.json:2–5` | `frontend/src/test/bluepencil-loader.test.ts:225–240` prüft teilweise Fixture/Hash; kein AuthN-/Tenant- und gemeinsamer Versionstest | **bedingt P1 aktiviert / P2 default-off** | Hoch für Lücke; Exposition nicht belegt | S+H: Opt-in-QS/Sidecar ohne Tenant-Isolation; Browser alpha.2/Sidecar alpha.1 nicht integritygebunden. | Beide Flags in Shared-QS: ohne Auth 401/403, Cross-Workspace unsichtbar; gemeinsame SHA-/Protokollprüfung. | BEDINGT; O |
| CR-26 | R05/SR-001; R05/SR-005; R05/SR-018 | `backend/auth_tenancy/services/authentication.py:175–220`; `backend/auth_tenancy/rest.py:172–212`; `backend/auth_tenancy/jwt_tokens.py:9–127` | `backend/rest_api/tests/test_workspace_scoped_roles.py:152–170` schützt Workspacepfad; kein Workspaceless-Stale-Bearer-/Family-Revocation-Test | P1 für Authorization; P2/P3 für Teilthemen | Hoch; JWT-Teil ist P3-Kandidat, kein Bypass-Beweis | S+H: nichtleerer `claims.roles`-Snapshot bleibt bei Workspaceless-Pfaden maßgeblich; kein `is_active`-/Revocation-Check. | Admin deaktivieren/Rolle entziehen; alter Bearer und Refresh-Familie nach Passwortwechsel müssen scheitern. | OFFEN |
| CR-27 | R05/SR-002; R05/SR-003; R05/SR-004 | `backend/rest_api/auth_views.py:180–247`; `backend/auth_tenancy/services/user_account.py:94–113`; `backend/reqogniloom/settings.py:367–372` | Kein vollständiger Auth-Matrix-Test für Body-Token-Default, MFA und Provisioning-Passwortvalidatoren | P2 | Hoch bzw. Policy | S+H: drei getrennte Auth-Policy-Lücken; kein einzelner Bypass wird behauptet. | Browser-/CLI-Login, Admin ohne MFA, Similarity-/Common-/Numeric-/Breached-Passwörter über REST/MCP/Provisionierung. | OFFEN; Policy |
| CR-28 | R05/SR-009 | `backend/mcp_server/views.py:788–801`; `backend/mcp_server/sse_pubsub.py:13–23,74–131` | Keine Proxy-/Access-Log-Redaction- oder Header-Reconnect-Matrix; Session-TTL-/Encryption-Unitbeleg vorhanden, aber URL-Leak offen | P2 | Hoch | S+H: Session-ID ist URL-Bearer mit acht Stunden TTL; Query-String kann Logs/History erreichen. | Query-/Event-Endpoint umziehen, Logs auf `session_id` prüfen; ungültige/fremde/expired Session scheitert. | OFFEN |
| CR-29 | R05/SR-010; R05/SR-011; R05/SR-012; R02/F-07; R07/PERF-003 | `backend/mcp_server/views.py:148–156,579–612`; `backend/reqogniloom/health.py:73–225`; `backend/rest_api/views.py:7808–8079`; `backend/llm_adapter/router.py:363–438` | R07:446–447 nennt Worker-Cleanup, aber keinen Queue-/SSE-/Thread-Cap-Test; R02:582–624 fordert Lasttest | P2 | Hoch für Mechanik; O für Wirkung | S+H: Workerzahl begrenzt, Arbeit/Queue/SSE/Health/Upload/Provider-Lifecycle nicht vollständig begrenzt. | Queue voll, Redis aus, Health-Flood, 20/25/100-MiB-Upload und Provider-Thread-Stress; Backpressure/ RSS messen. | OFFEN; O/H |
| CR-30 | R07/CI-001; R07/CI-002 | `.github/workflows/ci.yml:41–55,118–153`; `backend/mcp_server/tests/test_mcp_api_key_roles.py:71–90`; `backend/mcp_server/tests/test_e2e_sse_transport.py:317–361` | CI überspringt Live-Tests; `pytest --collect-only`-/Integrationslauf laut R07:95,118 offen | P1 | Hoch | S+H: vier Testbäume mit 463 Definitionen außerhalb der Matrix; Live-HTTP/Redis nicht im PR-Gate. | Collection-Matrix-Diff; ASGI+Postgres+Redis-Integrationsjob; Testnamen und Umgebungs-Fingerprint archivieren. | OFFEN |
| CR-31 | R07/E2E-001; R07/E2E-002; R07/E2E-003 | `.github/workflows/playwright.yml:143–212`; `e2e/tests/hermes-bugfix-campaign.spec.ts:667–687`; `e2e/tests/api-completeness.spec.ts:269–287`; `e2e/package.json:4–10` | Playwright startet laut Workflow `runserver`/Vite; kein authentifizierter SSE-Roundtrip; `test:e2e:api` zielt auf fehlendes Verzeichnis | P1 für Laufzeitparität; P2 für Tooling | Hoch | S+H: WSGI/Vite statt ASGI/nginx; Core-Contract-Fehler werden als Skip sichtbar. | Uvicorn/Image/nginx gegen `runserver`/Vite vergleichen; SSE-Handshake/Frames/Message prüfen; absichtlicher Contract-Fehler muss rot werden. | OFFEN; O |
| CR-32 | R07/REL-001; R10/DEP-003 | `.github/workflows/docker-publish.yml:98–112,142–191`; `.woodpecker.yml:123–127` | Kein sichtbarer Test-vor-Image-Gate; Trivy-Scan und separater Push ohne Digest-/SBOM-/Cosign-Nachweis | P1 | Hoch | S+H: Release-Reihenfolge und Provenienz des tatsächlich gepushten Images fehlen. | Absichtlich roter Test darf kein Image publizieren; Scan-/Manifest-/SBOM-/Provenance-/Signatur-Digest gleich. | OFFEN |
| CR-33 | R07/TEST-001 | `e2e/helpers/auth.ts:80–99,241–264`; `e2e/tests/visual-regression.spec.ts:47–73`; `backend/mcp_server/tests/test_mcp_api_key_roles.py:265–275` | Kein vollständiger `afterAll`-/Finalizer-Nachweis; R07:212–233 verlangt wiederholte Läufe | P2 | Hoch | S+H: Workspaces/API-Keys bleiben persistent; lokale Zustandsabhängigkeit verzerrt E2E. | Drei Visual-Regression-Läufe auf gleicher DB; nach globalem Teardown keine Fixtures. | OFFEN |
| CR-34 | R07/COV-001; R07/TYPE-001 | `backend/pyproject.toml:28–36`; `frontend/package.json:7–15,40–60`; `frontend/tsconfig.build.json:3–8`; `e2e/package.json:4–10` | Kein Coverage-Skript/`fail_under`; Test-TS und E2E haben keinen separaten `tsc --noEmit`-Vertrag | P2 | Hoch | S+H: quantitative Coverage und Testtypprüfung fehlen; Ratchets schützen nicht jede Zeile. | Coverage-JSON/Threshold; synthetischer Testtypfehler muss `tsc --noEmit` rot machen, Produktionsbuild bleibt separat. | OFFEN |
| CR-35 | R07/PERF-001; R07/PERF-002 | `backend/se_metrics/aggregator.py:241–265`; `backend/se_metrics/cache.py:15–63`; `backend/Dockerfile:253–260` | `backend/se_metrics/tests/test_aggregator.py:7–17,161–174` mockt Quellen; `backend/se_metrics/tests/test_cache.py:154–193` testet nur Threads im selben Prozess | P2 | Hoch für Mechanik; O für Last | S/H: N+1-Querymuster und prozesslokaler Lock vs. vier Produktionsworker. | 1/100/1.000 Items mit Query-Count/Explain; vier Prozesse gegen denselben Cache-Key. | OFFEN; H/O |
| CR-36 | R07/OPS-001 | `backend/persistence/tests/test_migrations_and_indexes.py:26–30`; `.github/workflows/ci.yml:118–153` | Nur Persistence-App-Check; CI/E2E führen keinen vollständigen `makemigrations --check` aus | P2 | Hoch | S+H: Model-/Migrationsdrift in anderen Apps kann bis zum Runtime-Pfad durchrutschen. | Absichtliche Modeländerung ohne Migration; vollständiger App-Gate muss Datei/App nennen. | OFFEN |
| CR-37 | R07/OPS-002; R05/SR-015 | `deploy/docker-compose.yml:127–170`; `scripts/backup.sh:74–105`; `scripts/restore.sh:49,116,181–186`; `backend/admin_ops/services/backup_service.py:58–130` | Kein isolierter Restore-Smoke; kein verschlüsselter-At-rest-Test | P1 für Recovery-Reproduzierbarkeit; P2 für Vertraulichkeit | Hoch | S+H: Sidecar erzeugt `.sql.gz`, Restore erwartet andere Quelle/Dateiformat; gzip schützt Vertraulichkeit nicht. | Sidecar-Backup in frische DB kopieren; Integritätsfehler vor Überschreiben abbrechen; verschlüsselten Dump ohne Key nicht lesbar. | OFFEN |
| CR-38 | R10/DEP-001; R10/DEP-002; R10/DEP-004; R10/DEP-009; R05/SR-017 | `backend/requirements.txt:4–8,39–171`; `backend/requirements.lock:1–28`; `backend/Dockerfile:29–51`; `frontend/Dockerfile:4,44–53`; `.github/workflows/ci.yml:15–20,98–153` | Kein Clean-Room-Doppelbuild; `R10` führt keinen CVE-/SBOM-Lauf aus | P1 für Kontrolllücke; CVE-Aussage offen | Hoch für Drift; E für Vulnerability-Wirkung | S+E/H: Lock nicht installiert, Images/Actions/Scanner nicht digest-/SHA-/Hash-gebunden; VCS-Pin ist reproduzierbar referenziert, aber nicht releasegeprüft. | Linux/CPython/CPU-kompatibler Lock mit Hashes; zwei Builds, Image-Digest, SBOM und Scanner-Versionen vergleichen. | OFFEN; E/O |
| CR-39 | R10/DEP-005; R10/DEP-008; R10/DEP-010; R10/DEP-011; R10/DEP-012 | `backend/requirements.txt:159–171`; `backend/requirements.lock:66`; `.github/dependabot.yml:3–33`; `frontend/package-lock.json`; `integrations/hermes-plugin/reqogniloom/package-lock.json` | Keine zentrale vollständige SBOM-/Notice-/Dependabot-Matrix; Python-Lock ohne Lizenzfelder | P2; `DEP-011` P3 | Hoch für Evidenzlücke; E für Registry-Version | S/E: Tooling-/MCP-/E2E-/Lizenzabdeckung und Honcho-Versionen driften; keine CVE-Aussage ableiten. | Clean-Room-Resolver, SPDX/CycloneDX, Notice-Matrix, `npm ci`, Scanner-/OSV-Lauf und Plattform-Soll. | OFFEN; E/O |
| CR-40 | R06/FEA-001, FEA-002, FEA-003, FEA-004, FEA-005, FEA-006, FEA-007 | `frontend/src/components/NavigationShell/NavigationShell.tsx:119–128`; `frontend/src/components/SplitView/SplitView.tsx:525–823`; `frontend/src/styles/tokens.css:885–1559`; `frontend/src/components/TraceabilityView/TraceabilityView.tsx:290–662` | R06:759–766: fokussierte Vitest-/Lintläufe, 272/277 bestanden; keine Browser-/AT-Sitzung; berechnete Kontraste in R06:121–155 | P1 | Hoch statisch; O für Screenreader | S+H: sieben unabhängige zentrale Barrieren; keine formelle AA-Zertifizierung behauptet. | Chromium/Keyboard/Axe, 320/375/767/768 px/200-%-Zoom, NVDA/JAWS/VoiceOver; Trace-Degraded-State bei 503. | OFFEN; O |
| CR-41 | R06/FEA-008, FEA-009, FEA-010, FEA-011, FEA-012, FEA-013, FEA-014, FEA-015, FEA-016 | `frontend/src/components/NavigationShell/SidebarNavigation.tsx:182–307,439–495`; `frontend/src/components/shared/ArtifactForm/fields/MultiEnum.tsx:17–53`; `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx:102–175`; `frontend/src/components/TestRuns/TestRunsList.tsx:229–260` | R06:763–766: Lint 0 Fehler/290 Warnungen, gezielte Vitest-Teile; kein vollständiger Browser/Screenreader-Nachweis | P2/P3 (kanonisch P2) | Hoch bis mittel | S/H: neun Semantik-/Interaktionslücken; P3 bleibt lokale Hygiene, keine neue WCAG-Schwere ohne Nutzerfluss. | Browser-Accessibility-Tree, Tastatur, Screenreader und fokussierte Flows; `test:e2e:api`/Lint nicht als Ersatz. | OFFEN; O |
| CR-42 | R03/CD-007; R03/CD-008; R03/CD-009; R03/CD-010 | `backend/rest_api/views.py:7467–7565`; `frontend/src/types/index.ts:861–871`; `frontend/src/components/TraceabilityView/TraceabilityView.tsx:461–481`; `frontend/src/api/test-runs.ts:46–80` | R03:57–91,164–171: keine vollständige Schema-/Frontend-Parität; R06:759–766: keine vollständige Frontend-Baseline | P2; CD-010 P3 | Hoch bzw. mittel | S+H: TestRun-Shapes, CR-UI-Scope, selektive Concurrency-Guards und Enum-Typen bleiben getrennte Entscheidungen. | GET/POST/Bulk-Resultvertrag, Two-Tab-Konflikte, CR-Lifecycle und Serializer-Enums gemeinsam prüfen. | OFFEN |
| CR-43 | R07/DOC-001 | `README.md:1018–1020`; `.github/workflows/ci.yml:34–39` | Kein versioniertes `pytest --collect-only`-/Vitest-/Playwright-List-Artefakt | P3 | Hoch | S+H: historische Marketing-/CI-Zahlen sind keine Collection-Baseline. | Collection-/List-Befehle in sauberem Runner ausführen, Zählstand/Revision speichern und README-Zahlen daran binden. | OFFEN |
| CR-44 | R01/AB-009; R11/CR-44 | `deploy/docker-compose.minimal.yml:3–12,154–159`; R11:169 | Kein Capability-/Readiness-Test für Async-Degradierung im Minimalprofil | P2 | Hoch | S+H: Async-Features bleiben pending; Profil ist bewusst reduziert, Health signalisiert es nicht. | Ohne Worker Async-Feature auslösen; Status/Health muss Degradierung sichtbar machen. | OFFEN; O |
| CR-45 | R05/SR-016 | `.github/workflows/version-drift-check.yml:53–78`; `.github/workflows/docker-publish.yml:127–132` | Kein CI-Test mit Shell-Metazeichen; Actions-SHA-Prüfung ist kein Dispatch-Injection-Test | P1 | Hoch | S+H: untrusted Input/Output wird in Shell-Quelltext interpoliert; Runner-/Secret-Risiko. | `"; id; #`, Newline und Redirect-Metazeichen dürfen keinen zusätzlichen Befehl ausführen; URL-Allowlist/ENV-Indirektion. | OFFEN |
| CR-46 | R01/AB-003; R01/AB-011 | `backend/rest_api/mixins/workflow_transitions.py:100–112`; `backend/admin_ops/theme_rest.py:31–323`; `backend/audit/events.py:90–176`; `backend/application/event_bus.py:137–275` | `backend/rest_api/tests/test_architecture.py:99–181` deckt nicht alle Mixins/`admin_ops`; kein Wiring-Test für unbenutzte Publisher | P2 | Hoch | S+H: Boundary-Ratchet und zwei `DomainEventBus`-Begriffe erlauben Missverständnisse/Layering-Lücken. | Ratchet um alle Adapter/Mixins erweitern; Startup-/Importtest meldet ungenutzten Eventpfad. | OFFEN |
| CR-47 | R04/TR-004; R04/SE-001; R04/SE-002; R04/SE-003; R04/SE-004 | `backend/application/trace_link_service.py:1326–1463`; `backend/workflow/precondition_rules.py:52–60,276–610`; `docs/se/traceability-matrix.md:1–19,582–606`; `docs/se/test_coverage_report.md:7–81`; `.agent-meta/schemas/se-adr.schema.json:4–101` | `docs/se/traceability-matrix.md:657–666` warnt vor unbelegegten Markern; R04:584–619 findet keine formale Review-Ablage; Generator-/Review-Gate offen | P2 | Hoch | S+H: Suspect-Propagation, fail-open Preconditions, Taxonomie, Matrix und Teststatus widersprechen sich. | Generator-Fixture mit absichtlichem Widerspruch; `Covered` verlangt Testlauf-/`review_id`-Referenz; SE-Schema-/Taxonomie-Check ausführen. | OFFEN; Evidenzlücke |

## 3. Offene Fragen und nicht ausgeführte Checks

Die folgenden Punkte sind ausdrücklich **keine erledigten Verifikationen**:

1. **Revision:** alle P1-Codepfade auf `e3df119e...` erneut prüfen; R01–R04 nicht ungeprüft auf HEAD übertragen.
2. **Compose:** DDL-Rolle, frischer Development-Stack und Health-/Restart-Status mit maskierten Secrets archivieren.
3. **RLS:** ContextGraphProjector unter `SET ROLE reqogniloom_app` ohne `app.current_tenant`; direkter `bl_delta_index_entry`-Query mit zwei Tenants.
4. **Tenant/API-Key:** `comment.resolve` mit Workspace A/B; fenced/unfenced Keys; neuer UI-/REST-Key mit Scope/Fence/Expiry; Bestandskey-Rotation.
5. **Interview:** REST/MCP Single-/Multi-Parität, zwei parallele Formalize-Aufrufe, Fehler nach erstem Feld, History/Audit/Outbox gemeinsam.
6. **Workflow:** zwei DB-Verbindungen mit konkurrierenden Transitionen; Global-Propagation mit Fault Injection und Item in abgeleitetem Workspace.
7. **API/OpenAPI:** Schema-Snapshot für `interviews`, `test-runs/results`, `bulk`, `tracelinks`; Status-/Schema-Parität gegen Views und Frontend-Typen.
8. **Security:** stale Bearer nach Deaktivierung/Rollenzugang, Refresh-Familie, MFA, Provider-Budget, SSRF inklusive Redirect/DNS-Wechsel, Session-ID-Redaction und Action-Metazeichen.
9. **Runtime/Load:** echter Uvicorn/ASGI-/nginx-SSE-Roundtrip mit Key; Queue-/Thread-/SSE-Caps; Health-Flood; Upload-Grenzen; langsame Webhooks und Worker-Kill.
10. **Frontend:** `npm run lint`, fokussierte Vitest-Suite, Chromium/Keyboard/Axe, manuelle NVDA-/JAWS-/VoiceOver-Matrix, 200-%-Reflow und alle realen Theme-Kontraste.
11. **CI/Test:** `pytest --collect-only`, vollständiger App-Migrationscheck, Test-/E2E-TypeScript, Coverage-Baseline und Absichtstest für Skip-/Release-Gates.
12. **Supply Chain:** Clean-Room-Python-/Node-Auflösung, fest gepinnte Scanner, SBOM/Provenance, Image-Digest, Scan-/Push-Gleichheit und isolierter Backup-Restore. Externe CVE-/Vendor-Aussagen erst danach als verifiziert markieren.

## 4. Widersprüche und offene Reconciliation-Entscheidungen

| Widerspruch | Quellen | Aktuelle Auflösung |
|---|---|---|
| R04-Zählhinweis aus der früheren/initial Dateifassung (Audit-Trail). | Aktuelle Quelldatei R04:19,94–105,199–608; frühere/initial Formulierung über R11 | Aktueller Stand: 9 P2; die frühere Angabe ist nur Audit-Trail, kein aktiver Widerspruch und kein neuer Befund. |
| `R01` beobachtet Restart-Stack, `R06` keinen laufenden Stack. | R01:22,55,641–645; R06:759–766 | Zeit-/Revisionskonflikt; aktueller Status `O`. |
| Toolzahlen 218/35 vs. 215/31 vs. 188/31 vs. 20/40. | R01:454–488; R02:15–18,680–686; R03:47; R11:95 | Manifest ist aktueller Anker; andere Dokumente sind Driftquellen (`CR-21`). |
| Trace-Link-Typen 6/8 vs. 11. | R04:292–345,647–648; Code/Katalog in R11:96 | Aktueller Code/Katalog ist Implementierungsquelle; normative Dokumente können stale sein. |
| API-Key P1 vs. P2. | R02:349–394; R03:238–276; R05:344–386 | Neue fail-open Agent-/UI-Keys P1; Bestandskey-Härtung P2 (`CR-03`). |
| Bounded MCP Pool vs. unbounded Queue. | R07:28,446; R02:582–612; R05:528–567 | Nur Workerzahl bounded; Arbeit/Queue nicht (`CR-29`). |
| Bluepencil P1 vs. Default-off/QS-only. | R02:488–529; R05:915–916; R10:175–186 | Aktiviert bedingt P1, Default P2; getrennte Security-/Provenienz-Subbefunde (`CR-25`). |
| Minimal-Compose P2 vs. bewusstes Profil. | R01:417–452; R05:915–916 | Capability-/Readiness-Lücke, kein stiller Produktionsfehler (`CR-44`). |
| Outbox „robust“ vs. Webhook-Blockade. | R01:18,232–267; R05:651–690 | Outbox-INSERT und externe Zustellung sind getrennte Verträge; beide Aussagen gelten (`CR-18`). |
| Externe CVE-/Registry-Aussagen. | R10:21–29,35–43,214–225 | Nur `E`; keine CVE- oder Dependency-Änderung aus dieser Prüfung ableiten. |

## 5. Test-, Runtime- und Auditgrenzen

- **Nicht einheitlicher HEAD-Lauf:** R03/R06 haben begrenzte Teilergebnisse, R04 scheiterte an Umgebungsinitialisierung, R01 hat historische Runtime-Beobachtung, R02/R05/R07/R10 sind statisch. Kein grüner Gesamtbaseline-Nachweis existiert.
- **Keine CVE-Aussage:** R10:29,269–279 und R11:24,49–50 markieren externe CVE-/Registry-Daten als nicht live verifiziert. `0 bestätigte verwundbare Pakete` bedeutet nicht `0 Schwachstellen`.
- **Keine Screenreader-Zusage:** R06:759–766 nennt keine laufenden Browser-/NVDA-/JAWS-/VoiceOver-Tests; berechnete Kontraste sind statische Rechenwerte.
- **Keine Performance-Zusage:** `PERF-001`/`PERF-003` sind Hypothesen; Query-Count-, Thread-, Load- und Reflow-Messungen fehlen.
- **Keine Produktionsaussage:** Historische Compose-/Restart- und Release-Berichte sind Kontext, kein aktueller Betriebsnachweis.
- **Keine Änderung an Requirements:** Dieses Register dokumentiert Befunde und Verifikationspläne; es ändert oder erfindet keine REQ-IDs und schreibt nicht in `docs/REQUIREMENTS.md`.

## 6. Pflege- und Abschlussregel

Ein Track wird erst `VERIFIZIERT`, wenn der jeweilige Plan ein ausführbares Test-/CI-Artefakt, Commit/Revision, Umgebung, Ergebnis und gegebenenfalls Abweichung enthält. Ein historischer Report, ein bestehender Unit-Test oder eine unabhängige Reviewer-Aussage ersetzt diese Evidenz nicht. Bei neuem Codefund muss der Track entweder einem bestehenden `CR` zugeordnet oder mit einer neuen ID, vollständiger Primärquelle und Reconciliation-Entscheidung ergänzt werden.

## 7. W0-Slice-Nachweis (2026-09-25, uncommitted)

Dieses Addendum dokumentiert ausschließlich die tatsächlich ausgeführten Prüfungen des bounded W0/W1-Slices. Historische Revision, Branch und Frontmatter oben bleiben unverändert; die Slice-Arbeit ist absichtlich uncommitted.

> **W1-Statusannotation (2026-09-25, datiert):** Der vorstehende Satz zur *uncommitted* Slice-Arbeit war zum Zeitpunkt der W0-Ausführung korrekt und beschreibt den damaligen Working Tree. Er ist seit 2026-09-25 **aufgehoben**: Die Slice-Arbeit wurde committet und gemergt. Die vollständige Auflösung mit Commit-/PR-Provenienz steht in [Abschnitt 7.4](#74-auflösung-der-provenienz-2026-09-25); die Close-out-Evidenz des Nachfolgeslices folgt in [Abschnitt 8](#8-w1-close-out-nachweis-2026-09-25). Der historische Wortlaut oben bleibt bewusst unverändert stehen.

| Feld | Festgehaltener Stand |
|---|---|
| Ziel-HEAD | `37b4343c5b74536451bba08625cd43e0095ed22b` |
| Branch | `feat/audit-w0-w1-security` |
| Working Tree | 19 tracked geänderte Slice-Pfade + 1 untracked Slice-Test; zusätzlich 1 untracked, leeres Nicht-Slice-Artefakt `backend/.github/workflows/version-drift-check.yml`; kein Commit erstellt **[W1-Anmerkung 2026-09-25: dieser Working-Tree-Stand ist der Vor-Commit-Zustand; die Zeile beschreibt den Slice vor Commit `82f13395`, siehe 7.4]** |
| Host/Runner | Windows NT 10.0.26200.0; finale DB-/Workflow-Läufe im Compose-Projekt `reqlo-audit-w0-w1-security-test` (`backend-test`, Python 3.12.14, pytest 9.1.1) |
| Python | 3.14.7 unter Windows; 3.14.4 im WSL-Test-Runner; finaler Container-Lauf Python 3.12.14 |
| Frontend-Laufzeit | Node 26.7.0 / npm 11.19.0; Frontend nicht betroffen, daher nicht ausgeführt |
| PostgreSQL/Redis/Image | `reqlo-audit-w0-w1-security-test-postgres-1` und `-redis-1` healthy; finaler DB-Lauf via `backend-test`; kein App-Image-Run behauptet |

### 7.0 Pfadinventar (uncommitted)

> **W1-Anmerkung (2026-09-25, datiert):** „uncommitted" in dieser Überschrift ist der historische W0-Wortlaut für den Zustand *vor* Commit `82f13395`. Das Inventar selbst (19 tracked geänderte Slice-Pfade + 2 untracked Pfade, davon 1 Nicht-Slice-Artefakt) bleibt gültige Audit-Record-Information und wird nicht angetastet; die Provenienz-Auflösung steht in [7.4](#74-auflösung-der-provenienz-2026-09-25).

**19 tracked geänderte Slice-Pfade:**
- `.github/workflows/version-drift-check.yml`
- `backend/application/comment_service.py`
- `backend/application/tests/test_comment_service.py`
- `backend/application/workspace_lookup.py`
- `backend/auth_tenancy/rest.py`
- `backend/auth_tenancy/services/authentication.py`
- `backend/auth_tenancy/tests/test_api_key_agent_identity.py`
- `backend/auth_tenancy/tests/test_authentication.py`
- `backend/mcp_server/tests/test_comment_tool_group.py`
- `backend/mcp_server/tests/test_mcp_workspace_scope.py`
- `backend/mcp_server/tools/comment.py`
- `backend/mcp_server/workspace_scope.py`
- `backend/rest_api/api_key_views.py`
- `backend/rest_api/tests/test_agent_self_approval_913.py`
- `backend/rest_api/tests/test_api_key_agent_fields.py`
- `backend/rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py`
- `backend/rest_api/tests/test_trace_link_proposal_rest.py`
- `backend/rest_api/tests/test_workspace_scoped_roles.py`
- `docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`

**2 untracked Pfade:**
- `backend/rest_api/tests/test_version_drift_workflow_security.py` — untracked Slice-Test, nicht gestaged.
- `backend/.github/workflows/version-drift-check.yml` — untracked, leeres Nicht-Slice-Artefakt, nicht gestaged, nicht verändert und nicht Teil des Slices.

### 7.1 Preliminary-Prüfungen (vor dem finalen Stack-Lauf)

Die Preliminary-pytest-Kommandos wurden mit `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` und `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test` ausgeführt; die `manage.py`-Kommandos mit `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test`. Die finalen DB- und Workflow-Läufe verwenden den Compose-Test-Runner aus Abschnitt 7.2.

| Kommando | Ergebnis |
|---|---|
| `python manage.py check` | PASS, 0 Systemcheck-Fehler |
| `python manage.py makemigrations --check --dry-run` | Exit 0, `No changes detected`; Warnung: Host `postgres` nicht auflösbar, daher keine DB-Verbindungsprüfung |
| `python -m pytest -p pytest_django.plugin --collect-only -q rest_api/tests/test_api_key_agent_fields.py rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py application/tests/test_comment_service.py mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_workspace_scoped_roles.py rest_api/tests/test_version_drift_workflow_security.py` | 135 Tests gesammelt |
| `python -m pytest -p pytest_django.plugin -q rest_api/tests/test_version_drift_workflow_security.py` | 22 passed |
| `python -m pytest -p pytest_django.plugin -q rest_api/tests/test_api_key_agent_fields.py -k "validation_precedes_lifecycle"` | 7 passed, 10 nicht ausgeführt |
| `python -m pytest -p pytest_django.plugin -q rest_api/tests/test_version_drift_workflow_security.py rest_api/tests/test_api_key_agent_fields.py mcp_server/tests/test_comment_tool_group.py -k "valid_https_url or invalid_deployed_url or secret_ or dispatch_input or empty_configuration or validation_precedes_lifecycle or maps or exactly or delete"` | 32 passed, 16 nicht ausgeführt |
| `python -m pytest -p pytest_django.plugin -q auth_tenancy/tests/test_api_key_granular_scopes_865.py -k "scope_tier or normalize or missing_scope or non_string or unknown_scope"` | 21 passed, 19 nicht ausgeführt |
| `python -m pytest -p pytest_django.plugin -q mcp_server/tests/test_mcp_workspace_scope.py -k "every_read_tool_is_classified or classification_sets_are_disjoint or tool_enforced_scope_tools_are_real_read_tools or registry_targets_reference_known_tools or registry_targets_reference_declared_params or every_entity_key_is_declared or tenant_scoped_read_tools_are_real_read_tools"` | 7 passed, 22 nicht ausgeführt |
| **PRELIMINARY** `python -m pytest -p pytest_django.plugin --tb=no -q rest_api/tests/test_api_key_agent_fields.py rest_api/tests/test_version_drift_workflow_security.py rest_api/tests/test_workspace_scoped_roles.py rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py application/tests/test_comment_service.py mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py` | 135 gesammelt, 40 passed, 95 Errors; **blockiert**, alle DB-Setup-Fehler: `could not translate host name "postgres"`; keine DB-Assertions verifiziert |
| `ruff check . --select=F821,F822` | PASS |
| `ruff check --select=I,F,E auth_tenancy/services/authentication.py auth_tenancy/rest.py rest_api/api_key_views.py application/comment_service.py application/workspace_lookup.py mcp_server/workspace_scope.py mcp_server/tools/comment.py rest_api/tests/test_version_drift_workflow_security.py rest_api/tests/test_api_key_agent_fields.py rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py application/tests/test_comment_service.py auth_tenancy/tests/test_api_key_agent_identity.py auth_tenancy/tests/test_authentication.py mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_agent_self_approval_913.py rest_api/tests/test_trace_link_proposal_rest.py rest_api/tests/test_workspace_scoped_roles.py` | PASS |
| `python -m compileall -q auth_tenancy/services/authentication.py auth_tenancy/rest.py rest_api/api_key_views.py application/comment_service.py application/workspace_lookup.py mcp_server/workspace_scope.py mcp_server/tools/comment.py rest_api/tests/test_version_drift_workflow_security.py rest_api/tests/test_api_key_agent_fields.py rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py application/tests/test_comment_service.py auth_tenancy/tests/test_api_key_agent_identity.py auth_tenancy/tests/test_authentication.py mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_agent_self_approval_913.py rest_api/tests/test_trace_link_proposal_rest.py rest_api/tests/test_workspace_scoped_roles.py` | PASS |
| `git diff --check` plus untracked-file check | PASS |
| `scan_for_secrets` diff-only (Added Lines plus untracked Slice-Datei) | PASS, keine Findings |

Der Diff-Scan wurde ausschließlich auf Added Lines (`git diff --unified=0`) plus die untracked Testdatei angewendet; unveränderte Kontextzeilen mit bestehenden Test-Platzhaltern wurden nicht als Slice-Secret-Finding gewertet.

### 7.2 Finale Verifikation nach Remediation

Finaler DB-Runner: Compose-Projekt `reqlo-audit-w0-w1-security-test`, `--project-directory .`, `backend-test`, `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test`, PostgreSQL-Service `postgres`, Redis-Service `redis`, pytest 9.1.1/Django 6.1.1/Python 3.12.14.

**Neue Negativtests zuerst:**

```powershell
docker compose -p reqlo-audit-w0-w1-security-test --project-directory . -f deploy/docker-compose.yml -f testing/docker-compose.test.yml run --rm backend-test pytest -q --create-db rest_api/tests/test_api_key_agent_fields.py rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_workspace_scoped_roles.py -k "principal_type_is_validated_before_lifecycle or validation_precedes_lifecycle or principal_type_variants_are_rejected or api_key_agent_lifecycle_rejects_incomplete_security_fields or api_key_user_explicit_null_scope_is_rejected or resolve_rejects_workspace_id_before_service or fenced_agent_key_rejects_workspace_b_before_comment_handler or explicit_workspace_cannot_bypass_fenced_comment_target or fenced_agent_key_cannot_resolve_same_tenant_workspace_b_comment"
```

Ergebnis: **29 passed, 79 deselected**, 39.21 s.

**Fokussierte finale DB-Suite:**

```powershell
docker compose -p reqlo-audit-w0-w1-security-test --project-directory . -f deploy/docker-compose.yml -f testing/docker-compose.test.yml run --rm backend-test pytest -q --create-db auth_tenancy/tests/test_api_key_agent_identity.py auth_tenancy/tests/test_api_key_granular_scopes_865.py auth_tenancy/tests/test_authentication.py rest_api/tests/test_agent_self_approval_913.py rest_api/tests/test_api_key_agent_fields.py rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py rest_api/tests/test_trace_link_proposal_rest.py rest_api/tests/test_bearer_token_role_resolution.py rest_api/tests/test_workspace_scoped_roles.py application/tests/test_comment_service.py mcp_server/tests/test_comment_tool_group.py mcp_server/tests/test_mcp_workspace_scope.py
```

Ergebnis: **224 passed**, 56 Warnungen, 54.13 s. Die Suite erfasst importierte Testfälle mehrfach; alle 224 Läufe waren erfolgreich.

**Separater Workflow-Test mit korrektem Root-Workflow-Mount:**

```powershell
docker compose -p reqlo-audit-w0-w1-security-test --project-directory . -f deploy/docker-compose.yml -f testing/docker-compose.test.yml run --rm -v "${PWD}/.github:/repo/.github:ro" -e REQLO_REPO_ROOT=/repo backend-test pytest -q rest_api/tests/test_version_drift_workflow_security.py
```

Ergebnis: **29 passed**; der Test las `.github/workflows/version-drift-check.yml` aus dem Root-Mount `/repo/.github`.

**Fehlerhafte Vorversuche und Korrekturen:** Der erste Workflow-Aufruf ohne `--project-directory .` scheiterte beim Container-Start mit `ImportError: No module named 'reqogniloom'`; der korrigierte Root-Mount-Lauf ist der oben dokumentierte grüne Lauf. Der erste neue Negativtest-Lauf ergab 28 passed/1 failed, weil der REST-Vertrag für diesen Fall `403`/`"403"` statt `PERMISSION_DENIED` liefert; die Test-Erwartung wurde an den bestehenden Vertrag angepasst, danach liefen 29/29 Tests grün.

**Finale statische und Umgebungs-Checks:**

| Kommando | Ergebnis |
|---|---|
| `docker compose -p reqlo-audit-w0-w1-security-test --project-directory . -f deploy/docker-compose.yml -f testing/docker-compose.test.yml run --rm backend-test sh -c "python manage.py check && python manage.py makemigrations --check --dry-run"` | PASS; Systemcheck 0 Fehler; `No changes detected` |
| `ruff check . --select=F821,F822` | PASS |
| `ruff check --select=I,F,E ...` über alle Slice-Pythonpfade | PASS |
| `python -m compileall -q ...` über alle Slice-Pythonpfade | PASS |
| `git diff --check` plus untracked-file check | PASS |
| Scope-/Status-Check mit `git status --porcelain=v1 -uall` | PASS: 19 tracked Slice-Pfade + 1 untracked Slice-Test; das untracked leere `backend/.github/workflows/version-drift-check.yml` wurde separat als Nicht-Slice-Artefakt bestätigt |
| Diff-only `scan_for_secrets` über Added Lines plus untracked Slice-Datei | PASS, keine Findings; keine Secret-Inhalte ausgegeben |

### 7.3 Abweichungen und offene W0-/W1-Evidenz

- **PRELIMINARY/BLOCKIERT:** Der frühere 135/40+95-Lauf bleibt als Vorlauf dokumentiert; der finale DB-Lauf in Abschnitt 7.2 ist grün.
- **ACTIONLINT-ERGEBNIS ROT (Stand dieses Addendums; W1-Stand: GESCHLOSSEN — siehe [8.2](#82-actionlint-gate-w0-schlussung)): `actionlint` ist auf dem Host weiterhin nicht nativ installiert, wurde jetzt aber real über das digest-gepinnte Image `rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667` ausgeführt (Digest per `docker pull` + `docker image inspect` aufgelöst, Version via `actionlint -version` = 1.7.12). Kommando: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12@sha256:b193... -color`. Echter Exit-Code **1**. Befund (einziger, unverändert offen **[W0-Stand — zum Zeitpunkt dieses Laufs zutreffend; der Befund wurde am 2026-09-25 behoben, siehe 8.2]**): `.github/workflows/docker-publish.yml:66:9` — `SC2129:style` (drei aufeinanderfolgende `>> "$GITHUB_OUTPUT"`-Redirects). `ci.yml`, `version-drift-check.yml`, `playwright.yml` und `pages.yml` sind sauber (Exit 0); die actionlint-eigenen Checks sind mit `-shellcheck=` grün.
  - **W0-Entscheidung (historischer Wortlaut, ausdrücklich überholt):** Der Befund ist ein `style`-, kein Korrektheitsfehler und liegt außerhalb des W1-Slices, daher bewusst **nicht** behoben und **nicht** per `-ignore` wegkonfiguriert.
  - **W1-Korrektur (2026-09-25, datiert):** Die vorstehende W0-Entscheidung ist widerrufen. Der Befund wurde im W1-Close-out-Slice **behoben** — nicht per Ausnahme, sondern auf der Sache: Die drei aufeinanderfolgenden `>> "$GITHUB_OUTPUT"`-Redirects wurden zu einer einzigen `{ … } >> "$GITHUB_OUTPUT"`-Gruppe zusammengefasst. Die Ausgabeäquivalenz wurde empirisch unter GNU bash 5.2 nachgewiesen (byte-identisch, 110 Bytes, 3 newline-terminierte Records, übereinstimmendes sha256 `02d3d10dc64edc7667b6ad56a92af5afe3e426caee1472e1dd05191446859bb5`). Der vollständige Re-Run liefert Exit-Code **0** ohne Ausgabe; `docker-publish.yml` isoliert ebenfalls Exit 0. Eine Negativkontrolle auf einer Scratch-Kopie außerhalb des Repos reproduzierte den ursprünglichen Exit-1-Befund und belegt damit ein echtes Negativ statt eines übersprungenen Checkers. Es wurde **kein** `-ignore` und **kein** `shellcheck: ""` ergänzt. Damit gilt das W0-Actionlint-Gate seit 2026-09-25 als **GESCHLOSSEN**; Belege in [8.2](#82-actionlint-gate-w0-schlussung).
- **NICHT AUSGEFÜHRT:** Frontend-Tests und Typecheck, da keine Frontend-Datei betroffen ist; Release-/Image-Nachweis und vollständige W0-Exit-Kriterien wurden nicht behauptet.
- **Lint-Abweichung:** der optionale Default-Ruff-Lauf über die Slice-Dateien meldete 37 Bestands-/Regelbefunde außerhalb des CI-Pyflakes-Gates; der im CI konfigurierte `F821,F822`-Lauf ist grün.

Status dieses Addendums: **TEILWEISE VERIFIZIERT / ACTIONLINT-GATE ROT (1 `style`-Befund) / RELEASE-GATE OFFEN**. Der actionlint-Lauf ist real ausgeführt und der Befund offen dokumentiert; der neue CI-Job `workflow-lint` in `.github/workflows/ci.yml` führt dasselbe gepinnte Image aus und ist deshalb **noch rot**, bis der SC2129-Befund entschieden ist (Fix oder explizite Akzeptanz) — das Gate wurde nicht abgeschwächt. Der W0-Slice ist nur für die in Abschnitt 7.2 tatsächlich ausgeführten DB- und Workflow-Prüfungen freigegeben; historische Provenienz und der frühere preliminary DB-Fehlerlauf bleiben unverändert dokumentiert.

> **W1-Korrektur der Statuszeile (2026-09-25, datiert):** Der vorstehende Absatz ist der **W0-Abschlussstatus** und bleibt als historischer Wortlaut unverändert stehen. Zwei Aussagen darin sind seit 2026-09-25 nicht mehr wahr und werden hiermit korrigiert, ohne den Wortlaut zu überschreiben:
> 1. **`ACTIONLINT-GATE ROT` → GESCHLOSSEN.** Der einzige Befund (`SC2129:style`, `.github/workflows/docker-publish.yml:66`) wurde behoben, nicht wegkonfiguriert; der Re-Run ist Exit 0. Siehe [7.3](#73-abweichungen-und-offene-w0-w1-evidenz) und [8.2](#82-actionlint-gate-w0-schlussung).
> 2. **`workflow-lint` ist nicht mehr „noch rot".** Mit dem Fix liefert der Job dasselbe grüne Ergebnis wie der lokale Lauf; es wurde weder `-ignore` noch `shellcheck: ""` ergänzt. Der Job ist bislang jedoch **nicht auf einem echten CI-Runner gelaufen** — Evidenz ist ausschließlich der lokale gepinnte Container-Lauf (Restrisiko, siehe [8.6](#86-verbleibendes-restrisiko-bewusst-offen-geführt)).
>
> **RELEASE-GATE bleibt OFFEN.** Die Statusüberschrift dieses Addendums gilt nur für den W0-Slice; der Gesamt-W1-Abschluss mit allen nicht abgearbeiteten Punkten steht in [Abschnitt 8](#8-w1-close-out-nachweis-2026-09-25).

### 7.4 Auflösung der Provenienz (2026-09-25)

Dieser Abschnitt ist ein **datierter W1-Nachtrag** zu [7](#7-w0-slice-nachweis-2026-09-25-uncommitted). Er verändert keine Evidenzzeile der Abschnitte 7.0–7.3, sondern hebt deren Provenienzstatus auf und verweist auf den Nachfolgeslice.

**Betroffene historische Aussagen (unverändert erhalten, hiermit aufgehoben):**

| Ort im Dokument | Historischer Wortlaut (W0) | Status seit 2026-09-25 |
|---|---|---|
| Überschrift von §7 | `## 7. W0-Slice-Nachweis (2026-09-25, uncommitted)` — der Klammerzusatz `uncommitted` ist der historische W0-Wortlaut | aufgehoben; die Slice-Arbeit ist committet und gemergt |
| Einleitungssatz von §7 | „die Slice-Arbeit ist absichtlich uncommitted" | aufgehoben (W1-Statusannotation dort belassen) |
| Tabelle „Working Tree" in §7 | „kein Commit erstellt" | aufgehoben; beschreibt den Vor-Commit-Zustand |
| Überschrift 7.0 | `### 7.0 Pfadinventar (uncommitted)` | aufgehoben; das Inventar selbst (19 tracked geänderte Slice-Pfade + 2 untracked Pfade) bleibt gültige Record-Information |

**Tatsächliche Commit-/PR-Provenienz (verifiziert):**

| Feld | Festgehaltener Stand |
|---|---|
| Slice-Commit | `82f1339595485e4706702bff5ebe8a5760d22be4` — „fix: harden W0/W1 security boundaries" |
| Merge-Commit | `59bcb7a91e17b13cfedd1476073a2d1b6e8d040d` — „Merge pull request #1070 from Popoboxxo/feat/audit-w0-w1-security" |
| Ziel-Branch | `origin/main` |
| Nachweis der Zugehörigkeit | `git merge-base --is-ancestor 82f13395 origin/main` → **true** (Exit 0) |
| Slice-Branch (Quelle) | `feat/audit-w0-w1-security` |
| Parent des Slice-Commits | `37b4343c5b74536451bba08625cd43e0095ed22b` — identisch mit der Zeile „Ziel-HEAD" in §7 |

**Was aus dieser Auflösung folgt und was ausdrücklich nicht folgt:**

- Der Slice ist **nicht mehr uncommitted.** `git show --stat 82f13395` umfasst genau 20 Dateien: die 19 tracked Slice-Pfade aus 7.0 **plus** den zuvor untracked Slice-Test `backend/rest_api/tests/test_version_drift_workflow_security.py` (174 Zeilen), der damit versioniert ist. Das in 7.0 genannte Nicht-Slice-Artefakt `backend/.github/workflows/version-drift-check.yml` ist **nicht** Teil des Commits — die Trennung aus 7.0 ist also bestätigt.
- Die Evidenz der Abschnitte 7.0–7.3 bleibt gültig: Sie beschreibt die Prüfungen, die auf dem W0-Working Tree **vor** dem Commit ausgeführt wurden. Der PRELIMINARY/BLOCKIERT-Lauf (135 gesammelt / 40 passed / 95 Errors, `could not translate host name "postgres"`) und die dokumentierten Fehlversuche (fehlender `--project-directory`, 28/1 beim ersten Negativtest) werden **nicht** entfernt und **nicht** umformuliert — sie sind Audit-Trail-Wert.
- Kein Rückschluss auf `main` vor dem Merge: `e3df119e52c0cbcc18df02f708567207c0374826` im Frontmatter oben bleibt die Provenienz des **Audits vom 2026-09-24** und wird von dieser Nachtragsarbeit nicht angetastet.
- **Weiterverweis:** Die Close-out-Arbeit des Nachfolgeslices `feat/audit-w1-closeout` (Basis `origin/main` = `59bcb7a9`, enthaltend PR #1070 / `82f13395`) ist in [Abschnitt 8](#8-w1-close-out-nachweis-2026-09-25) dokumentiert. Sie ist zum Zeitpunkt dieses Nachtrags noch nicht committet.

### 7.5 Weiterführung der Provenienz-Auflösung (2026-09-25, PR #1071)

Dieser Abschnitt ist ein **zweiter datierter Nachtrag** zu [7.4](#74-auflösung-der-provenienz-2026-09-25). Er hebt die letzte in 7.4 verbliebene offene Provenienzaussage auf und verändert keine Evidenzzeile der Abschnitte 7.0–7.4.

**Die in 7.4 offene Aussage (unverändert erhalten, hiermit aufgehoben):** der letzte Bullet von 7.4 — „Sie ist zum Zeitpunkt dieses Nachtrags noch nicht committet." Das war der Stand des ersten Nachtrags und ist seit 2026-09-25 überholt.

**Vollständige Provenienzkette (Stand 2026-09-25):**

| Stufe | Feld | Festgehaltener Stand |
|---|---|---|
| W0/W1-Slice | Commit | `82f1339595485e4706702bff5ebe8a5760d22be4` — „fix: harden W0/W1 security boundaries" |
| W0/W1-Slice | PR / Merge | PR **#1070**, gemergt als `59bcb7a91e17b13cfedd1476073a2d1b6e8d040d` — „Merge pull request #1070 from Popoboxxo/feat/audit-w0-w1-security" |
| W1-Close-out | Commit | `f85407f7b9684426dec989ade265d1bc4eb70217` — „fix: close W1 security audit gaps" |
| W1-Close-out | PR | **#1071** — dort und nur dort sind die **ursprünglichen** Zahlen aus [8.3](#83-ausgeführte-kommandos-und-ergebnisse) und [8.4](#84-was-je-audit-track-tatsächlich-geschlossen-wurde) entstanden |
| Review-Runde zu PR #1071 | Commit | **noch nicht committet** — zum Zeitpunkt dieses Eintrags existiert dafür bewusst **keine** SHA; siehe die commit-gebundene Fortschreibung in [8.0](#80-revision-branch-und-commitbindung) |
| Review-Runde zu PR #1071 | Branch | `feat/audit-w1-closeout` (auf `f85407f7b9684426dec989ade265d1bc4eb70217`) |

**Was daraus folgt:**

- **Der Close-out ist committet.** Die gesamte Evidence-Produktion der Abschnitte 8.1–8.6 ist damit reproduzierbar an `f85407f7` gebunden und nicht mehr an einen flüchtigen Working Tree.
- **Der committete-slice-Teil bleibt unberührt.** `82f13395`/PR #1070 und `59bcb7a9` sind unverändert die in 7.4 verifizierte Provenienz; dieser Nachtrag fügt eine Stufe hinzu und überschreibt keine.
- **Die Überarbeitung ist streng additiv.** Die Zahlen der ursprünglichen Close-out-Runde in 8.3 bleiben als historischer Messstand stehen. Wo die Review-Runde zu **anderen** Werten kommt, stehen die neuen Werte datiert in [8.7](#87-review-follow-up-zu-pr-1071-2026-09-25) und benennen die superseded Größe ausdrücklich.
- **Kein Rückschluss.** `e3df119e52c0cbcc18df02f708567207c0374826` im Frontmatter oben bleibt die Provenienz des **Audits vom 2026-09-24**; die Commits dieser Kette sind Nachtrags-Arbeit und ändern daran nichts.

## 8. W1-Close-out-Nachweis (2026-09-25)

Dieser Abschnitt ist ein **eigenständiger, datierter W1-Close-out-Record**. Er ist nicht Teil des Audits vom 2026-09-24 und ändert die Abschnitte 1–7 nicht; insbesondere bleiben die Track-Status der Abschnitte 2, die Widerspruchstabelle in 4 und die Abschlussregel in 6 unverändert stehen. Statusänderungen gegenüber Abschnitt 2 werden ausschließlich hier als datierte W1-Annotation geführt.

> **Lesehinweis:** Der Statusblock am Dateiende ist der historische Abschlussvermerk des Audits vom 2026-09-24 und beschreibt die 47 kanonischen Tracks der Abschnitte 1–6. Er wird hier weder ergänzt noch umformuliert; der W1-Abschlussstatus steht ausschließlich in den Abschnitten 8.4–8.6.

### 8.0 Revision, Branch und Commitbindung

| Feld | Festgehaltener Stand |
|---|---|
| Basis | `origin/main` = `59bcb7a91e17b13cfedd1476073a2d1b6e8d040d` (Merge von PR #1070, enthält `82f13395`) |
| Arbeitsbranch | `feat/audit-w1-closeout`, von `origin/main` bei `59bcb7a9` abgezweigt |
| Commitbindung des Close-outs | `f85407f7b9684426dec989ade265d1bc4eb70217` — „fix: close W1 security audit gaps", PR **#1071**. Dies ist der Commit, in dem die Zahlen der Abschnitte 8.1–8.6 entstanden sind. **[Datierte Fortschreibung 2026-09-25: diese Zele lautete ursprünglich „noch nicht committet … die gesamte W1-Close-out-Arbeit liegt uncommitted im Working Tree. Es wird bewusst keine SHA für den Close-out genannt." Das ist seit dem Commit überholt und wird hier nicht mehr behauptet; die Auflösung der W0-Provenienz steht in 7.4/7.5.]** |
| Commitbindung der Review-Runde | **noch nicht committet** — die in [8.7](#87-review-follow-up-zu-pr-1071-2026-09-25) dokumentierte Review-Runde liegt zum Zeitpunkt dieses Eintrags **uncommitted auf dem Branch `feat/audit-w1-closeout`, auf `f85407f7` aufsetzend.** Dafür wird bewusst **keine** SHA genannt: sie existiert noch nicht. |
| Bindung der Ergebnisse | §8.1–8.6: an Commit `f85407f7` (PR #1071) + die nachfolgend aufgeführten 13 Pfade. §8.7: an `f85407f7` + die in 8.7 genannten 5 geänderten Pfade, **noch uncommitted**. |
| Nachweis des Working Trees | `git status --porcelain=v1 -uall` |

**Working-Tree-Inventar des Close-outs (4 geändert, 9 neu):**

- geändert: `.github/workflows/ci.yml`, `.github/workflows/docker-publish.yml`, `backend/persistence/tests/test_rls_coverage.py`, `docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`
- neu: `backend/auth_tenancy/management/commands/inventory_api_keys.py`, `backend/auth_tenancy/tests/test_inventory_api_keys_command.py`, `backend/baseline/migrations/0010_baseline_delta_index_entry_rls.py`, `backend/context_graph/tests/test_projector_rls_tenant_arm.py`, `backend/mcp_server/tests/test_mcp_workspace_id_header_decorative.py`, `backend/mcp_server/tests/test_mcp_workspaceless_revocation.py`, `backend/persistence/tests/test_rls_plain_child_models.py`, `backend/rest_api/tests/test_workspace_id_header_decorative.py`, `docs/api-key-inventory.md`

### 8.1 Verifizierte Umgebung

| Feld | Festgehaltener Stand |
|---|---|
| Host | Windows NT 10.0.26200.0 |
| Host-Python | 3.14.7 **[datierte Korrektur 2026-09-25: diese Zele wurde in der ursprünglichen Close-out-Runde als `3.13.14` notiert. Das ist sachlich falsch — der Host ist 3.14.7. Die earlier notierte Angabe ist hiermit superseded und bleibt nur als Audit-Trail sichtbar. Das für das Gate maßgebliche Runtime bleibt der Container in der Zeile „Test-Runner" (Python 3.12.14); die falsche Host-Angabe hat die Gate-Aussage nicht getragen, da kein pytest-Lauf auf dem Host stattfand.]** |
| Host-ruff | 0.16.9 — **Abweichung:** CI pinnt `ruff==0.16.5` (`.github/workflows/ci.yml`). Der lokale `I,F,E`-Lauf ist damit eine **Superset-Prüfung**, keine byte-identische CI-Reproduktion. |
| Docker / Compose | Docker 29.8.0, Docker Compose v5.5.1, Compose-Projekt `reqlo-audit-w1-test` |
| Test-Runner | Service `backend-test`, `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test`, Container-Python 3.12.14 |
| Datenbank | **echtes PostgreSQL**; Serverstring `PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc`; `ENGINE=django.db.backends.postgresql`; 68 live RLS-Policies in `pg_policies`; 97 Tabellen in `information_schema` **[datierte Anmerkung 2026-09-25: die Policy-Zahl dieser Zeile stammt aus der ursprünglichen Close-out-Runde. Die Review-Runde zu PR #1071 misst `pg_policies` = **67**. Beide Werte werden hier unglättiert nebeneinander geführt; dieses Register erklärt die Differenz von einer Policy **nicht** und leitet daraus ausdrücklich keinen Befund ab. Beide Messungen stehen gegen dasselbe PostgreSQL 16.15.]** |
| actionlint | 1.7.12, digest-gepinnt auf `rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667` |

**Kein SQLite-Fallback — ausdrücklich festgehalten:** `backend/reqogniloom/settings_test.py:67` setzt `ENGINE` fest auf `django.db.backends.postgresql`; es existiert **keine** SQLite-Verzweigung. In diesem Slice ist **kein** SQLite-Fallback aufgetreten. Die grünen Tests fragen `pg_policies` und `information_schema` ab und setzen `SET ROLE reqogniloom_app` mit der GUC `app.current_tenant` — ein Verhalten, das auf SQLite prinzipiell nicht reproduzierbar wäre und daher die RLS-Aussagen in 8.4 trägt.

### 8.2 Actionlint-Gate (W0-Schlussung)

**Ausführung (unverändert digest-gepinnt):** `actionlint` wurde real über den Container ausgeführt, nicht nur strukturell substituiert. Der Digest wurde mit `docker pull` + `docker image inspect` aufgelöst, die Version mit `actionlint -version` als 1.7.12 bestätigt.

```text
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667 -color
```

**Befund und Behebung auf der Sache:** Der einzige Befund des W0-Laufs, `SC2129:style` in `.github/workflows/docker-publish.yml:66` (drei aufeinanderfolgende `>> "$GITHUB_OUTPUT"`-Redirects), wurde **behoben**, indem die drei Redirects zu einer einzigen `{ … } >> "$GITHUB_OUTPUT"`-Gruppe zusammengefasst wurden (nachweisbar in `.github/workflows/docker-publish.yml:90–94`).

**Äquivalenznachweis (empirisch, GNU bash 5.2):** Die Ausgabe vor und nach dem Fix ist byte-identisch — 110 Bytes, 3 newline-terminierte Records, übereinstimmendes sha256 `02d3d10dc64edc7667b6ad56a92af5afe3e426caee1472e1dd05191446859bb5`.

**Ergebnis nach dem Fix:**

| Kommando | Exit-Code | Ausgabe |
|---|---|---|
| Vollständiger Lauf (alle Workflows) | **0** | keine |
| `docker run --rm -v "$PWD:/repo" -w /repo <gepinntes Image> -color .github/workflows/docker-publish.yml` | **0** | keine |

**Negativkontrolle:** Eine Scratch-Kopie **außerhalb** des Repos reproduzierte den ursprünglichen Exit-1-Befund. Das grüne Ergebnis ist damit ein echtes Negativ und nicht das eines übersprungenen Checkers.

**Keine Abschwächung:** Es wurde **kein** `-ignore` und **kein** `shellcheck: ""` irgendwo ergänzt.

**CI-Gate:** In `.github/workflows/ci.yml` wurde der Job `workflow-lint` („Workflow Lint (actionlint)") ergänzt, der dasselbe gepinnte Image mit demselben Digest gegen dieselbe Workflow-Liste ausführt. Lokal und CI sind damit deckungsgleich **in der Konfiguration**; ein realer CI-Lauf steht aus (siehe [8.6](#86-verbleibendes-restrisiko-bewusst-offen-geführt)).

**Gate-Status: W0-Actionlint-Gate GESCHLOSSEN (2026-09-25).**

### 8.3 Ausgeführte Kommandos und Ergebnisse

Alle Angaben sind **echte Exit-Codes** der ausgeführten Läufe, keine Sollwerte.

| Lauf | Ergebnis | Exit |
|---|---|---|
| Fokussierte Suite (7 Module) | **108 passed**, 0 failed, 0 deselected, 0 skipped | **0** |
| Regressionsset (18 Pfade: W0-Slice + RLS-Nachbarn) | **494 passed** | **0** |
| Zwei reale RLS-Nachbarmodule, separat | **20 passed** | **0** |
| `ruff check . --select=F821,F822` | keine Findings | **0** |
| `ruff check --select=I,F,E` über die 9 geänderten/neuen Python-Dateien | keine Findings | **0** |
| `python -m compileall -q` | keine Findings | **0** |
| `python manage.py check` | „System check identified no issues (0 silenced)" | **0** |
| `python manage.py makemigrations --check --dry-run` | „No changes detected" | **0** |
| `git diff --check` | keine Findings | **0** |
| Trailing-Whitespace-/Tab-/Final-Newline-Scan über die untracked Dateien | 0 Findings | **0** |
| Diff-only Secret-Scan | **0 Findings** | nicht berichtet |
| actionlint Voll-Lauf | grün | **0** |
| actionlint `docker-publish.yml` isoliert | grün | **0** |
| Nach-Aufräum-Re-Verifikation, vier berührte Testmodule | **83/83** | **0** |
| Nach-Aufräum-Re-Verifikation, sieben fokussierte Module | **108/108** | **0** |

**Offen gelegte Fehl- und Korrekturversuche (nicht verdeckt):**

- **Erster abgebrochener Regressionslauf: Exit 4** (Usage-Fehler). Der Lauf wurde abgebrochen und auf die real existierenden Pfade korrigiert.
- **Pfadkorrektur:** Der ursprünglich beauftragte Pfad `backend/persistence/tests/test_rls_policies.py` **existiert in diesem Repository nicht** (bestätigt über `git ls-files backend/persistence/tests/`). Der Lauf wurde auf die 18 real existierenden Pfade korrigiert; die zwei realen RLS-Nachbarmodule wurden **zusätzlich separat** mit 20 passed / Exit 0 gefahren.
- **Ruff-Drift:** Der `I,F,E`-Lauf stand zunächst bei **Exit 1 mit 5 Findings** — 2× `I001`, 1× `F541`, 2× `E501`. Alle fünf lagen in den **neuen** Dateien dieses Slices, **keines** in vorbestehendem Code; nach Korrektur Exit 0.
- **Migrations-Drift:** Die handgeschriebene RunSQL-Migration `backend/baseline/migrations/0010_baseline_delta_index_entry_rls.py` ist **kein** Model-Drift — `makemigrations --check --dry-run` meldet „No changes detected".
- **Secret-Scan — Erstbefunde und ihre Auflösung:** Der diff-only Scan meldete zunächst **2 Findings** in neuen Test-Fixtures: ein `Bearer`-Literal und eine generische `secret`-Zuweisung. Beide wurden aufgelöst, indem die Platzhalterwerte durch die **dokumentierte `_SAFE_PATTERNS`-Allowlist des Scanners selbst** geleitet wurden — nach dem bereits committeten Präzedenzfall in `backend/rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py:53`. Das Scanner-Muster matcht **weiterhin**; nur die Allowlist hebt den Befund auf. Der Wert wurde also **nicht** obfuskiert, um die Erkennung zu umgehen. Endstand: **0 Findings**.
- **Ruff-Versionsabweichung:** lokal 0.16.9, CI-gepinnt 0.16.5 — die lokale `I,F,E`-Aussage ist eine Superset-Prüfung, siehe [8.6](#86-verbleibendes-restrisiko-bewusst-offen-geführt).

### 8.4 Was je Audit-Track tatsächlich geschlossen wurde

Die Statuszellen der Tracks in [Abschnitt 2](#2-kanonisches-finding-trackregister) bleiben unverändert; die folgenden Angaben sind datierte W1-Annotationen.

#### CR-02 — GESCHLOSSEN

Neuer Test `backend/context_graph/tests/test_projector_rls_tenant_arm.py`, **6/6 grün gegen echtes PostgreSQL**. Mit `SET ROLE reqogniloom_app` und bewusst **nicht** gesetzter GUC `app.current_tenant` schreibt das reale `ContextGraphProjector.poll_and_dispatch()` für **keinen** von zwei Tenants eine einzige `ContextEdge`-Zeile. Die Variante mit warmem Settings-Cache erzwingt die Ausführung **hinter** das Settings-Gate bis in den `Workspace.unscoped`-SELECT, der für sich allein fail-closed ist. Ein fremder Tenant projiziert nichts. Erst das Arming des richtigen Tenants lässt den Projector laufen.

**Kein Produktionsdefekt gefunden; keine Codeänderung nötig.** Der Track gilt damit als auf HEAD-nahem Stand verifiziert — mit der in [8.1](#81-verifizierte-umgebung) dokumentierten Einschränkung, dass der Nachweis auf dem Arbeits Tree dieses Slices und nicht auf einem CI-Runner entstand.

#### CR-17 — TEILGESCHLOSSEN, Restrisiko OFFEN

**`bl_delta_index_entry` ist geschlossen (fail-closed).** `backend/baseline/migrations/0010_baseline_delta_index_entry_rls.py` ergänzt `ENABLE ROW LEVEL SECURITY` und `FORCE ROW LEVEL SECURITY` mit einer Policy, die über den Elternbezug `baseline_id → baseline.tenant_id` schlüsselt. Ein unbewaffneter Read der App-Rolle liefert 0 Zeilen, ein foreign-tenant `INSERT` wird abgelehnt — 2 grüne Tests.

**Die vier Tabellen `as_domain_event_outbox`, `as_domain_event_dlq`, `as_webhook_subscription`, `as_webhook_delivery_log` bleiben OFFEN.** Jede lieferte im 2-Tenants-Seed der nicht-Superuser-App-Rolle bei nicht gesetzter `app.current_tenant` je 2 Zeilen zurück. Die Ursache ist **strukturell**: reine `models.Model`-Klassen, geschlüsselt über eine nackte `workspace_id`-UUID, ohne `tenant_id`-Spalte und ohne FK, der eine erreichen könnte. Eine GUC-basierte Policy ist damit nicht bloß nicht implementiert, sondern **nicht ausdrückbar**.

**Umgang des Tests:** Die vier Tabellen sind in `RLS_EXEMPT_TABLES` (`backend/persistence/tests/test_rls_coverage.py`) mit je einer Begründung deklariert, die den tenant-kontextfreien Produktionspfad, die WITH CHECK- und die USING-Fehlerart sowie die erforderliche Korrektur benennt. Maschinelle Zusicherungen: (a) jede Begründung ist nichttrivial und nennt `app.current_tenant`; (b) `information_schema` bestätigt fehlende `tenant_id`-Spalte und fehlenden FK darauf — der Test **fällt also an dem Tag, an dem eine `tenant_id`-Spalte auftaucht**, und erzwingt die Neuaussinandersetzung; (c) ein AST-Scan belegt, dass für die Webhook-Tabellen kein REST-/Serializer-/MCP-Reader existiert.

**Kompensationsmaßnahmen sind Service-/Codepfad-Ebene, KEINE Datenbankgarantie:** `DlqService.list_dlq` und `DlqService.replay_dlq_event` (`backend/application/dlq_service.py:75,129`) lösen `workspace_id` über das tenant-gefilterte `Workspace.objects` auf, **bevor** sie die Zeile berühren. Die Django-Admin-Changelists exponieren jedoch alle Tenants' Zeilen einem Staff-Superuser und bleiben ein **menschlich erreichbarer Cross-Tenant-Pfad**.

**Erforderliche Korrektur (NICHT ausgeführt, Architekturänderung):** `tenant_id` bereits bei der Emission auf die Outbox-Payload stempeln — genau die Form, die `memory.projector` bereits verwendet.

#### CR-03 — Legacy-Inventar geliefert; kein Schlüssel rotiert

Neuer, **read-only** Management-Command `manage.py inventory_api_keys` (`backend/auth_tenancy/management/commands/inventory_api_keys.py`; App `auth_tenancy`, die das `ApiKey`-Modell besitzt). Er berichtet je Schlüssel: stabile nicht-geheime ID, Owner-Benutzer + Tenant, `last_used_at`, Scope, Principal-Typ, Workspace-Fence, Ablauf (mit Unterscheidung „kein Ablauf gesetzt" vs. „abgelaufen"), abgeleiteter Status sowie eine Flag-Spalte je Vertragsregel.

**Datierte Rotationsregel** als einzelne benannte Konstante `CR-03-LEGACY-API-KEY-ROTATION/2026-09-25` mit Wirksamkeitsdatum 2026-09-25 — damit kann ein archivierter Report nie unter einer neueren Regel gelesen werden. Formate: `text`/`json`/`csv`, `--output`, `--tenant-id`. Es existiert **kein** `--fix`/`--apply`/`--rotate`/`--write`/`--revoke`.

**Read-only ist vierfach unabhängig abgesichert:** Zeilen-Tupel vor/nach einschließlich `modified_at`/`version`; `CaptureQueriesContext` ohne INSERT/UPDATE/DELETE; Patchen der schlüssel-schreibenden Services mit Assert-not-called; Write-Flags lösen `CommandError` aus. Der Secret-Hash erscheint in **keinem** Format — bewiesen durch Scannen jedes 8-Zeichen-Fensters, mit Positivkontrolle, dass der Leak-Detektor tatsächlich auslöst. Auf **keinen** Schlüssel wird ein Capability-Verdikt (`invalid`/`broken`/`insecure`/`compromised`/`usab`) gestempelt. Der Row-Digest vor und nach einem echten Lauf war identisch (`7c8336bb2f26cf49c9602a169e98194c6b9c3481671a6f8602bdf6fd4b18c9fc`) und belegt echtes Read-only-Verhalten. 39 neue Tests, zusätzlich 413 grüne Regressionstests in `auth_tenancy/tests/`.

> **Ausdrücklich festgehalten:** **Es wurde kein Schlüssel gelöscht, still verändert oder als nicht agent-fähig abgestempelt — das Inventar tut absichtlich nichts dergleichen.** Ein Kandidat erfordert eine Rotation über den bestehenden Key-Management-Pfad. Dokumentation: `docs/api-key-inventory.md`.

#### CR-22 — nur die `X-Workspace-ID`-Sub-Assertion geschlossen; der Track ist NICHT geschlossen

Neue Tests `backend/rest_api/tests/test_workspace_id_header_decorative.py` (20 Tests) und `backend/mcp_server/tests/test_mcp_workspace_id_header_decorative.py` (14 Tests) prüfen feldweise `AuthContext`-Identitätsgleichheit mit und ohne Header, Whole-Response-Gleichheit sowie alle vier geforderten Header-Wertvarianten (Cross-Tenant-UUID, Same-Tenant-ohne-Rolle-UUID, Nicht-UUID, leer).

Der Header wird im gesamten Backend **nicht gelesen** — **null Produktionscode-Treffer**; jeder Treffer liegt in einem Test. **[Datenkorrektur 2026-09-25: der hier ersetzte Wortlaut lautete „(ein repo-weiter Treffer, in einem Test)". Die Trefferzahl dieser Klammer war falsch und ist hiermit superseded; sie bleibt nur als Audit-Trail lesbar. Neu gemessen und verifiziert: `git grep -i -c -e "X-Workspace-ID" -- backend/` → 2 Dateien / 9 Zeilen, davon `backend/mcp_server/tests/test_mcp_workspace_id_header_decorative.py` 5 und `backend/rest_api/tests/test_workspace_id_header_decorative.py` 4. `git grep -i -c -e "HTTP_X_WORKSPACE" -- backend/` (erfasst als Präfix auch `HTTP_X_WORKSPACE_ID`) → 3 Dateien / 13 Zeilen, davon dieselbe MCP-Datei 6, dieselbe REST-Datei 6 und `backend/rest_api/tests/test_workspace_scoped_roles.py` 1. Vereinigungsmenge beider Formen: **3 Dateien, 22 treffende Zeilen, 0 Dateien außerhalb von `*/tests/`.** Die Reviewer-Angabe „two test hits" entspricht der Dateizahl der gestrichelten Form (2), nicht einer Zeilenzahl; die Zeilenzahlen oben sind die belegten.]** Die load-bearing Aussage ist damit **präzise und verifizierbar**: Es gibt **null** Lesevorgänge des Headers in der Backend-Implementierung, und **jeder** repo-weite Treffer ist ein Test. REST löst die Zielworkspace ausschließlich aus URL-kwargs, dem Query-Parameter `workspace_id` oder dem JSON-Body auf (`backend/auth_tenancy/workspace_scope.py`; einziges Gate in `backend/auth_tenancy/rest.py:180`), MCP verwirft ihn bereits am Transport und leitet nur `X-API-Key`/`Authorization` weiter.

**WEITER OFFEN auf derselben CR-22-Zeile:** der Batch-Fehlervertrag und der Hermes-TypeScript-Timeout-/Retry-Vertrag bleiben untestiert.

##### Geschwister-Header `X-Project-ID` und `X-User-ID` — NICHT eigenständig getestet (Ergänzung 2026-09-25)

**Ausdrücklich als Lücke festgehalten, nicht als sicher und nicht als unsicher.** Die CR-22-Arbeit hat ausschließlich `X-Workspace-ID` bewiesen. Für die beiden gleichartigen Header derselben Klasse gilt das **nicht**:

| Header | Konfiguriert in | Test, der Identitätsgleichheit mit/ohne Header beweist | Test, der „wird nicht gelesen" beweist |
|---|---|---|---|
| `X-Workspace-ID` | `.agent-meta/config/plugin-catalog.yaml:280` | **ja** — `test_workspace_id_header_decorative.py`, `test_mcp_workspace_id_header_decorative.py` | **ja** (implizit, über die 0-Produktionscode-Treffer in [8.4](#84-was-je-audit-track-tatsächlich-geschlossen-wurde)) |
| `X-Project-ID` | `.agent-meta/config/plugin-catalog.yaml:278` | **nein** | **nein** |
| `X-User-ID` | `.agent-meta/config/plugin-catalog.yaml:279` | **nein** | **nein** |

- **Kein Test belegt, dass sie die Identität nicht ändern.** Es existiert kein Äquivalent zu `test_workspace_id_header_decorative.py` für diese beiden Header — also kein Feld-für-Feld-`AuthContext`-Vergleich, kein Whole-Response-Vergleich, keine der vier Header-Wertvarianten.
- **Kein dedizierter Test belegt, dass sie nicht gelesen werden.** Für `X-Workspace-ID` ist dieser zweite Nachweis nur ein Nebenprodukt der Test-Inventur; für `X-Project-ID`/`X-User-ID` existiert er nicht.
- **Statische Beobachtung, ausdrücklich kein Testersatz:** `git grep -i -n -E "X-Project-ID|X-User-ID|HTTP_X_PROJECT|HTTP_X_USER" -- backend/` liefert **null Treffer** in `backend/`. Ein Negativ-Grep über einen Baum ist ein Hinweis, **kein** Verhaltensnachweis: er belegt weder, dass zur Laufzeit nichts gelesen wird, noch dass ein künftiger Pfad es nicht tut.
- **Die Codepfad-Begründung überträgt sich nicht automatisch.** Das Argument für `X-Workspace-ID` war pfadspezifisch: REST löst die Zielworkspace aus URL-kwargs/`workspace_id`/JSON-Body, MCP verwirft den Header am Transport. Für `X-Project-ID` und `X-User-ID` wurde **kein** entsprechender Codepfad analysiert — weder ob ein Auflösungspfad existiert, der sie stillschweigend konsumiert, noch ob einer existieren *könnte*. Eine Verallgemeinerung „gleiche Klasse, also gleiches Verhalten" wäre eine Hypothese, keine Feststellung, und wird hier **nicht** erhoben.
- **Konsequenz:** Das Schließen dieser Lücke ist **offene Arbeit** und in [8.6.1](#861-priorisierte-nacharbeiten-aus-der-review-runde-zu-pr-1071-2026-09-25) als eigenständiger Folgepunkt priorisiert. Diese Ergänzung ändert den Track-Status von CR-22 **nicht**: er bleibt wie in [8.4](#84-was-je-audit-track-tatsächlich-geschlossen-wurde) und [8.5](#85-w1-exit-kriterien-nur-tatsächlich-verifiziert-grün) **NICHT geschlossen**.

#### CR-26 — zur Hälfte geschlossen; eine Hälfte muss offen bleiben

Neuer Test `backend/mcp_server/tests/test_mcp_workspaceless_revocation.py` (10 Tests) deckt den MCP-Workpaceless-Fallback `ToolRegistry._resolve_global_roles` (`backend/mcp_server/tool_registry.py:1393`) ab, den die W0-Tests verfehlten, weil diese sämtlich über `comment.resolve` liefen und damit einen Zielworkspace auflösten. Die Fälle **suspendierter Principal**, **gelöschter Principal** und **deaktivierter Principal** werden alle mit `PERMISSION_DENIED`/`AUTH_FAILED` abgewiesen, **ohne** dass der Handler je erreicht wird; auch der Fail-soft-`except → ()`-Zweig ist abgesichert.

**Nicht-Vakuizität** wurde über eine Wegwerf-Mutationsprobe bewiesen: `_resolve_global_roles` auf eine veraltete Rolle zu neutralisieren ließ den widerrufenen Write **gelingen** und den Handler erreichbar. **Gemessene Blast Radius:** 21 von 218 registrierten Tools sind WRITE-Tools **ohne** `workspace_id`-Parameter und ohne Target-Eintrag — dieser Branch ist also kein Randfall. Der REST-Workpaceless-Stale-Bearer-Pfad war bereits durch W0 abgedeckt.

**WEITER OFFEN:** Es existiert **kein Passwort-Änderungs-Endpunkt** (`backend/rest_api/auth_views.py` nutzt `UserProfileSerializer`, dessen schreibbare Felder `first_name`/`last_name` sind und dessen geschützte Felder `password` einschließen — der Endpoint gibt also **by design** 400 zurück) und **keinerlei serverseitigen Revocation-Hook** (null Treffer für `authz_version`/`password_changed_at`/`tokens_valid_after`; `validate_bearer_token` ist ein zustandsloser Decode ohne DB-Konsult; Refresh-Familien-Revocation existiert nur für `reuse_detected` und `logout`). Das ist eine **fehlende Funktion**, keine Testabdeckungslücke. Die kleinste schließende Form ist in [8.6](#86-verbleibendes-restrisiko-bewusst-offen-geführt) benannt; bewusst **nicht** gebaut, weil es Architekturarbeit außerhalb dieses Scopes ist.

#### Staleness-Markierung der Track-Zeilen CR-22 und CR-26

Die älteren Texte in diesen beiden Tabellenzeilen sind **relativ zu HEAD stale**, ohne dass die Zellen hier stillschweigend umgeschrieben werden:

| Track | Historischer Zellentext in Abschnitt 2 | Warum stale |
|---|---|---|
| CR-26 | `kein Workspaceless-Stale-Bearer-/Family-Revocation-Test` | Der Workspaceless-Stale-Bearer-Test wurde durch `82f13395` (PR #1070) und der Revocation-Branch erneut durch diesen W1-Slice (`test_mcp_workspaceless_revocation.py`) ergänzt. **Nur** der Family-Revocation-Teil dieser Zelle bleibt zutreffend offen. |
| CR-22 | `kein Header-/Batch-/Hermes-Timeout-Kontrakttest` | Der Header-Teil wurde in diesem W1-Slice ergänzt (`test_workspace_id_header_decorative.py`, `test_mcp_workspace_id_header_decorative.py`). **Nur** der Batch-/Hermes-Timeout-Teil dieser Zelle bleibt zutreffend offen. |

Die Formulierung `Deckt Read-Tools, nicht comment.resolve Write-Fence` steht nicht auf CR-22 oder CR-26, sondern auf der **CR-04**-Zeile in [Abschnitt 2](#2-kanonisches-finding-trackregister); sie wird hier nur der genauen Zuordnung wegen genannt und nicht bewertet. Die Track-Statuszellen selbst bleiben unangetastet.

### 8.5 W1-Exit-Kriterien (nur tatsächlich verifiziert grün)

**GRÜN — ausschließlich diese Punkte:**

1. CR-02-Exit-Evidenz gegen echtes PostgreSQL (6/6, fail-closed ohne GUC).
2. CR-17-Schließung für `bl_delta_index_entry` (fail-closed per `ENABLE`+`FORCE` RLS mit Eltern-Policy).
3. Read-only-Legacy-API-Key-Inventar mit datierter Rotationsregel `CR-03-LEGACY-API-KEY-ROTATION/2026-09-25`.
4. Gepinnte actionlint-Ausführung mit reproduzierbarem CI-Gate (`workflow-lint`) — **Konfiguration** grün, kein realer CI-Lauf.
5. CR-22-Sub-Assertion `X-Workspace-ID`-Identität (REST 20 + MCP 14 Tests).
6. CR-26-MCP-Branch `_resolve_global_roles` (10 Tests, Nicht-Vakuizität per Mutationsprobe).
7. Das vollständige lokale Verifikationsgate aus [8.3](#83-ausgeführte-kommandos-und-ergebnisse) inklusive Secret-Scan 0 Findings.

**NICHT als erfüllt beansprucht:** alle übrigen Punkte des W1-Plans. Insbesondere gilt der jeweilige Track-Status in [Abschnitt 2](#2-kanonisches-finding-trackregister) für CR-17 (Resthälfte), CR-22 (Batch-/Hermes-Verträge) und CR-26 (Revocation nach Passwortwechsel) **unverändert fort**.

### 8.6 Verbleibendes Restrisiko (bewusst offen geführt)

Jeder Punkt unten ist **nicht** geschlossen und wird hier sichtbar weitergereicht:

1. **CR-17 — die vier worker-eigenen Plain-Tabellen** (`as_domain_event_outbox`, `as_domain_event_dlq`, `as_webhook_subscription`, `as_webhook_delivery_log`): keine RLS, keine `tenant_id`-Spalte, keine ausdrückbare Policy. Der Django-Admin-Superuser bleibt ein **menschlich erreichbarer Cross-Tenant-Pfad**. Die Kompensationsmaßnahmen sind **ausschließlich** Service-/Codepfad-Ebene.
2. **CR-26 — Revocation der Refresh-Familie nach Passwortwechsel:** kein Endpunkt, kein Revocation-Hook, keine `authz_version`/`password_changed_at`/`tokens_valid_after`-Prüfung. **Architekturentscheidung erforderlich.** Kleinste schließende Form: ein Passwort-Änderungs-Endpunkt plus ein serverseitiger Revocation-Zustand, den `validate_bearer_token` und die Refresh-Familie auswerten — bewusst nicht gebaut (außerhalb des Scopes).
3. **CR-22 — Batch-Fehlervertrag und Hermes-TypeScript-Timeout-/Retry-Verträge:** untestiert.
4. **Cost-Seam (CR-20):** der LLM-/Provider-Budget-Default (`None`) und die read-only-, Hintergrund- und Health-Pfade, die eine zentrale Quota umgehen, sind in diesem Slice **nicht** bearbeitet.
5. **Vollständige Trust-Dokumentation:** in diesem Slice **nicht** erstellt.
6. **Release-/Supply-Chain-Gates:** kein Test-vor-Image-Gate, kein Image-Digest, keine SBOM/Provenance, kein isolierter Restore-Smoke (CR-30, CR-32, CR-37, CR-38, CR-39) — **nicht** bearbeitet.
7. **Frontend-/Browser-/Accessibility-Matrix** (CR-40/CR-41) — **nicht** bearbeitet; es wurde keine einzige Frontend-Datei angefasst.
8. **Der neue CI-Job `workflow-lint` ist noch nicht auf einem echten CI-Runner gelaufen.** Evidenz ist ausschließlich der lokale, digest-gepinnte Container-Lauf. Die Job-Konfiguration ist geschrieben, ihr Lauf in CI ist unbestätigt.
9. **Ruff-Versionsabweichung:** lokal 0.16.9, CI pinnt 0.16.5. Das lokale `I,F,E`-Ergebnis ist eine **Superset-Prüfung** und keine byte-identische CI-Reproduktion.
10. **`makemigrations --check`:** der Lauf gab einen `RuntimeWarning` aus, dass die Zieldatenbank nicht erreichbar war; der Teil-Check zur History-Konsistenz konnte daher nicht verbinden. Das Model-Drift-Verdict ist **filesystem-basiert** und davon unberührt.
11. **Die vier CR-17-Assertions zu Webhook/Outbox sind ein Codepfad-/Kompensationsmaßnahmen-Argument, KEINE datenbankseitig erzwungene Garantie.**

#### 8.6.1 Priorisierte Nacharbeiten aus der Review-Runde zu PR #1071 (2026-09-25)

Dieser Block ist ein **datierter Nachtrag** zu [8.6](#86-verbleibendes-restrisiko-bewusst-offen-geführt). Die elf Punkte 1–11 oben bleiben unverändert stehen; die folgenden Punkte sind **neu** in der Review-Runde entstanden und sind untereinander nach Priorität geordnet. Keiner von ihnen wurde in PR #1071 behoben.

##### P1 — `pl_user`: Pre-Authentication-Lookup auf einer Tabelle ohne RLS — bewusst NICHT in diesem PR behoben

**Was `pl_user` ist — verifiziert durch Recherche, nicht angenommen:**

`pl_user` ist eine **PostgreSQL-Tabelle**. Sie ist **keine** PostgreSQL-Rolle und **kein** Django-Permission-/Rollenlabel. Es ist der `db_table` des Django-`User`-Modells (das `AUTH_USER_MODEL`):

| Beleg | Fundstelle |
|---|---|
| Modellklasse `class User(AuditableModel)` — ein **einfaches** Auditable-Modell, **nicht** `TenantScopedModel` (`backend/persistence/models.py:442`) | `backend/persistence/models.py:497` |
| `db_table = "pl_user"` | `backend/persistence/models.py:550` |
| Tabellenerzeugung | `backend/persistence/migrations/0001_initial.py:54` (`options={"db_table": "pl_user"}`) |
| `tenant`-FK ist **nullable** (`null=True`, `blank=True`, `on_delete=PROTECT`) — Plattform-Admins ohne Tenant sind ein vorgesehener Zustand | `backend/persistence/models.py:541–547` |

**RLS-Status — bewusster Ausschluss, keine Lücke im Sinne von CR-17:** `backend/persistence/migrations/0003_rls_policies.py:43–45` kommentiert die Tenant-Tabellenliste mit „Tenant and User are intentionally excluded: Tenant is the boundary itself and User may be tenant-less (platform admin)." `pl_user` steht damit **nicht** in `_TENANT_TABLES`, **nicht** in `backend/persistence/migrations/0067_rls_remaining_pl_tables.py` und **nicht** in `RLS_EXEMPT_TABLES` (`backend/persistence/tests/test_rls_coverage.py:75`). Die Tabelle hat damit **keine** Policy.

**Der Pre-Authentication-Lookup — was er tut:**

| Schritt | Fundstelle | Wirkung |
|---|---|---|
| `ApiKey.unscoped.select_related("user").filter(key_hash__in=candidates).first()` | `backend/auth_tenancy/services/authentication.py:511–515` | `select_related("user")` ist ein **JOIN auf `pl_user` in derselben Query** — ausgeführt, **bevor** die Anfrage authentifiziert ist. |
| Begründung im Docstring: „Lookup uses the ``unscoped`` manager because no tenant context exists yet at authentication time." | `backend/auth_tenancy/services/authentication.py:494–495` | Der Codepfad benennt sich selbst als Pre-Authentication. |
| `if api_key.user.tenant_id is None: raise AuthenticationFailed("invalid_api_key")` | `backend/auth_tenancy/services/authentication.py:537–539` | **Die Tenant-Identität wird aus der `pl_user`-Zeile abgeleitet, nicht aus der Key-Zeile.** |
| `class UnscopedManager` — „Row-Level Security (COMP-PL-006) remains the backstop even when this manager is used through the application connection" | `backend/persistence/tenancy.py:161–171` | Für `at_api_key` trägt diese Zusage (Policy greift nicht beim Owner). Für **`pl_user` trägt sie nicht**: die Tabelle hat keine Policy, also *keinen* RLS-Backstop. |
| Gleiche Form im neuen Inventar-Command: `ApiKey.unscoped.all()` mit `SET LOCAL row_security = off` und Ausgabe von `row["user__username"]` / `row["user_id"]` | `backend/auth_tenancy/management/commands/inventory_api_keys.py:357–363`, `:383–384` | Ein Management-Command hat **überhaupt keinen** authentifizierten Principal. |

**Warum das eine eigene Entscheidung braucht und kein Inline-Fix ist:**

1. **Der Zugriff ist tragend, nicht dekorativ.** Er ist die Quelle der Tenant-Identität, mit der nachgelagert `app.current_tenant` armiert wird. Man kann den Lookup nicht einfach „entfernen", „einschränken" oder „unter RLS stellen", ohne vorher zu entscheiden, was die autoritative Tenant-Quelle sein soll.
2. **Eine Standard-Policy ist hier nicht ausdrückbar.** `tenant_id` ist nullable, und die GUC-gebundene Policy würde für genau die Pre-Auth-Query null Zeilen liefern, die erfolgreich sein **muss**. Das ist strukturell dasselbe Henne-Ei-Problem, das für die Schwester-Tabelle bereits in `RLS_EXEMPT_TABLES["at_api_key"]` (`backend/persistence/tests/test_rls_coverage.py:76–81`) dokumentiert ist.
3. **Die reparierenden Formen sind architektonisch verschieden** und jede verändert den Authentifizierungsvertrag: Tenant auf der Key-Zeile denormalisieren · eine eigene `api_key_principal`-Tabelle einführen · einen Pre-Auth-Auflösungsdienst bauen · eine dokumentierte Plattform-Admin-Ausnahme akzeptieren. Die Wahl zwischen ihnen ist eine Entscheidung, kein Patch.
4. **Konsequenz für dieses PR:** `pl_user` ist in PR #1071 **bewusst nicht angefasst**. Es wird weder gepatcht noch wegkonfiguriert noch als akzeptiert markiert.

**Rangfolge — und warum genau hier:** `pl_user` ist der **höchstpriorisierte Punkt unter den in dieser Review-Runde neu entstandenen Nacharbeiten** (P1 in diesem Block, also über P2 und P3), weil er auf dem **Authentifizierungspfad** sitzt und — anders als die übrigen neuen Punkte — **keine kompensierende Kontrolle** besitzt: die P2-/P3-Punkte sind Testabdeckungslücken, die einen vorhandenen, wenn auch nicht datenbankseitig erzwungenen Codepfad betreffen; `pl_user` ist ein realer Tabellenzugriff ohne RLS-Backstop. Er ist gleichwohl **bewusst nicht** über die vorbestehenden Punkte 1–11 der [8.6](#86-verbleibendes-restrisiko-bewusst-offen-geführt) gehoben, weil seine Exposition **begrenzt** ist: gelesen wird ausschließlich die Owner-Zeile **eines** bereits über den Hash identifizierten Keys — keine Aufzählung, keine Massenabfrage über Tenants. Punkt 1 (die vier worker-eigenen Plain-Tabellen) ist nach Wirkung höher, weil ein Staff-Superuser dort alle Tenants' Outbox-Zeilen lesen kann; Punkt 2 (Revocation nach Passwortwechsel) ist eine fehlende Funktion. Diese Einordnung ist eine **Priorisierungsentscheidung dieses Registers**, keine aus dem Code abgeleitete Severity.

##### P2 — `X-Project-ID` und `X-User-ID`: nicht eigenständig getestet

Siehe die vollständige Lückendarstellung in [8.4](#84-was-je-audit-track-tatsächlich-geschlossen-wurde). Kurzfassung: Für die beiden Geschwister-Header derselben Klasse wie `X-Workspace-ID` existiert **kein** Test, der beweist, dass sie die Identität nicht ändern, und **kein** dedizierter Test, der beweist, dass sie nicht gelesen werden. Die Codepfad-Begründung für `X-Workspace-ID` wurde für sie **nicht** analysiert und wird **nicht** übertragen. Sie werden weder als sicher noch als unsicher geführt — die Lücke ist der Befund. **Offen.**

##### P3 — drei Testverzeichnisse werden von keinem CI-Matrix-Set ausgeführt

Bei der CI-Matrix-Änderung dieser Runde (Aufnahme von `context_graph/tests`) fiel auf, dass drei weitere Testverzeichnisse von **keinem** Set ausgeführt werden. Verifiziert gegen die Matrix in `.github/workflows/ci.yml:41–55` (vier Sets: `set-1-core` = `application/tests persistence/tests`; `set-2-api` = 5 Pfade; `set-3-mcp` = `mcp_server/tests`; `set-4-features` = 11 Pfade):

| Verzeichnis | `test_*.py` (verifiziert via `git ls-files`) | In einem Matrix-Set? |
|---|---|---|
| `backend/link_types/tests/` | **14** | **nein** |
| `backend/memory/tests/` | **13** | **nein** |
| `backend/tests/` (Projektwurzel) | **4** — darunter `test_required_secrets.py` | **nein** |

- Sie wurden in dieser Runde **bewusst nicht** aufgenommen. Der Aufnahme von `context_graph/tests` lag eine konkrete Begründung vor (siehe [8.7](#87-review-follow-up-zu-pr-1071-2026-09-25)); für diese drei Verzeichnisse ist eine solche Begründung **nicht** erhoben worden, und sie zu ergänzen, ohne sie zu untersuchen, wäre eine Ausweitung des Scopes.
- **Gesondert zu entscheiden:** Dass `backend/tests/test_required_secrets.py` in CI nicht läuft, ist **nicht** nur eine Zahlenlücke. Ein Required-Secrets-Test, der im PR-Gate nicht ausgeführt wird, prüft die Secret-Konfiguration nicht gegen den einzigen Ort, an dem neue Änderungen auflaufen. Ob dieser Test laufen **muss**, in ein eigenes Set gehört oder bewusst anders behandelt wird (z. B. Host-Umgebung), ist eine **offene Entscheidung** und wird hier ausdrücklich als eine solche geführt, nicht als Detailpunkt.
- **Sichtbare Wirkung:** Vor dieser Runde wäre der in `f85407f7` ergänzte CR-02-Projector-Test nie in CI gelaufen. Dieselbe Mechanik betrifft weiterhin diese drei Verzeichnisse.

### 8.7 Review-Follow-up zu PR #1071 (2026-09-25)

Dieser Abschnitt ist ein **datierter Nachtrag zur Review-Runde auf PR #1071** und ergänzt [8.3](#83-ausgeführte-kommandos-und-ergebnisse), ohne dessen Zahlen zu löschen. Wo die Review-Runde zu **anderen** Werten kommt, benennt die jeweilige Zeile die superseded Größe ausdrücklich. Commitbindung: `f85407f7b9684426dec989ade265d1bc4eb70217` + 5 geänderte Pfade, **noch nicht committet** (siehe [8.0](#80-revision-branch-und-commitbindung) und [7.5](#75-weiterführung-der-provenienz-auflösung-2026-09-25-pr-1071)).

**Geänderte Pfade dieser Review-Runde (5, verifiziert über `git status --porcelain=v1 -uall`; `git diff --stat` = 5 files changed, 1172 insertions, 87 deletions):** `.github/workflows/ci.yml`, `backend/auth_tenancy/management/commands/inventory_api_keys.py`, `backend/auth_tenancy/tests/test_inventory_api_keys_command.py`, `backend/persistence/tests/test_rls_coverage.py`, `backend/persistence/tests/test_rls_plain_child_models.py`

#### 8.7.1 Neue gemessene Testzahlen

| Lauf | Ergebnis | Exit |
|---|---|---|
| Berührte Module zusammen | **90 passed**, 0 failed, **1 xfailed**, 0 deselected, 0 skipped | **0** |
| `auth_tenancy/tests/ rest_api/tests/test_api_key_agent_fields.py` | **435 passed, 1 xfailed** | **0** |
| `baseline/ context_graph/ persistence/ application/tests/test_event_bus.py application/tests/test_webhook_dispatcher.py mcp_server/tests/test_audit_tool_group.py memory/tests/test_projector_rls_tenant_resolution.py` | **637 passed** | **0** |
| W1-Slice-Re-Run: `rest_api/tests/test_workspace_id_header_decorative.py rest_api/tests/test_workspace_scoped_roles.py rest_api/tests/test_bearer_token_role_resolution.py mcp_server/tests/test_mcp_workspace_id_header_decorative.py mcp_server/tests/test_mcp_workspaceless_revocation.py context_graph/tests/test_projector_rls_tenant_arm.py` | **76 passed** | **0** |
| **Summe der vier Läufe** | **1238 passed**, 0 failed, **1 xfailed** | — |
| `context_graph/tests` allein unter PostgreSQL (ganzes Verzeichnis) | **26 passed** | **0** |

**Der einzelne `xfail` ist beabsichtigt und wird hier ausdrücklich offengelegt — er ist keine verdeckte Auslassung.** Test: `test_a_json_null_fence_column_would_be_reported_as_unset`, deklariert mit `xfail(strict=True)`. Grund: `ApiKey.workspace_ids` ist `NOT NULL` und hat weder ein `clean()` noch einen Validator, ein JSON-`null`-Fence ist also **nicht erreichbar**. Der Strict-Marker bewirkt, dass der Test zu einem **harten Fehlschlag** umschlägt, sobald die Spalte jemals nullable wird. Der Test dokumentiert damit einen bekannten, unerreichbaren Zustand, statt ein Ergebnis zu verstecken.

**Drei Zählregeln, damit die Summe nicht falsch gelesen wird:**

1. **Der xfail ist *ein* Test, kein Summand.** `1 xfailed` wird in **zwei** der vier Läufe gemeldet, weil dieselbe Deklaration von beiden Auswahlen erfasst wird. Die Aggregatzahl 1 ist die Zahl **distinkter** xfail-Testfälle, nicht die Summe über die Läufe.
2. **Der 26er-Lauf ist ein fünfter Lauf außerhalb der Vierer-Summe.** Er deckt das **ganze** Verzeichnis `context_graph/tests` ab und ist nötig, weil dieses Verzeichnis jetzt in der CI-Matrix liegt. Er überlappt den `context_graph/`-Anteil des 637er-Laufs und wird deshalb **nicht** zur Summe addiert — eine Gesamtsumme über alle fünf Läufe würde doppelt zählen.
3. **Das ist eine Abweichung von der vorigen Messlatte und wird benannt, nicht geglättet:** die vorherige Runde in [8.3](#83-ausgeführte-kommandos-und-ergebnisse) protokollierte „0 deselected/skipped". Der Balken dieser Runde lautet **0 deselected, 0 skipped, 1 xfailed** — die Null-Linie bei deselected/skipped bleibt also gehalten, und **neu** ist ausschließlich der eine, bewusst deklarierte `xfail`.

#### 8.7.2 Übrige Gates dieser Runde

| Gate | Ergebnis | Exit |
|---|---|---|
| `ruff check . --select=F821,F822` | keine Findings | **0** |
| `ruff check --select=I,F,E` über die 4 geänderten Python-Dateien | keine Findings | **0** — **superseded: zuvor Exit 1 mit 5 Findings, jetzt bereinigt** |
| `python -m compileall -q` (Host **und** Container) | keine Findings | **0** |
| `python manage.py check` | „System check identified no issues (0 silenced)" | **0** |
| `python manage.py makemigrations --check --dry-run` | „No changes detected" | **0** |
| `git diff --check` | keine Findings | **0** |
| Diff-only `scan_for_secrets` | **0 Findings** | — |
| `actionlint` mit impliziter Discovery | grün | **0** |

**Korrektur zu [8.1](#81-verifizierte-umgebung), datiert 2026-09-25:** Dort war der Host als **3.13.14** notiert. Der Host ist tatsächlich **3.14.7**. Das für das Gate maßgebliche Runtime ist der **Container** mit **3.12.14** — diese Angabe war und ist richtig. Die falsche Host-Version ist in 8.1 berichtigt; sie hat keine Gate-Aussage getragen, da kein pytest-Lauf auf dem Host stattfand.

**Secret-Scanner — Validierung des Scanners selbst:** Der diff-only Lauf ergab **0 Findings**. Der Scanner wurde dabei mit einer **Positivkontrolle** geprüft: von 7 synthetischen Secrets hat er **6** erkannt; der eine Nicht-Treffer wurde korrekt durch die `example`-Platzhalterregel unterdrückt. „0 Findings" ist damit als echtes Negativ belegt und nicht als stilles Überspringen.

**actionlint mit impliziter Discovery:** Exit **0**; `-verbose` meldet `Collected 5 YAML files` / `0 errors in 5 files` und listet `docker-publish.yml`, `pages.yml`, `playwright.yml`, `ci.yml`, `version-drift-check.yml` — exakt die fünf versionierten Dateien unter `.github/workflows/` (verifiziert via `git ls-files .github/workflows/`). Der Job-Parameter `args: -color` (`.github/workflows/ci.yml:345`) und die Argumente des lokalen Kommandos sind nun **identisch**, der lokale und der CI-Umfang decken sich also.

**Nachweis, dass die Discovery echt ist (kein Überspringen und kein Null-Umfang):** Eine Wegwerf-Probe-Workflow mit einem bekannten Verstoß wurde **gemeldet** und hob die Coverage von 5 auf **6**. Eine Negativkontrolle auf einer Scratch-Kopie bestätigte, dass alle fünf bestehenden Workflows **weiterhin** gelintet werden. Der Job überspringt also keine Dateien und lintet nicht null.

**Nicht-obvious Vorbedingung, entdeckt und im Job-Kommentar dokumentiert:** Implizite Discovery löst einen **Projekt-Root** auf und **schlägt fehl** mit `no project was found in any parent directories of "/repo"` (Exit **3**), wenn `.git` im Mount nicht sichtbar ist. `actions/checkout` stellt es bereit (`.github/workflows/ci.yml:340`); die Vorbedingung steht im Job-Kommentar (`.github/workflows/ci.yml:321–330`).

**Last-bearing Property des CR-17-Justifications-Guards bewiesen:** Auf einer Scratch-Kopie wurde **ein** erforderlicher Claim-Marker gelöscht, während die Datei **länger** gemacht wurde — sodass die frühere Längenprüfung `> 200` nicht das sein konnte, was den Befund ausgelöst hat. Ergebnis: Guard **rot** mit `1 failed, 3 passed`, Exit **1**. Der Guard hängt also an den konkreten Claim-Markern, nicht an einer Längenschwelle.

**Datenbank:** durchgehend echtes **PostgreSQL 16.15**; `pg_policies` = **67**; die Suiten verwenden `SET ROLE "reqogniloom_app"`. **Kein SQLite-Fallback.** Zu `pg_policies` = 67 gegenüber 68 in [8.1](#81-verifizierte-umgebung): beide Werte stehen ungeglättigt nebeneinander; dieses Register erklärt die Differenz nicht und leitet daraus keinen Befund ab.

**Selbstkorrigierter Probe-Fehler, vom Ausführenden offengelegt:** Eine Engine-Proof-Probe schlug **zuerst an ihrer eigenen fehlenden Datenbank** fehl — **nicht** an einem Produktproblem.

#### 8.7.3 Änderungen dieser Review-Runde und ihre Begründung

**a) Actionlint-Job — Pfadliste durch Discovery ersetzt.** Die hart kodierte Fünf-Pfad-Liste wurde durch implizite Discovery ersetzt, damit eine neu hinzugefügte Workflow-Datei **nicht** an einer veralteten Liste vorbeirutschen kann. Ergänzt wurde job-scoped `permissions: contents: read` (`.github/workflows/ci.yml:336–337`) — Least Privilege, der Job liest nur die ausgecheckten Workflow-Dateien. **Kein** Workflow- oder Repository-Level-`permissions`-Block wurde ergänzt; die **anderen sechs Jobs** (`lint`, `backend-test`, `requirements-drift-check`, `agent-templates-test`, `frontend-test`, `hermes-plugin-test` — verifiziert über die Job-Definitionen in `.github/workflows/ci.yml:10, 32, 155, 236, 255, 284`) behalten damit die Repository-Voreinstellung; **je Job verifiziert**. Version und Digest unverändert, **kein** `-ignore`, **kein** `shellcheck: ""`.

**b) CI-Matrix — `context_graph/tests` aufgenommen.** Aufnahme in `set-4-features`, das damit **11 Pfade** umfasst; der **Set-Name wurde mitgezogen**, damit er zutreffend bleibt. Begründung: `backend/context_graph/apps.py` deklariert die App als **ADR-01-Layer-1-App parallel zu `traceability`/`baseline`/`workflow`**, und alle drei liegen bereits in diesem Set. Der Name von `set-1-core` wurde **nicht** angetastet, weil dessen Inhalt unverändert blieb. Wirkung: Vor dieser Änderung wäre der in `f85407f7` ergänzte CR-02-Projector-Test **nie in CI gelaufen**.

**c) Klassifikation des Inventar-Fences — ein echter Bug, nicht nur ein fehlender Test.** Die Fence-Regel lautete `if not workspace_ids`, sodass ein Fence **nicht-kanonischer** Einträge als „set" durchging. Empirisch **vor** dem Fix verifiziert: `missing=[] candidate=False` für `["not-a-uuid"]`. Kanonizität wird jetzt über **Round-Trip** entschieden: `str(UUID(value)) == value` — bewusst **strenger** als ein Parse-Test, weil `UUID()` bloße 32-stellige Hex-, Upper-Case-, `{}`-geklammerte und `urn:uuid:`-Formen akzeptiert und sie stillschweigend umschreibt. Drei Zustände: `unset` · `set` (jeder Eintrag kanonisch) · `defective` (≥1 nicht-kanonisch, einschließlich gemischter Fences). Die Regel ist eine **Konjunktion** — ein gemischter Fence ist daher `defective`, nicht `set`. `defective` fließt durch die text-/json-/csv-Renderer und wird in den Summen mitgezählt.

**d) Klassifikation künftiger Rotationen — je Vertragsregel festgenagelt.** Ein Key, der **streng nach** dem Wirksamkeitsdatum 2026-09-25 erzeugt wurde und eine Regel verletzt, bleibt Rotationskandidat — mit dem **regelgeleiteten** Grund und **ausdrücklich nicht** dem Vor-Regel-Grund. Ein regelkonformer künftig datierter Key ist kein Kandidat. Vorher war **nur** der Vor-Regel-Auslöser abgedeckt.

**e) RLS-Exemption-Begründungen — erweitert, und der Guard prüft jetzt Markern statt Länge.** Die Begründungen wurden um **verifizierte, tabellenweise Django-Admin-Exposition** erweitert. Der Guard (`backend/persistence/tests/test_rls_plain_child_models.py`) prüft nun **konkrete Claim-Marker** (`CR17_JUSTIFICATION_CLAIMS`) statt einer Längenschwelle, sodass die Admin-Expositions-Sätze **nicht mehr still** entfernt werden können. Der Guard trägt zusätzlich eine **Veraltungsprüfung**, die den Claim-Satz an das Exemption-Inventar bindet.

**f) Outbox-Reader/Writer-Allowlist für `as_domain_event_outbox`.** Deklarierte **Reader**: `application/event_bus.py` und `application/admin.py` (die Allowlist-Namen im Guard sind `OUTBOX_READER_MODULES` und `OUTBOX_WRITER_MODULES`, `backend/persistence/tests/test_rls_plain_child_models.py:998,1003`). Deklarierte **Writer**: `application/dlq_service.py`. Nicht klassifizierte Zugriffsformen zählen als **READER** (fail-closed). Ein Writer, der zugleich liest, wird **abgelehnt**, damit sich ein Reader nicht hinter einem Writer-Label verstecken kann. Eine **Nicht-Vakuizitäts-Assertion** verhindert, dass die Allowlist durch classifying everything as reader grün wird. **Legitime Writer werden nicht blockiert:** Module, die ausschließlich `DomainEventOutbox.EventType.*` referenzieren, werden korrekt **nicht** als Tabellenzugriff gezählt — die Review-Runde nennt dafür **15** Module.

> **Präzisierung (verifiziert 2026-09-25, `git grep -l -E "DomainEventOutbox\.EventType" -- backend/`):** Der Ausdruck trifft aktuell **15 Dateien**, aber **nicht** 15 Module, die *ausschließlich* das Enum referenzieren. Zwei der 15 sind gesondert zu behandeln: `backend/application/event_bus.py` ist selbst der **deklarierte Reader** und greift damit durchaus auf die Tabelle zu, und `backend/persistence/tests/test_rls_plain_child_models.py` ist der **Guard selbst**, nicht ein Kandidat. Die als „rein Enum-referenzierend" ausgeschlossenen Module sind damit die übrigen **13** der Trefferliste. Die Kennzahl 15 der Review-Runde bleibt als deren Messstand zitiert; dieses Register erhebt **keinen** Gegenwert, weil die Allowlist zur Laufzeit über Zugriffsformen und nicht über Dateinamen klassifiziert — die Dateiliste ist nur die Grundlage dieses Negativbefunds.

**g) Docstring-Übertreibungen — an drei Stellen korrigiert.**
1. Der Read-only-Test des Inventars benennt jetzt **nur die fünf Mutatoren**, die er tatsächlich patcht, und stellt **explizit** die ungepatchten Lücken dar sowie welche anderen Tests diese abdecken.
2. Der RLS-Guard für `at_api_key` ist jetzt als **Anti-Regression-Tripwire** beschrieben, das für diese Tabelle **derzeit ein NO-OP** ist — weil `validate_api_key` den Tenant **aus der Zeile** auflösen muss, bevor ein Tenant-Kontext überhaupt existieren kann. Das entspricht der Korrektur am Docstring in `backend/persistence/tests/test_rls_coverage.py:372–399`.
3. die **Plain-Child-Äquivalenz-Behauptung** trennt jetzt, was **belegt** ist (das RLS-geschützte Plain-Child wird demselben Maßstab unterworfen) von dem, was **nicht** belegt ist (die **vier** worker-eigenen Tabellen sind **nicht** äquivalent und werden nur vom Deklarations- und Kompensationskontroll-Check erfasst).

#### 8.7.4 Was diese Review-Runde **nicht** geändert hat

- **Kein Track-Status kehrt sich.** Alle Statuszellen in [Abschnitt 2](#2-kanonisches-finding-trackregister) bleiben unverändert; CR-22, CR-17 (Resthälfte) und CR-26 bleiben wie in [8.5](#85-w1-exit-kriterien-nur-tatsächlich-verifiziert-grün) offen fortgeführt.
- **`pl_user` wurde nicht behoben** — bewusst, siehe [8.6.1 P1](#p1--pl_user-pre-authentication-lookup-auf-einer-tabelle-ohne-rls--bewusst-nicht-in-diesem-pr-behoben).
- **`X-Project-ID`/`X-User-ID` wurden nicht getestet** — siehe [8.6.1 P2](#p2--x-project-id-und-x-user-id-nicht-eigenständig-getestet).
- **Die drei ungelisteten Testverzeichnisse wurden nicht aufgenommen** — siehe [8.6.1 P3](#p3--drei-testverzeichnisse-werden-von-keinem-ci-matrix-set-ausgeführt).
- **Kein Schreibvorgang an Anwendungs-, Test-, CI- oder bestehenden Auditdateien** außerhalb der in 8.7.3 genannten fünf Pfade; dieses Register ist die einzige Dokumentationsdatei dieser Runde.

```text
STATUS: done
RESULT: Alle 47 kanonischen Reconciliation-Tracks sind mit Quellenbericht, Primärbeleg, Test-/CI-Beleg, Severity, Confidence, Tatsache/Hypothese, Verifikationsplan und Status auffindbar. Historische Runtime- und externe CVE-Aussagen bleiben ausdrücklich als historisch, E oder O markiert.
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md
```
