---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: validator
revision: e3df119e52c0cbcc18df02f708567207c0374826
branch: feat/1031-bluepencil-host-bridge
---

# Systemaudit 2026-09 — Konsistenzprüfung der Tiefenaudits

**Prüfgegenstand:** Zweite, unabhängige Konsistenz- und Reconciliation-Prüfung der Berichte `01`, `02`, `03`, `04`, `05`, `06`, `07` und `10` aus `docs/se/reports/deep_audit/system-audit-2026-09/`  
**Nachtrag:** Die unabhängige Kernclaim-Validierung und die daraus folgenden Korrekturen sind in [`12-evidence-validation-and-corrections.md`](12-evidence-validation-and-corrections.md) dokumentiert und für die betroffenen P1-Claims maßgeblich.  
**Prüfrevision:** `e3df119e52c0cbcc18df02f708567207c0374826`  
**Prüfdatum:** 2026-09-24  
**Änderungsgrenze:** ausschließlich dieser Bericht; keine Anwendungs-, Test-, CI-, Infrastruktur- oder bestehenden Auditdatei wurde geändert.

## 1. Kurzurteil

Die acht Berichte enthalten **109 Quellbefunde** (33 P1, 69 P2, 7 P3, 0 P0). Nach Bereinigung von Überschneidungen und widersprüchlichen Zählungen ergeben sich **47 kanonische Reconciliation-Tracks**. Die zentrale Aussage des Audits bleibt bestehen: Es gibt keinen belegten P0-Befund, aber der geprüfte Stand ist **nicht als konsistenter Release-Gate freigabefähig**. Mehrere P1-Standardpfade (Tenant-Fence, API-Key-Erzeugung, MCP-Interview, Workflow-Konkurrenz, Auth-/Kostenkontrolle, CI-/E2E-/Release-Gates) sind nicht geschlossen oder nicht durch eine einheitliche aktuelle Testevidenz belegt.

Diese Prüfung ist eine Konsistenzprüfung, keine neue Code-Qualitätsbewertung. Sie übernimmt eine Feststellung nur, wenn sie in mindestens einem Bericht mit einem konkreten repo-relativ belegten Codepfad, Konfigurationspfad oder explizitem Nicht-Nachweis dokumentiert ist. Historische Runtime-Aussagen werden als historisch oder als offene Messung markiert und nicht als aktueller Zustand ausgegeben.

**Wichtig:** Die Berichte sind überwiegend statisch. `03`, `04` und `06` enthalten begrenzte Testläufe, aber es existiert kein einheitlicher, aktueller, vollständig grüner Backend-/Frontend-/E2E-/Container-Nachweis. Externe CVE- und Registry-Aussagen aus `10` wurden nicht unabhängig nachverifiziert.

## 2. Prüfgrundlage und Evidenzregeln

### 2.1 Verwendete Berichte und Revisionen

| Kürzel | Repo-relativer Bericht | Revisionsstand | Konsistenzbewertung |
|---|---|---|---|
| R01 | `docs/se/reports/deep_audit/system-audit-2026-09/01-architecture-and-boundaries.md` | `94a3737a312150713a0684c147260a13ded01f50` (`R01:11`) | älter als Prüf-HEAD; Runtime-Aussage historisch |
| R02 | `docs/se/reports/deep_audit/system-audit-2026-09/02-agents-plugins-mcp.md` | keine Revision im Bericht (`R02:1-7`) | als unversionierter/unverifizierter Beitrag behandelt |
| R03 | `docs/se/reports/deep_audit/system-audit-2026-09/03-api-ui-data-contract-drift.md` | `66e21f56` (`R03:11`) | vor Prüf-HEAD; statische Vertragsbefunde |
| R04 | `docs/se/reports/deep_audit/system-audit-2026-09/04-workflow-state-machines-and-se.md` | `66e21f56f36b10e9280e10fed75ee709e5bd7d50` (`R04:7`) | vor Prüf-HEAD; aktuelle Dateifassung nennt 9 P2 konsistent |
| R05 | `docs/se/reports/deep_audit/system-audit-2026-09/05-security-resilience-and-operations.md` | `e3df119e52c0cbcc18df02f708567207c0374826` (`R05:7`) | revisionstreu; überwiegend statisch |
| R06 | `docs/se/reports/deep_audit/system-audit-2026-09/06-frontend-ux-accessibility-and-design-system.md` | `66e21f56f36b10e9280e10fed75ee709e5bd7d50` (`R06:7`) | vor Prüf-HEAD; begrenzte Vitest-/Lint-Evidenz |
| R07 | `docs/se/reports/deep_audit/system-audit-2026-09/07-testing-ci-performance-and-dependencies.md` | `e3df119e52c0cbcc18df02f708567207c0374826` (`R07:7`) | revisionstreu; statische Testinventur |
| R10 | `docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md` | `e3df119e52c0cbcc18df02f708567207c0374826` (`R10:7`) | revisionstreu; externe Registry-/CVE-Aussagen nicht live verifiziert |

Die uneinheitlichen Revisionsstände sind selbst ein Befund der Nachweiskette: Kein Befund aus `R01` bis `R04` darf ohne erneuten Abgleich als Beobachtung am Prüf-HEAD ausgegeben werden. Für Codefakten wird im Folgenden der jeweils im Bericht genannte Codepfad verwendet; der Status `offene Messung` bleibt bestehen, wenn keine HEAD-nahe Laufzeitevidenz vorliegt.

### 2.2 Evidenzklassen

- **S — statisch:** Quelltext, Migration, Manifest, Konfiguration oder Dokumentation belegt den Zustand, aber keine Laufzeitwirkung.
- **T — Test:** Ein explizit gestarteter, eng begrenzter Testlauf oder ein generiertes Schema belegt nur den genannten Testumfang.
- **R — Runtime:** Ein Bericht beschreibt eine konkrete Beobachtung. Sie wird nicht auf den Prüf-HEAD übertragen, wenn der Bericht eine andere Revision oder ein anderes Zeitfenster nennt.
- **H — Hypothese:** Mögliche Auswirkung aus `S`/`R`; kein behaupteter Schaden.
- **E — externe Behauptung:** Registry-/CVE-/Vendor-Aussage aus einem Bericht, die in dieser Prüfung nicht unabhängig bestätigt wurde.
- **O — offene Messung:** Benötigt einen reproduzierbaren Lauf, bevor ein Release-Gate darauf gestützt wird.

### 2.3 Korrekturhinweis zur früheren R04-Berichtszählung

Die frühere/initial Dateifassung von `R04` nannte in der Summary `0 P0, 3 P1 und 8 P2`. Die aktuelle Quelldatei `R04:19` nennt bereits `0 P0, 3 P1 und 9 P2`; Befundtabelle `R04:94–105` und die neun P2-Detailüberschriften `R04:199,284,326,366,408,450,491,535,578` bestätigen diesen Stand. Die konsolidierte Zählung verwendet daher **3 P1 + 9 P2 = 12**. Die frühere Abweichung ist nur Audit-Trail, kein aktiver Widerspruch und kein neuer Produktbefund.

Damit besteht kein aktiver interner R04-Zählwiderspruch mehr; die frühere/initial abweichende Summary-Formulierung bleibt ausschließlich als Audit-Trail dokumentiert. Ähnlich ist `R05:915-916` ausdrücklich als False-Positive-Guard formuliert: Bluepencil und Minimal-Compose sind dort als standardmäßig deaktivierte Opt-in-/QS-Betriebsprofile beschrieben. Das ändert nicht die Existenz der Risiken, wohl aber ihre Reichweite und Prio-Kalibrierung.

### 2.4 Test- und Runtime-Matrix

| Quelle | Was tatsächlich belegt ist | Was nicht belegt ist |
|---|---|---|
| R02:41-62, 896-911 | statische MCP-/Manifest-/Plugin-Prüfung; positive Ratchets | keine Server-, Container-, Hermes- oder MCP-Client-Läufe |
| R03:57-91, 51 | read-only OpenAPI-Erzeugung; 3 Frontend-Dateien mit 19 Tests und Frontend-Build laut Bericht | keine vollständige Suite, kein PostgreSQL-Host, kein einheitlicher HEAD-Testlauf |
| R04:662-668 | statische Workflow-/SE-Prüfung; pytest-Versuch scheiterte an Windows-Plugin/`fcntl` bzw. Django-Initialisierung | kein grüner Workflow-/Traceability-Lauf |
| R05:38-44, 903-918 | statische Security-/Operations-Prüfung; keine Runtime-/CVE-Läufe | kein aktueller Auth-, SSRF-, SSE- oder CI-Injection-Lauf |
| R06:42-51, 759-766 | 24 Vitest-Dateien, 277 Tests, 272 bestanden; 5 lokale `localStorage`-Fehler; Lint 0 Fehler/290 Warnungen; kein laufender Docker-Stack | kein vollständiger Frontend-/Playwright-/Screenreader-/Browserlauf |
| R07:17, 465-475 | statische Testinventur, CI-/Release-/Performance-Befunde | keine Tests, Builds, Container oder Scanner in diesem Bericht |
| R10:17, 31-43, 269-279 | Manifest-/Lock-/SBOM-Inspektion; externe Angaben aus der Quelle | keine unabhängige CVE-Datenbankabfrage, kein Scanner-/SBOM-Lauf |

Die grünen Teilresultate aus `R03` und `R06` widersprechen den fehlgeschlagenen oder nicht ausgeführten Läufen nicht, weil sie unterschiedliche Testumfänge und Umgebungen beschreiben. Sie ersetzen jedoch keinen gemeinsamen, revisionsgebundenen Baseline-Lauf.

## 3. Reconciliation-Entscheidungen

### 3.1 Severity-Kalibrierung

| Befundtyp | Konsolidierte Einstufung | Begründung |
|---|---|---|
| Tenant-/Workspace-Fence, API-Key-Erzeugung, MCP-Multi-Formalize, aktive Workflow-Race, stale Bearer, LLM-Kostenpfad, CI-Injection, Release-Gate | P1, sofern der Standardpfad aktiv ist | Verfügbarkeit, Daten-/Security-Korrektheit oder Release-Nachweis ist wesentlich betroffen |
| Dev-Compose-Migration, Bluepencil, Minimal-Compose, langsame Webhooks, externe Provider-/Backup-Szenarien | P1 nur unter expliziter Aktivierung bzw. belegtem Runtimepfad; sonst P2/bedingt | Erreichbarkeit und Betriebsprofil begrenzen die Reichweite |
| Vertrags-, Dokumentations-, Coverage-, Accessibility- und Defense-in-Depth-Lücken | P2, sofern kein belegter aktiver Daten-/Security-Schaden | materielle, aber begrenzte Reichweite |
| Enum-/Version-/Dokumentationshygiene ohne Laufzeitwirkung | P3 | lokale Wartungs- oder Nachweiswirkung |

Die Prio der Quellbefunde wird nicht durch einfaches Mittelwert-Aggregieren verändert. Jede kanonische Zeile nennt deshalb die Abweichung zwischen Quell-Prio und konsolidierter Prio.

### 3.2 Wesentliche Konflikte und Korrekturen

| Konflikt | Quellen | Konsolidierte Auflösung |
|---|---|---|
| R04: Frühere/initial Summary nannte 8 statt 9 P2 (Audit-Trail) | Aktuelle Quelldatei `R04:19,94–105,199–608` | Aktueller Stand: 9 P2; korrigierte Gesamtzahl 69 P2; kein aktiver Zählwiderspruch |
| „bounded MCP pool“ vs. unbounded Queue | `R07:28,446` gegenüber `R02:582-612` und `R05:528-567` | Nur die Zahl der Worker ist begrenzt (`max_workers=10`); die Arbeit/Warteschlange ist nicht begrenzt. `CR-29` bleibt P2 |
| Bluepencil P1 vs. Default-off/QS-only | `R02:488-529` gegenüber `R05:915-916`, `R06` | Opt-in-Security-Lücke bleibt; kanonisch **bedingt P1, im Default-/Produktionsprofil P2**, bis Aktivierung/Exposition belegt ist |
| Minimal-Compose P2 vs. bewusstes Profil | `R01:417-452` gegenüber `R05:915-916` | Kein stiller Produktionsfehler; Capability-/Readiness-Lücke des ausgewählten Profils (`CR-44`) |
| Laufender Restart-Stack vs. kein laufender Stack | `R01:22,55,641-645` vs. `R06:759-766` und `R07:17` | Zeit-/Revisionskonflikt. Restart-Beobachtung bleibt historisch (`R`), aktueller Stack-Status bleibt `O` |
| Outbox „robust“ vs. Webhook-Blockade | `R01:18,232-267` | Transactional-Outbox-INSERT und externe Webhook-Zustellung sind getrennte Verträge; nicht widersprüchlich, aber unzureichend getrennt (`CR-18`) |
| Toolzahlen 218/35 vs. 215/31 vs. 188/31 vs. 20/40 | `R02:15-18,680-686`, `R03:47`, `R01:454-488` | `docs/agent-templates/tool-manifest.json:2-4` ist der aktuelle Manifestanker; README/SSOT/Prompts sind Driftquellen, keine alternativen Tool-SSOTs (`CR-21`) |
| Trace-Link-Typen 6/8 vs. 11 | `R04:292-297,334-345`, `R04:647-648` vs. `R01:454-465` | Aktueller Code/Katalog (`backend/traceability/types.py:20-37`, `backend/link_types/builtin.py:1-27`) ist Implementierungsquelle; normative Dokumente/Matrix sind stale (`CR-15`, `CR-47`) |
| Workspace-Sprache: Requirements/Code/Adapter | `R03:198-236`, `R01` nicht als eigener Befund | Code zeigt eine geteilte Quelle; kein Bericht darf `preset.language` und `Workspace.language` als austauschbar behandeln (`CR-13`) |
| API-Key P1 vs. P2 | `R02:349-394`, `R03:238-276` = P1; `R05:344-386` = P2 | Ein gemeinsamer Security-Lifecycle-Befund; für neu erzeugte Agent-/UI-Keys **P1**, Legacy-Key-Härtung P2 (`CR-03`) |
| SSRF: ein breiter vs. mehrere Endpunktbefunde | `R01:269-303,379-415`; `R05:388-430` | Gemeinsamer Egress-Root, aber getrennte Endpunkte/Privilegien; nicht als vollständiges Duplikat zählen (`CR-19`) |
| Dependency-/Release-Zuständigkeit | `R07:453-457` erklärt R10 für `DEP-001..005/012` autoritativ | Release-Reihenfolge (`REL-001`) und Dependency-Provenienz (`DEP-*`) bleiben getrennte Unterpunkte eines Release-Tracks (`CR-32`, `CR-38`, `CR-39`) |
| Externe CVE-/Vendor-Aussagen | `R10:21-29,35-43,214-225` | Nur als E/O behandelt; kein CVE-Status und keine Dependency-Änderung aus dieser Prüfung ableiten |

## 4. Kanonisches Finding-Ledger

Die folgende Zuordnung ist absichtlich vollständig gegenüber den 109 Quellbefunden. `D` bedeutet echtes Duplikat/gleiche Maßnahme, `C` Konflikt, `S` separater Subbefund trotz Themenüberschneidung, `—` eigenständig.

### 4.1 Architektur, Application- und Vertragsgrenzen

| Kanonische ID | Quellbefunde | Konsolidierte Aussage / Disposition | Prio / Konfidenz | Beleg und nächste Evidenz |
|---|---|---|---|---|
| CR-01 | AB-001, OPS-003 (S) | Compose-Migrationsgrenze und separater CLI-Kompatibilitätsfehler: Dev-Backend führt DDL mit App-Rolle aus; Legacy-/v2-Compose-Befehle sind zusätzlich inkonsistent. Runtime-Fehler aus R01 historisch, Konfiguration weiterhin relevant. | P1 / H statisch, R historisch | `deploy/docker-compose.override.yml:64-72`; `deploy/docker-compose.yml:251-265,330-371`; `R01:117-153`; `R07:373-394`; aktueller `docker compose config`/frischer Stack offen |
| CR-02 | AB-002 (—) | ContextGraphProjector löst Tenant/Settings vor RLS-Arming; unscoped ORM umgeht nicht PostgreSQL-RLS. | P1 / H | `backend/context_graph/projector.py:75-109,163-185`; `backend/context_graph/admin_ops.py:45-57`; `R01:155-194`; App-Role-Regressionstest offen |
| CR-03 | F-02, CD-004, SR-006 (D/C) | Neue Agent-/UI-Keys können Legacy-Admin-Scope, leeren Workspace-Fence und `expires_at=NULL` erben. Quell-Prios P1/P1/P2 werden für neue fail-open Agent-Keys als P1 kalibriert; Bestandskeys bleiben migrations-/rotationsabhängig. | P1 / H | `backend/rest_api/api_key_views.py:285-365`; `backend/auth_tenancy/models.py:153-162`; `frontend/src/api/api-keys.ts:15-45`; `R02:349-394`; `R03:238-276`; `R05:344-386` |
| CR-04 | F-01 (—) | `comment.resolve` ist Write-Tool, aber Zielworkspace wird nicht über `comment → artifact → workspace` aufgelöst; unrestringierter Key kann tenantintern cross-workspace schreiben. | P1 / H | `backend/mcp_server/workspace_scope.py:173-176`; `backend/application/comment_service.py:151-173`; `R02:302-346`; negativer/positiver Fence-Test offen |
| CR-05 | CD-005 (—) | MCP-Schema/Handler reichen `confirmed_proposal` nicht durch; Multi-Formalize ist im publizierten MCP-Pfad nicht ausführbar. | P1 / H | `backend/mcp_server/tools/interview.py:181-202,408-427`; `backend/application/interview_service.py:900-949,1149-1169`; `R03:278-314`; REST/MCP-Paritätstest offen |
| CR-06 | F-04, AB-006 (S) | Interview-Single-Formalize-Race und Chat-Turn-Atomizität sind **zwei** Defekte: fehlende Initial-Lock/Idempotenz sowie getrennte Einzeltransaktionen/LLM-Grenze. | P1 / H (Race), P2 (Atomizität) | `backend/application/interview_service.py:448-492,900-1147,1680-1747`; `R02:442-484`; `R01:305-340`; Zwei-Request-/Fehlerpfadtest offen |
| CR-07 | WF-004 (—) | Interview-Formalize/Abandon umgehen WorkflowFacade und verschlucken Engine-Fehler; Audit-/Outbox-Seam kann fehlen. | P1 / H | `backend/application/interview_service.py:1092-1129,1250-1268,1316-1349`; `backend/application/workflow_facade.py:124-155`; `R04:240-282`; Fehlerinjektionstest offen |
| CR-08 | WF-001 (—) | Öffentliche Transition validiert vor dem Lock; `select_for_update()` schützt Zeile, nicht die vorherige fachliche Entscheidung. | P1 / H | `backend/workflow/services.py:273-327`; `backend/workflow/lifecycle_manager.py:295-341`; `R04:111-152`; Zwei-Request-Test offen |
| CR-09 | WF-002 (—) | Global-Definition-Mutationen schreiben global zuerst, propagieren nicht atomar und schützen Live-Items/Orphans nicht ausreichend. | P1 / H | `backend/workflow/global_definition_store.py:126-317`; `backend/rest_api/global_default_views.py:233-449`; `R04:154-197`; Fault-Injection/Orphan-Test offen |
| CR-10 | WF-003 (—) | Provisioning behauptet Backfill, repariert bestehende Legacy-Workspaces aber nicht. | P2 / H | `backend/workflow/management/commands/provision_workflow_definitions.py:10-100`; `R04:199-238`; `docs/REQUIREMENTS.md:237`; Vorher/Nachher-Fixture offen |
| CR-11 | CD-001 (—) | Fehler-`details` kann Objekt oder Array sein; OpenAPI und Frontend verlangen Array. | P2 / H | `backend/rest_api/error_envelope.py:18-37`; `backend/rest_api/openapi.py:43-64`; `frontend/src/types/index.ts:699-709`; `R03:117-152`; Contract-Test offen |
| CR-12 | CD-002 (—) | Generiertes OpenAPI bildet Interview-/TestRun-Actions falsch oder ohne Body/Fehler-/Result-Schema ab. | P1 / H | `R03:154-196`; `backend/rest_api/openapi.py:68-98`; `backend/rest_api/views.py:7467-7565`; Schema-Snapshot-Gate offen |
| CR-13 | CD-003 (—) | Workspace-Sprache ist zwischen `preset.language` und ORM-Spalte aufgespalten; Adapter lesen unterschiedliche Quellen. | P1 / H | `backend/persistence/models.py:719-760`; `backend/application/workspace_service.py:171-177,639-748`; `backend/rest_api/views.py:4895-4932`; `R03:198-236`; Cross-Adapter-Test offen |
| CR-14 | CD-006 (—) | TraceLink-OpenAPI verspricht Detail-GET/PATCH, Runtime liefert 404/405; ID-Echo ist UI-spezifisch. | P2 / H | `backend/rest_api/views.py:3024-3165`; `R03:316-349`; Schema/Runtime-Paritätstest offen |
| CR-15 | TR-001, TR-002 (S) | TraceLink-Update/Batch umgehen Workspace-Katalog; Single-/Batch-Zyklusvertrag ist linktyp-/global uneinheitlich. Keine Reduktion auf einen CRUD-Bug. | P2 / H | `backend/traceability/trace_link_manager.py:463-583`; `backend/application/trace_link_service.py:273-347`; `R04:284-364`; Cross-Type-/Catalog-Test offen |
| CR-16 | TR-003, AB-012 (S) | VCRM akzeptiert `baseline_id`, lehnt Snapshot-Abdeckung aber ab; DiffEngine verschluckt Store-/RLS-Fehler. Zwei getrennte Vertragslücken mit gemeinsamer Baseline-Evidenzproblematik. | P2 / H | `backend/traceability/coverage_calculator.py:216-262`; `backend/baseline/diff_engine.py:109-177`; `R01:528-561`; `R04:366-406`; Failure-/Snapshot-Test offen |
| CR-17 | AB-007, SR-014 (S) | Plain Operational Models und Baseline-Delta-Kindmodell haben keine eigene RLS; aktuelle Service-Pre-Checks sind vorhanden, Datenbank-Defense-in-Depth fehlt. | P2 / H | `backend/baseline/models.py:116-187`; `backend/application/models.py:44-182`; `R01:342-377`; `R05:692-733`; App-Role-Cross-Tenant-Test offen |
| CR-18 | AB-004, SR-013 (D) | Webhook-HTTP/Retry läuft synchron im Outbox-Poller und kann Worker-/Claim-Grenzen überschreiten; externe Zustellung ist nicht atomar vom Event-Erfolg getrennt. | P2 / H | `backend/application/event_bus.py:232-275,458-557`; `backend/application/webhook_dispatcher.py:201-301`; `R01:232-267`; `R05:651-690`; langsamer Endpunkt/Worker-Kill offen |

### 4.2 Security-, Integrations- und Betriebsgrenzen

| Kanonische ID | Quellbefunde | Konsolidierte Aussage / Disposition | Prio / Konfidenz | Beleg und nächste Evidenz |
|---|---|---|---|---|
| CR-19 | AB-005, AB-008, SR-007 (D/S) | Outbound-URL-Policy ist nicht zentral für Webhook, Memory/Honcho, Ollama und Provider-Ausführung; Endpunkte/Privilegien bleiben getrennt zu testen. | P2 / H (Kontrolllücke), E-Ausnutzbarkeit offen | `backend/llm_adapter/url_guard.py:149-197`; `backend/memory/memory_rest.py:176-227`; `backend/application/webhook_dispatcher.py:303-338`; `R01:269-303,379-415`; `R05:388-430`; Redirect-/DNS-Rebinding-Test offen |
| CR-20 | SR-008 (—) | LLM-Budget ist optional und wird von Read-only-/Memory-/Health-Pfaden umgangen; `context.change_impact` kann Kosten erzeugen. | P1 / H | `backend/mcp_server/tools/cross_cutting.py:132-179`; `backend/reqogniloom/settings.py:747-753`; `R05:432-481`; Quota-/Provider-Test offen |
| CR-21 | AB-010, F-06, F-09, F-13 (D) | MCP-Dokumentation, Agent-Prompts, Root-Kontext, Quickstart und Version driften; Manifest ist einzige aktuelle Toolquelle. Stdio bleibt nicht geroutet. | P2 / H für Drift, O für Laufzeit | `docs/agent-templates/tool-manifest.json:2-4`; `backend/mcp_server/urls.py:18-25`; `backend/mcp_server/views.py:405-431`; `README.md:1050-1073,1154-1188`; `R01:454-488`; `R02:533-715,854-892`; generierter CI-Smoke offen |
| CR-22 | F-03, F-08, F-11 (S) | Plugin-Header sind dekorativ; HTTP/SSE-Batchverträge und Hermes-Timeouts divergieren. Header sind keine Scope-Quelle. | P2 / H | `.agent-meta/config/plugin-catalog.yaml:273-286`; `backend/mcp_server/views.py:176-190,281-304,480-612`; `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts:52-70`; `R02:398-440,628-667,765-805`; Client-Contract-Test offen |
| CR-23 | F-10 (—) | Plugin-Allow/Blocklisten sind Prompt-Governance, keine serverseitige Security Boundary; Providerkonfigurationen divergieren. | P2 / H | `.agent-meta/config/plugin-catalog.yaml:243-261`; `.agent-meta/scripts/lib/mcp_provider_config.py:152-175`; `R02:718-762`; Provider-Snapshot-/Adversarial-Test offen |
| CR-24 | F-12, DEP-006 (D) | Hermes-TS und Python-Agent-Plugin sind parallele, nicht live verifizierte Verträge; CI priorisiert nur TS. | P2 / H Governance, E Hostvertrag | `integrations/hermes-plugin/reqogniloom/src/hermes-sdk-types.ts:2-19`; `integrations/hermes-agent-plugin/README.md:7-23`; `.github/workflows/ci.yml:284-319`; `R02:808-851`; `R10:162-173`; Supported-Surface-Matrix offen |
| CR-25 | F-05, DEP-007 (S/C) | Bluepencil ist standardmäßig deaktiviertes Debug/QS-Profil; bei Aktivierung fehlen AuthN/Tenant-Isolation und die Browser-/Sidecar-Versionen sind nicht integrity-gebunden. Security- und Asset-Provenienz sind getrennte Subbefunde. | bedingt P1 aktiviert / P2 Default, H | `deploy/bluepencil/README.md:1-20,178-195`; `deploy/bluepencil/server.js:1678-1746`; `frontend/src/bluepencil/loader.ts:277-305`; `R02:488-529`; `R05:915-916`; `R10:175-186`; Expositions-/Hash-Test offen |
| CR-26 | SR-001, SR-005, SR-018 (D/S) | Workspaceless Bearer verwendet stale Rollen/keine aktive User-Prüfung; Passwort-/Family-Revocation fehlt; handgebaute JWT-Implementierung ist P3-Kandidat, kein Bypass-Beweis. | P1 für Authorization, P2/P3 für Teilthemen / H | `backend/auth_tenancy/services/authentication.py:175-220`; `backend/auth_tenancy/rest.py:172-212`; `backend/auth_tenancy/jwt_tokens.py:9-127`; `R05:121-174,303-342,865-901`; Auth-/Fuzz-Test offen |
| CR-27 | SR-002, SR-003, SR-004 (S) | Body-Token-Default, fehlendes MFA und uneinheitliche Passwortvalidierung sind drei Auth-Policy-Lücken; nicht zu einem einzelnen Bypass verschmelzen. | P2 / H bzw. Policy | `backend/rest_api/auth_views.py:180-247`; `backend/auth_tenancy/services/user_account.py:94-113`; `backend/reqogniloom/settings.py:367-372`; `R05:176-302`; Auth-Matrix-Test offen |
| CR-28 | SR-009 (—) | MCP-Session-ID ist ein URL-Bearer-Credential mit acht Stunden TTL; URL-/Log-Exposition ist eigenes Risiko. | P2 / H | `backend/mcp_server/views.py:788-801`; `backend/mcp_server/sse_pubsub.py:13-23,74-131`; `R05:483-526`; Header-/Proxy-Log-Test offen |
| CR-29 | SR-010, SR-011, SR-012, F-07, PERF-003 (D/S) | Workerzahl ist begrenzt, Queue-/SSE-/Throttle-/Provider-Arbeit nicht; Health-/Upload-/LLM-Ressourcen können teuer werden. `R07:28` darf nicht als bounded work gelesen werden. | P2 / H Mechanik, O Auswirkung | `backend/mcp_server/views.py:148-156,579-612`; `backend/reqogniloom/health.py:73-225`; `backend/rest_api/views.py:7808-8079`; `R02:582-624`; `R05:528-649`; `R07:442-451`; Last-/Backpressure-Test offen |

### 4.3 Test-, Release- und Supply-Chain-Gates

| Kanonische ID | Quellbefunde | Konsolidierte Aussage / Disposition | Prio / Konfidenz | Beleg und nächste Evidenz |
|---|---|---|---|---|
| CR-30 | CI-001, CI-002 (S) | Backend-CI lässt 463 Testdefinitionen aus; Live-MCP-/Redis-Integrationstests werden explizit übersprungen. Kein vollständiger CI-Scope. | P1 / H | `.github/workflows/ci.yml:41-55,118-153`; `backend/mcp_server/tests/test_mcp_api_key_roles.py:71-90`; `R07:74-118`; Collection-/Integrationslauf offen |
| CR-31 | E2E-001, E2E-002, E2E-003 (S) | E2E testet WSGI/Vite statt ASGI/nginx, skippt Core-Contract-Fehler und `test:e2e:api` zielt auf fehlendes Verzeichnis. | P1 für Laufzeitparität, P2 Tooling / H | `.github/workflows/playwright.yml:143-212`; `e2e/tests/hermes-bugfix-campaign.spec.ts:667-687`; `e2e/tests/api-completeness.spec.ts:269-287`; `e2e/package.json:4-10`; `R07:120-164,396-417`; authentifizierter SSE-Roundtrip offen |
| CR-32 | REL-001, DEP-003 (S) | Release-Pipeline erzwingt kein sichtbares Test-vor-Image-Gate; Scan, Push, SBOM und Signatur sind nicht digestgebunden. | P1 / H | `.github/workflows/docker-publish.yml:98-112,142-191`; `.woodpecker.yml:123-127`; `R07:166-187`; `R10:123-134`; absichtlich roter Test/Digest-Test offen |
| CR-33 | TEST-001 (—) | E2E-Fixtures hinterlassen Workspaces/API-Keys und erzeugen persistente Zustandsabhängigkeit. | P2 / H | `e2e/helpers/auth.ts:80-99,241-264`; `e2e/tests/visual-regression.spec.ts:47-73`; `R07:212-233`; wiederholter Lauf/Teardown offen |
| CR-34 | COV-001, TYPE-001 (D) | Kein quantitativer Backend-/Frontend-Coverage-Gate; Test-TypeScript und E2E haben keinen separaten Typecheck. | P2 / H | `backend/pyproject.toml:28-36`; `frontend/package.json:7-15,40-60`; `frontend/tsconfig.build.json:3-8`; `R07:235-279`; synthetischer Coverage-/Typecheck-Gate offen |
| CR-35 | PERF-001, PERF-002 (S) | SeMetrics-Gap-Berechnung ist als N+1-Hypothese und In-Process-Cache-Lock als Multi-Worker-Lücke getrennt zu messen. | P2 / H Mechanik, O Lastwirkung | `backend/se_metrics/aggregator.py:241-265`; `backend/se_metrics/cache.py:15-63`; `backend/Dockerfile:253-260`; `R07:281-325`; Query-/4-Prozess-Test offen |
| CR-36 | OPS-001 (—) | Kein vollständiger `makemigrations --check`-Gate über alle Apps. | P2 / H | `backend/persistence/tests/test_migrations_and_indexes.py:26-30`; `.github/workflows/ci.yml:118-153`; `R07:350-371`; vollständiger App-Gate offen |
| CR-37 | OPS-002, SR-015 (S) | Sidecar erzeugt `.sql.gz`, Restore-Skripte erwarten andere Quelle/Dateiformat; Backups sind zusätzlich unverschlüsselt. Recovery und Vertraulichkeit sind zwei Schweregrade. | P1 für Recovery-Reproduzierbarkeit, P2 für At-rest / H | `deploy/docker-compose.yml:127-170`; `scripts/backup.sh:74-105`; `scripts/restore.sh:49,116,181-186`; `backend/admin_ops/services/backup_service.py:58-130`; `R05:735-774`; `R07:189-210`; isolierter Restore-Test offen |
| CR-38 | DEP-001, DEP-002, DEP-004, DEP-009, SR-017 (S) | Python-Lock stale/nicht installiert; Images/Actions/Scanner nicht digest-/SHA-/Hash-gebunden; VCS-Pin ist reproduzierbar referenziert, aber nicht release-geprüft. | P1 / H für Kontrolllücke, E/Einfluss | `backend/requirements.lock:1-28`; `backend/Dockerfile:29-51`; `frontend/Dockerfile:4,44-53`; `.github/workflows/ci.yml:15-20,98-153`; `R05:824-864`; `R10:97-147,201-212`; Clean-Room-Doppelbuild offen |
| CR-39 | DEP-005, DEP-008, DEP-010, DEP-011, DEP-012 (S) | Tooling-/MCP-/E2E-/Agent-Meta-Abdeckung, Lizenz-/Notice-Matrix und Honcho-Version sind getrennte Supply-Chain-/Hygiene-Tracks; keine CVE-Aussage ableiten. | P2, DEP-011 P3 / H bzw. E | `R10:149-251`; `backend/requirements.txt:159-171`; `.github/dependabot.yml:3-33`; `R07:453-457`; SBOM-/Lizenz-/Registry-Lauf offen |

### 4.4 Frontend-, API- und SE-Konsistenz

| Kanonische ID | Quellbefunde | Konsolidierte Aussage / Disposition | Prio / Konfidenz | Beleg und nächste Evidenz |
|---|---|---|---|---|
| CR-40 | FEA-001, FEA-002, FEA-003, FEA-004, FEA-005, FEA-006, FEA-007 (S) | Sieben unabhängige P1-Barrieren: Skip-Link, Dirty-Guard, mobiler SplitView, Kontrast, `html.lang`, Sprecherrollen und Traceability-Degraded-State. Nicht zu einem Accessibility-Befund zusammenziehen; gemeinsames AA-Gate, getrennte Maßnahmen. | P1 / H statisch, O Screenreader | `R06:159-435`; `R06:759-779`; Browser-/Screenreader-Matrix offen |
| CR-41 | FEA-008, FEA-009, FEA-010, FEA-011, FEA-012, FEA-013, FEA-014, FEA-015, FEA-016 (S) | Neun P2/P3-Semantik-/Interaktionslücken; P3 bleibt lokale Hygiene. Keine erneute WCAG-Schwere ohne Nutzerfluss-/Screenreader-Nachweis. | P2/P3 / H bzw. M | `R06:437-695`; `R06:697-703`; fokussierte Browserprüfung offen |
| CR-42 | CD-007, CD-008, CD-009, CD-010 (D/S) | TestRun-Result-Shapes, ChangeRequest-UI-Scope, selektive Concurrency-Guards und Enum-/Request-Typen sind vier Vertrags-/Produktentscheidungen; nicht zu einem Frontend-Bug verschmelzen. | P2, CD-010 P3 / H bzw. M | `R03:351-477`; `backend/rest_api/views.py:7467-7565`; `frontend/src/types/index.ts:861-871`; UI-/Schema-Paritätstest offen |
| CR-43 | DOC-001 (—) | README-/CI-Testzahlen sind historische Marketing-/Kommentarwerte, keine Collection-Baseline. | P3 / H | `R07:419-440`; `README.md:1018-1020`; Collection-/`--list`-Artefakt offen |
| CR-44 | AB-009 (C) | Minimal-Compose ist eine bewusst gewählte capabilities-reduzierte Installation; Async-Aufgaben bleiben ohne Worker pending und Health signalisiert dies nicht. | P2 / H | `deploy/docker-compose.minimal.yml:3-12,154-159`; `R01:417-452`; `R05:915-916`; Capability-/Readiness-Test offen |
| CR-45 | SR-016 (—) | Nicht vertrauenswürdige GitHub-Actions-Expression wird direkt in Shell-Quelltext interpoliert; Runner-/Secret-Risiko ist direkt für `workflow_dispatch`-Input. | P1 / H | `.github/workflows/version-drift-check.yml:53-78`; `.github/workflows/docker-publish.yml:127-132`; `R05:776-823`; Metazeichen-Dispatch-Test offen |
| CR-46 | AB-003, AB-011 (S) | Single-Entry-Point-Ratchet erfasst nicht alle Mixins/`admin_ops`; zwei `DomainEventBus`-Begriffe bleiben semantisch parallel. Separate Boundary-/Naming-Lücken, gemeinsamer Governance-Root. | P2 / H | `backend/rest_api/mixins/workflow_transitions.py:100-112`; `backend/admin_ops/theme_rest.py:31-323`; `backend/audit/events.py:90-176`; `backend/application/event_bus.py:137-275`; `R01:196-230,490-526`; erweiterter Ratchet-/Wiring-Test offen |
| CR-47 | TR-004, SE-001, SE-002, SE-003, SE-004 (S/C) | Suspect-Propagation ist One-Hop/teilweise; Preconditions fail-open; ADR-/REQ-Taxonomy, Matrix-/Teststatus und formale Review-Evidenz widersprechen sich. Als ein SSOT-/SE-Evidence-Track steuern, aber je Teilproblem getrennt beheben. | P2 / H | `backend/application/trace_link_service.py:1326-1463`; `backend/workflow/precondition_rules.py:52-60,276-610`; `docs/se/traceability-matrix.md:1-19,582-606`; `docs/se/reviews/` (keine formale Ablage laut `R04:584-619`); `R04:408-619`; Generator-/Review-Gate offen |

## 5. Reachability- und Priorisierungsmatrix

| Reachability | Tracks | Bewertung |
|---|---|---|
| Aktiver Standardpfad, unmittelbar relevant | CR-03, CR-04, CR-05, CR-06, CR-07, CR-08, CR-09, CR-12, CR-13, CR-20, CR-26, CR-30, CR-31, CR-32, CR-38, CR-45 | vor erneuter externer Vertrags-/Produktfreigabe schließen oder datiertes Restrisiko mit Owner/Abbaufdatum akzeptieren |
| Aktiver Frontend-/AA-Pfad | CR-40, ggf. CR-41, CR-42 | keine belastbare WCAG-2.2-AA-Sign-off ohne Browser-/Screenreader-Nachweis |
| Aktivierung/Deployment abhängig | CR-01, CR-18, CR-19, CR-25, CR-29, CR-37, CR-44 | erst nach Capability-/Expositionsnachweis als P1; sonst P2 |
| Historische oder nicht unabhängig bestätigte Evidenz | CR-01 Runtime-Anteil, AB-002-Worker-Impact, externe Registry-/CVE-Behauptungen in CR-24/CR-38/CR-39 | nicht als aktueller Release-Fakt zitieren; O-Messung erforderlich |
| Prozess-/Nachweisdrift | CR-21, CR-36, CR-43, CR-46, CR-47 | Matrix, Reviews, Versionen und Tests müssen aus einem versionierten Vertrag stammen |

### Empfohlene Reihenfolge für die nächste Validierung

1. **Korrektheit/Security vor Erweiterung:** CR-03, CR-04, CR-05, CR-06, CR-07, CR-08, CR-09, CR-13, CR-20, CR-26.
2. **Transport/Betrieb vor externem Onboarding:** CR-01, CR-02, CR-18, CR-19, CR-28, CR-29, CR-44.
3. **Release-Nachweis:** CR-30, CR-31, CR-32, CR-36, CR-37, CR-38, CR-39, CR-45; jeweils mit commitgebundenem Artefakt.
4. **Vertrags-/SE-SSOT:** CR-11, CR-12, CR-14, CR-15, CR-16, CR-17, CR-21, CR-42, CR-46, CR-47.
5. **Frontend-AA und verbleibende P2/P3:** CR-40/CR-41 nach den obigen Kernpfaden; kein AA-Sign-off aus statischen Kontrastwerten allein.

## 6. Erforderliche Nachweise und offene Messungen

Die folgenden Messungen sind **offen**, nicht als ausgeführt zu dokumentieren:

1. **Revision:** alle kanonischen P1-Codepfade auf `e3df119e52c0cbcc18df02f708567207c0374826` nochmals gegenprüfen; `R01`–`R04` nicht ungeprüft auf HEAD übertragen.
2. **Compose:** mit maskierter Konfiguration prüfen, welcher Dienst DDL ausführt; frischen Development-Stack mit pending Migration starten und Restart-/Health-Status archivieren. Keine historische Restart-Logik als aktuellen Erfolg ausgeben.
3. **RLS:** ContextGraphProjector unter `SET ROLE reqogniloom_app` ohne `app.current_tenant`; zwei Tenants; direkter Kindquery auf `bl_delta_index_entry`; Ergebnis und DB-Policy protokollieren.
4. **Tenant/API-Key:** `comment.resolve` mit Editor nur in Workspace A und Kommentar in B; fenced/unfenced Keys; neuer UI-/REST-Key mit Scope/Fence/Expiry; Bestandskeys getrennt inventarisieren.
5. **Interview:** REST/MCP Single-/Multi-Parität, fehlendes Proposal, zwei parallele Formalize-Aufrufe, absichtlicher Fehler nach erstem Feld; History, Audit, Outbox und Status gemeinsam prüfen.
6. **Workflow:** zwei unabhängige DB-Verbindungen mit konkurrierenden Transitionen; Global-Propagation mit Fault Injection und Item in abgeleitetem Workspace; SE-/Review-Referenzen synchronisieren.
7. **API/OpenAPI:** Schema-Snapshot für `interviews`, `test-runs/results`, `bulk`, `tracelinks`; Status-/Schema-Parität gegen Views und Frontend-Typen.
8. **Security:** stale Bearer nach Deaktivierung/Rollenzugang, Refresh-Family, MFA, Provider-Budget, SSRF-Ziele inkl. Redirect/DNS-Wechsel, Session-ID-Redaction und Action-Metazeichen.
9. **Runtime/Load:** echter Uvicorn/ASGI- und nginx-SSE-Roundtrip mit authentifiziertem Key; Queue-/Thread-/SSE-Caps; Health-Flood; Upload-Grenzen; langsame Webhooks und Worker-Kill.
10. **Frontend:** `npm run lint`, fokussierte Vitest-Suite sowie Chromium/Keyboard/Axe und manuelle NVDA/JAWS/VoiceOver-Prüfung; 200-%-Reflow und Theme-Kontrast aller realen Paare.
11. **CI/Test:** `pytest --collect-only`, vollständige App-Migrationsprüfung, TypeScript-Test-/E2E-Typecheck, Coverage-Baseline und Absichtstest für Skip/Release-Gates.
12. **Supply Chain:** Clean-Room-Python-/Node-Auflösung, fest gepinnte Scanner, SBOM/Provenance, Image-Digest, Scan-/Push-Gleichheit und isolierter Backup-Restore. Externe CVE-/Vendor-Aussagen erst danach als verifiziert markieren.

## 7. DoD- und Prozesskonformance

| DoD-/Prozesspunkt | Ergebnis | Nachweis / Einschränkung |
|---|---|---|
| Task vollständig umgesetzt | **erfüllt für diesen Bericht** | Dieser Bericht enthält Reconciliation, Quellen-/Konfliktregeln, vollständiges Finding-Ledger, Reihenfolge und Abschlussblock. |
| Änderungsgrenze | **erfüllt** | Nur `docs/se/reports/deep_audit/system-audit-2026-09/11-consistency-review.md` wurde neu erstellt; bestehende untracked `.serena/memories/*` und Berichte blieben unverändert. |
| Branch-Guard | **erfüllt** | `feat/1031-bluepencil-host-bridge`; nicht `main`/`master`. |
| Conventional Commit | **nicht zu beurteilen / kein Commit beauftragt** | Bestehende Commits `docs: ...` sind konventionell; für diesen Bericht wurde kein Commit erzeugt. |
| REQ-Traceability | **nicht vollständig erfüllt** | `R04:92-105` referenziert einzelne REQs, aber die übrigen Quellbefunde und die korrigierten SSOT-/Matrix-Aussagen sind nicht in einem zentralen, ausführbaren REQ-Gate synchronisiert (`CR-47`). |
| Tests / Regression-Nachweis | **nicht erfüllt als Release-Gate** | Zielbericht selbst enthält keinen grünen Lauf; Quellen enthalten nur begrenzte, revokations- und umgebungsabhängige Teilevidenz. Kein einheitlicher HEAD-Baseline-Lauf. |
| Security-Audit | **teilweise erfüllt** | `R05` ist ein statischer Security-Audit; P1-Befunde und fehlender CVE-/Runtime-Nachweis bleiben offen. |
| CODEBASE_OVERVIEW | **nicht durch diesen Task geändert** | KeineCODEBASE_OVERVIEW-Aktualisierung beauftragt oder vorgenommen; daher kein Aktualitätsnachweis. |
| Code-Qualität | **nicht bewertet** | Bewusst außerhalb der Validator-Grenze; die kanonischen Tracks bewerten Konsistenz, Evidenz und Release-Eignung, nicht Maintainability. |

## 8. Schlussfolgerung

Die Berichte sind als **Audit-Trail** gut genug dokumentiert, um die wesentlichen Risiken zu priorisieren, aber noch nicht als konsistente, releasefähige Evidenzkette. Die größte Abweichung liegt nicht in der Existenz einzelner Findings, sondern in (a) gemischten Revisionsständen, (b) fehlender gemeinsamer Test-/Runtime-Baseline, (c) historischen Aussagen, die wie aktuelle Fakten gelesen werden können, und (d) nicht synchronisierten SSOT-/Traceability-Dokumenten.

Vor einer erneuten Produktfreigabe müssen mindestens die P1-Standardpfade und die commitgebundenen Release-Gates geschlossen oder mit expliziter, datierter Risikoentscheidung versehen werden. Eine Freigabe dieses **Prüfberichts** bedeutet nicht die Freigabe des geprüften Produkts.

## 9. Abschlussstatus

```text
STATUS: done
RESULT: Die zweite Konsistenzprüfung hat 109 Quellbefunde zu 47 kanonischen Tracks reconciled, den aktualisierten R04-Zählstand von 9 P2 übernommen, historische Runtime-/externe Aussagen von aktueller Evidenz getrennt und die offenen Release-Gates benannt. Der Bericht ist vollständig; der geprüfte Produktstand bleibt wegen ungeschlossener P1- und Nachweisrisiken nicht release-reif.
VERDICT: APPROVED_WITH_NOTES
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/11-consistency-review.md
NEXT: Release for merge (Prüfbericht); Produktfreigabe zurück an Developer/Test-/Security-Verantwortliche
```
