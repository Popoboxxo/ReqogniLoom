# Systemaudit 2026-09-02 (grob): UI-Design, Konzeption, Schnittstellen

Stand: main @ 927c169c (v1.8.0-beta.6). Statisches Audit der reinen Funktionalität.
Ausgeschlossen: Tests, Dokumentation, CI, Deployment.

## 0. Methodik und Grenzen

- Navigation über graphify (7103 Knoten, 1316 Communities) und ProjectAtlas (Index refreshed, 1448 Dateien).
- ProjectAtlas Health liefert 3767 Findings, praktisch alle "missing-purpose". Keine strukturellen Fehler, daher nicht verwertet.
- Docker-Daemon lief nicht. Kein Live-Rendering, keine Screenshots. UI-Befunde sind Code-Befunde.
- Zahlen sind grep-basiert und grob. Sie zeigen Größenordnungen, keine exakten Inventare.

Schweregrade: **H** = hoch (Konzeptbruch oder Client-relevant), **M** = mittel, **N** = niedrig, **+** = positiv.

---

## A. UI-Design

### A1 (H) Inline-Styles dominieren die Views

- 1015 `style={{ ... }}` in `frontend/src/components`, davon 46 mit rohen px- oder Farbwerten.
- Schwerpunkte: RequirementEditors 106, WorkspaceSettings 102, shared 96, SystemSettings 52, TestRuns 52, TraceabilityView 46.
- Sogar die Shell: `<main style={{ flex:1, padding:"1.5rem" ... }}>` in `NavigationShell.tsx:130`.
- Bruch der Konvention "CSS Custom Properties aus tokens.css, keine hardcodierten Größen". Theming und Responsive werden dadurch pro Stelle statt pro Klasse gepflegt.

### A2 (H) Roh-Farben außerhalb des Token-Systems

- 74 Vorkommen von Hex/rgb außerhalb `tokens.css`.
- `canvas/CanvasEditor.tsx` 17, `WorkflowEditor.module.css` 15, `DiagramGraphEditor.module.css` 12, `MetricsDashboard.tsx` 7, `RiskEditors/RiskForm.tsx` 3.
- Es gibt 5 Themes (dark, light, bauhaus, nordic, sepia). Canvas, Workflow-Editor, Graph-Editor und Metrics fallen aus jedem Nicht-Default-Theme heraus.
- Nebenbefund: `CanvasEditor.tsx:104` nutzt `'Inter'` als Node-Font, Rest des Systems IBM Plex. Inter wird nur dafür geladen (`index.tsx:23`).

### A3 (H) Responsive-Modell existiert nur als Token

- Tokens definieren `--bp-md: 768px` und `--bp-lg: 1024px` (`tokens.css:817`).
- Gesamtes Frontend hat 7 `@media`-Regeln: 3× 1024px, 1× 640px, 3× reduced-motion. Keine einzige auf 768px.
- Das Drei-Breakpoint-Modell des UI-Konzepts (Kap. 6.3) ist nicht umgesetzt. Die App ist faktisch Desktop-only.

### A4 (M) SplitView trägt zwei Verträge, der neue ist tot

- `SplitView.tsx` (771 Zeilen) bietet Legacy (`leftPanel/rightPanel`, drag) und Konzept (`list/detail/spine/ratio`).
- Alle 16 Aufrufer nutzen Legacy. Kein einziger nutzt den Konzept-Vertrag.
- Der Konzeptvertrag inklusive Spine-Slot ist ungenutzter Code. Die Spine wird stattdessen von jedem Editor selbst platziert.

### A5 (M) Trace-Spine nur in der Hälfte der Artefakt-Views

- Spine vorhanden: Adr, Architecture, Goals, Issue, Needs, Requirement, Risk, TestCase (8).
- Spine fehlt: Icd, Diagram, Glossary, Baselines, TestRuns, Interview, Reviews, Traceability (8).
- Verletzt Prinzip 3.1 "Ein Artefakt sieht überall gleich aus". Das Signaturelement ist kein Systemelement, sondern ein Feature einzelner Editoren.

### A6 (M) Kein einheitliches Feedback-System

- Shared `Toast` wird in genau 2 Komponenten benutzt (DiagramGraphEditor, SystemSettings).
- 105 inline `role="alert"`, 47 `role="status"`. Jede View baut eigene Fehler- und Erfolgsbanner.
- Folge: gleiche Aktion (Speichern, Löschen, Server-Reject) sieht in jeder View anders aus.

### A7 (M) Auswahl nicht URL-adressierbar in 5 Views

- TestRuns, BaselinesView, Reviews, Goals, GlossaryView: kein `useParams`, kein `useSearchParams`, keine `:id`-Route.
- Auswahl lebt nur im React-State. Reload oder Link-Teilen verliert den Kontext.
- Widerspricht dem Leitgedanken "den Weg sichtbar halten" und dem Prinzip "der Rahmen bewegt sich nicht".

### A8 (N) Administrations-IA fragmentiert

- 5 Einstellungsflächen: `/settings`, `/system-settings`, `/user-management`, `/profile`, `/workflows`; dazu `/prompts` als Redirect auf `/settings?tab=llm`.
- Drei Rollenkonzepte gaten diese Seiten unterschiedlich (Workspace-Admin, Tenant-Admin, eigener User), jeweils client-seitig in der Page.

### A9 (N) Native `confirm()` verblieben

- `GlossaryView.tsx:197` nutzt `confirm(...)`, obwohl `ConfirmDialog` in 15 Views etabliert ist.

### A10 (N) `html lang` folgt nicht dem Sprachwechsel

- `i18n/index.ts` setzt nur die Initialsprache aus `navigator.language`. Kein `languageChanged`-Handler setzt `document.documentElement.lang`.
- Screenreader sprechen DE-Inhalte mit EN-Stimme oder umgekehrt.

### A11 (+) Positiv

- Token-System zweischichtig sauber: 0 Rohwerte in `--color-*`, alle über `--palette-*`.
- Shared-Komponenten breit adoptiert: PageHeader 25 Views, ListToolbar 17, EmptyState 15, ConfirmDialog 15, ArtifactInspector mit 12 Kinds.
- 1353 `data-testid`, 174 `aria-label`, `focus-visible` in global.css, reduced-motion beachtet.
- i18n vollständig paritätisch: 1693 Keys DE = 1693 Keys EN, 0 fehlende.
- Navigation: 26 Items in 5 Gruppen, Lazy-Routes, Legacy-Redirects für alte Pfade.

---

## B. Konzeption

### B1 (H) Drei Status-Achsen auf einem Artefakt

- `Requirement.status` (`persistence/models.py:964`, default "draft"), `Requirement.lifecycle_status` (`:1005`, outdated/active) und Workflow `current_state` (`workflow/models.py:211`, `persistence/models.py:1521`).
- `Goal.status` und `MainGoal.status` in `application/models.py:486/531` haben default `"Entwurf"`, deutscher String als Domänenwert. Persistence nutzt `"draft"`.
- Das UI-Prinzip "Farbe gehört dem Zustand" hat keinen eindeutigen Zustand, dem sie gehören kann. Badge-Variant-Tabelle muss drei Achsen und zwei Sprachen mappen.

### B2 (H) Zwei Persistenzmodelle und ein Layer-Verstoß

- Generisches `persistence.Artifact` (artifact_type, custom_fields) plus spezialisierte Tabellen in `persistence` (Requirement, StakeholderNeed, ArchitectureElement, TestCase, GlossaryTerm).
- Zusätzlich `application/models.py`: Adr, Risk, Goal, MainGoal, Issue, ChangeRequest als plain `models.Model`, nicht `TenantScopedModel`. Tenant nur indirekt über `artifact` FK (ChangeRequest über `baseline`).
- Layer 2 (application) hält damit Layer-0-Modelle. Row-Level-Isolation (ADR-03) greift für diese Entitäten nicht am Manager, sondern nur über den Join.
- Diagram und Icd sind weitere eigene Apps mit eigenen Version-Tabellen. Insgesamt vier Orte für "Artefakt".

### B3 (M) ChangeRequest existiert nur in der API

- REST `ChangeRequestViewSet` (Route `change-requests`, Action `transition`) und MCP `change_request.*` vorhanden.
- Frontend: 0 Treffer für `change-requests` oder `changeRequest`. Kein Api-Modul, keine Route, kein Editor.
- Entweder UI nachziehen oder den Endpoint explizit als API-only deklarieren.

### B4 (M) Trace-Link-Typen driften

- Backend `traceability/types.py`: 15 Link-Typen (inkl. `diagram-ref`).
- Frontend `types/index.ts:265-278`: 14 Typen. `diagram-ref` fehlt in der Union.
- FE kann diesen Typ weder anzeigen noch filtern noch anlegen.

### B5 (M) Sichtbarkeit über drei unabhängige Mechanismen

- `SidebarNavigation.tsx`: `feature`-Key gegen PRESET_VISIBILITY. 9 von 26 Items tragen `feature: "dashboard"` als "nicht gefiltert"-Hack.
- Goals zusätzlich über `activeWorkspace.goals_enabled`, Reviews über `approver_ui`, Admin-Seiten über Rollenprüfung in der Page.
- Kein gemeinsames Regelmodell. Neue Views raten, welchen Mechanismus sie nehmen.

### B6 (M) Zwei Versionierungskonzepte

- Audit-basiert (`versions` + `diff` Actions): Need, Requirement, Architecture, TestCase, Adr, Risk, Issue, Glossary.
- Eigene Version-Tabellen: `DiagramVersion`, `IcdVersion`, `GlossaryTermVersion` (Glossary hat beides).
- Lücken: Goal nur `versions` ohne `diff`, MainGoal nur `versions`, ChangeRequest nur `transition`, Baseline nur `diff`.
- ArtifactDiff im FE muss beide Welten bedienen.

### B7 (M) KI-Aktionen ohne gemeinsames Genehmigungsmodell

- Decompose: Vorschlag, dann `decompose/commit`. Suggest-Links: direkt. Interview: `propose` dann `formalize`. MainGoal: `generate` dann `approve`. Audit: `remediate`.
- Vier Semantiken für "KI schlägt vor, Mensch bestätigt". Kein einheitlicher Proposal-Typ, keine gemeinsame UI-Fläche.
- Memory-Konfiguration liegt in drei REST-Familien (`memory/me`, `system/memory*`, `workspaces/<id>/memory-settings`).

### B8 (N) Workflow-Konfiguration dreistufig

- `workflow-defaults` (global, item_type × preset), Workspace-Workflows, `permission-defaults` mit Enforcement-Flip und Mismatch-Report.
- Konsistent modelliert, aber hohe Einstiegshürde. Nur Hinweis, kein Defekt.

### B9 (+) Positiv

- Single-Entry-Point (ADR-01) wird eingehalten: 0 `.objects.` in `rest_api/*.py`, nur 2 Dateien importieren persistence-Modelle.
- Tenancy-Middleware ist registriert (`settings.py:261`). MCP-RBAC ist fail-closed (`_is_write_tool`, jedes unbekannte Tool gilt als Write).
- Soft-Delete-Pattern (outdate/reactivate) konsistent über REST und MCP.

---

## C. Schnittstellen

### C1 (H) OpenAPI-Schema für die Hälfte der API leer

- 46 `APIView`-Klassen, 43 ohne `serializer_class` und ohne `extend_schema`.
- Betroffen: Login/Logout/Refresh/Me, alle Workflow-Defaults, Permission-Defaults, Prompt-Templates und -Variables, LLM-Settings, Review-Policy, Context-Graph, CSV/ReqIF Import/Export, Audit, Decompose.
- Nur 13 `extend_schema` insgesamt bei 74 Views. drf-spectacular generiert für diese Endpoints Request/Response ohne Typen.
- Folge: `frontend/src/types/index.ts` ist handgepflegt ohne Vertrag. Drift wie B4 ist die erwartbare Konsequenz.

### C2 (M) Fehlerformat nicht durchgängig

- Exception-Handler normalisiert auf `{"error": {"code","message","details"}}` (`error_envelope.py`).
- Handgeschriebene Responses daneben: 10× `{"code": ...}` auf Top-Level, 2× `{"message": ...}`, 2× `{"error": "<string>"}`, 1× `{"detail": ...}`.
- Clients müssen vier Formen parsen. FE `api/errors.ts` existiert, deckt aber nur den Envelope ab.

### C3 (M) Route-Dubletten ohne Deprecation

- `tracelinks` und `trace-links` registrieren denselben ViewSet (`urls.py:163/170`).
- `traceability/{impact,path,cycles}` und `tracelinks/{impact,path,cycles}` parallel. Das FE nutzt beide Familien.
- `needs` flach und `workspaces/<pk>/needs` nested; `baselines` flach, nested und per `include(baseline_urlpatterns)`.
- Keine Sunset-Header, keine Schema-Markierung als deprecated.

### C4 (M) Workspace-Adressierung in zwei Stilen

- 21× `query_params.get("workspace")` gegen 16× URL-nested `workspace_pk`.
- MCP nutzt durchgängig `workspace_id`-Parameter. Ein REST-Client muss pro Endpoint nachschlagen.

### C5 (M) MCP-Server ist ein Tools-only-Server auf altem Protokollstand

- `MCP_PROTOCOL_VERSION = "2024-11-05"` (`protocol_handler.py:45`). Aktueller Spec-Stand ist 2025-06-18.
- Implementierte Methoden: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`. Keine `resources/*`, keine `prompts/*`.
- `McpArtifactProvider` (artifact.get als Markdown) und das Prompt-Template-System wären natürliche Resources bzw. Prompts, laufen aber als Tools.
- HTTP-Transport: GET liefert nur ein Info-JSON, kein Streamable-HTTP. SSE-Transport folgt dem Legacy-Modell mit `session_id` als Query-Parameter. Kein `Mcp-Session-Id`-Header.

### C6 (M) MCP und REST nicht paritätisch

- 27 Tool-Gruppen registriert (CLAUDE.md nennt 30), rund 175 Tools inklusive GenericCrud.
- Nur REST: ICDs, Metrics, API-Keys, Attribute-Visibility, Workflow-Defaults, Permission-Defaults, CSV/ReqIF, Theme, Banners, LLM-Settings, Context-Graph-Settings.
- Nur MCP: `ai_derivation.*` (6 Tools), `events.dlq_*`, `context.*`, `tool.*`.
- Ein KI-Agent kann Schnittstellen (ICD) nicht lesen, obwohl das Produkt sie als Kernartefakt führt.

### C7 (N) Frontend-Client wird an 7 Stellen umgangen

- `client.ts` ist fetch-basiert (kein Axios, anders als CLAUDE.md sagt) mit Timeout, Single-Flight-Refresh, CSRF.
- Direkte `fetch("/api/v1/...")` in `export.ts:41/77`, `import.ts:119/180`, `requirementBundle.ts:109`, `workspaces.ts:87`. 6 von 7 setzen credentials/CSRF selbst, aber keiner erbt Timeout und 401-Refresh.
- Binär-Downloads rechtfertigen einen Sonderpfad, nicht sieben Kopien.

### C8 (N) Filterung handgestrickt

- 10 `ordering_fields/search_fields/filterset_fields` gegen 86 manuelle `query_params.get(...)` in `views.py`.
- Filter-Parameter tauchen dadurch nicht im Schema auf. `ListToolbar` im FE bietet Search/Filter/Sort, jede View mappt selbst.

### C9 (+) Positiv

- Auth-Design solide: httpOnly Refresh-Cookie, CSRF-Header, Single-Flight-Refresh, 401 und 403 getrennt behandelt, 7 Throttle-Scopes (user, anon, login, login_ip, refresh, mcp_key, mcp_ip).
- JSON-RPC-Fehlercodes vollständig (-32700 bis -32603 plus Server-Range -32000..-32007).
- Free-Text-Sanitization als ViewSet-Mixin, Pagination global (25), Exception-Envelope zentral.

---

## D. Konzept-Review: Abdeckung eines strukturierten SE-Ansatzes

Referenzrahmen: die 17 Prozesse der NASA SE Engine (NASA SE Handbook, Kap. 2), weil die Projekt-Agenten (`se-consultant`) denselben Rahmen nutzen. Skala 0 bis 4: 0 = nicht vorhanden, 1 = nur über generische Mittel (Trace-Link, Custom Field), 2 = Grundfunktion, 3 = solide mit Lücken, 4 = vollständig.

### D1 Bewertungsmatrix

| # | Prozess | Score | Was da ist | Was fehlt |
|---|---|---|---|---|
| 1 | Stakeholder Expectations | 3 | StakeholderNeed (Kategorie, MoSCoW, Versionen, derive-requirements), Goals/MainGoal (generate/approve), Interview-Engine | Keine Stakeholder-Entität (wer will was), kein ConOps/Use-Case als Artefakt, keine MOEs |
| 2 | Technical Requirements Definition | 3 | Requirement L1-L4 mit type, category, acceptance_criteria, verification_method, complexity, uid, suspect; LLM validate, consistency check, similar; ReqIF | Requirement hat kein rationale, source, owner, priority (MoSCoW nur auf Need). Qualitätsprüfung nur per LLM, keine deterministischen INCOSE-Regeln |
| 3 | Logical Decomposition | 2 | decompose-next-level, AI Architecture-Decompose mit Commit, Diagramme (Mermaid, Canvas, Node-Graph) | Kein Funktions-, Zustands- oder Aktivitätsmodell als Entität. Funktionale und physische Zerlegung nicht getrennt |
| 4 | Design Solution Definition | 3 | ArchitectureElement (5 Typen, parent, ASIL, make-or-buy), ADR mit supersede, Allocation, ICD | Keine Trade Studies, keine Alternativen-Bewertung, ArchitectureElement hat kein Level-Feld (Level-Progression-Regel wirkt nur auf Requirements) |
| 5 | Product Implementation | 1 | Link-Typ `implements` | Keine Kopplung an Code, Build oder Repos. Bewusst außerhalb des Produktscopes |
| 6 | Product Integration | 2 | ICD-Versionen, ContractValidator (Syntax + Breaking Change), IcdTraceabilityConnector | Kein Integrationsplan, keine Integrationsreihenfolge, keine Integrationstest-Ebene |
| 7 | Product Verification | 3 | TestCase (steps, test_type), TestRun 4-Phasen-Lifecycle mit Results, verification_method, VCRM-Report, CoverageCalculator, `verifies` | Keine Trennung Prozedur/Fall, Verifikationsstufe (Unit/Integration/System) nicht am TestCase, keine Verifikations-Matrix pro Level |
| 8 | Product Validation | 2 | Need zu Requirement über derives-from, Signature-Gates als Abnahme | Kein Validierungs-Testtyp gegen Needs, kein Kunden-Sign-off-Artefakt, Coverage nur Requirement-zentriert |
| 9 | Product Transition | 0 | nichts | Release, Auslieferung, Übergabe nicht modelliert |
| 10 | Technical Planning | 0 | nichts | Keine Phasen, Meilensteine, Reviews (SRR/PDR/CDR) als Projektobjekte. Workflow-Gates sind pro Artefakt, nie pro Projekt |
| 11 | Requirements Management | 3 | versions/diff, suspect-Flag, Workflow-States, Baselines, Impact/Path/Cycles, Audit-Regeln, Volatility-Metrik | ChangeRequest nur API (B3), kein Requirement-Owner, kein Status-Report pro Level |
| 12 | Interface Management | 3 | ICD-App: Versionen, Parameter, Richtung, Typ, ContractValidator, similar, Timeline | Keine N²-Matrix, keine MCP-Tools (C6), keine ICD-Events im Outbox |
| 13 | Technical Risk Management | 3 | Risk mit probability, impact, detection, risk_score, severity, mitigation, owner, status | Kein Risiko-Verlauf/Burndown, keine Hazard-Analyse, Verknüpfung zu Requirements nur generisch |
| 14 | Configuration Management | 3 | Baselines 3 Scopes, Diff, VersionReconstructor, ChangeRequest an Baseline, Audit-Log, signature_seal | CR ohne UI, kein CCB-Workflow, keine Configuration-Item-Kennzeichnung, Diagram/ICD versionieren separat (B6) |
| 15 | Technical Data Management | 3 | Audit-Archiv, PDF/CSV/ReqIF, Requirement-Bundle-Export, Custom Fields, Glossar, Attribute-Visibility, Backup/Restore | Keine Dokumentgenerierung (Spezifikation als Dokument), kein SysML/XMI |
| 16 | Technical Assessment | 3 | se_metrics (Volatility, Coverage, Workflow-Gaps, Risk, Thresholds), Audit-Rule-Engine (5 Module: coverage, decomposition, level_progression, derivation/allocation, trace_p7), AI-Review, Reviews mit Signature-Gate (Passwort/TOTP), MetricsDashboard | Keine TPM/MOP-Verfolgung, keine Meilenstein-Reviews |
| 17 | Decision Analysis | 2 | ADR (create, supersede, versions, `decides`) | Keine Trade-Study, keine Kriterien-Gewichtung, keine Alternativen-Matrix |

Summe: 39 von 68 Punkten (57 %). Technical Management und System Design solide, Product Realization und Planning schwach.

### D2 Interpretation

- **Stärke:** Das System ist ein sehr gutes Requirements-, Traceability- und Konfigurationsmanagement-Werkzeug. Prozesse 11 bis 16 sind über dem Durchschnitt kommerzieller RM-Tools (Signature-Gates, Audit-Regeln, Baseline-Diff, VCRM).
- **Konzeptlücke 1, Funktionale Analyse:** Zwischen Requirement und ArchitectureElement fehlt die Funktionsebene. SE-Standard ist Need → Requirement → Funktion → physisches Element. Hier springt man von Requirement direkt auf Komponente. Diagramme sind Bilder, keine Modelle.

> **Was heißt "Funktionsebene"?** Ein System hat drei Fragen: Was muss es erfüllen (Requirement), was tut es (Funktion), woraus besteht es (Komponente). Die Funktion ist die Ebene dazwischen: "Druck messen", "Position berechnen", "Alarm auslösen". Sie hat Ein- und Ausgänge und wird einer oder mehreren Komponenten zugewiesen. Das ist der Kern von NASA "Logical Decomposition", ISO 15288 "Architecture Definition" und jedem SysML-Aktivitätsmodell. In ReqogniLoom kennt `ElementType` nur component, interface, subsystem, layer, module. Alles Struktur, nichts Verhalten. Folge: Ein Requirement wird direkt an eine Komponente gelinkt (`satisfies`). Wenn drei Komponenten zusammen eine Funktion erbringen, gibt es kein Artefakt dafür. Funktionsflüsse (was gibt A an B weiter) sind nur als ICD-Parameter darstellbar, nicht als Funktionskette. Die Diagramme (Mermaid, Canvas, Node-Graph) zeigen das zwar, aber die Kästchen sind keine Artefakte mit Trace-Links. Kleinster Schritt: `element_type = "function"` plus Link-Typ `performs` (Komponente → Funktion), `satisfies` dann Requirement → Funktion, und Node-Graph-Knoten dürfen auf Funktions-Artefakte zeigen (`KNOWN_ARTIFACT_ENTITY_TYPES` in `diagram/node_graph.py` erweitern).
- **Konzeptlücke 2, Projektzeitachse:** Es gibt keinen Begriff von Phase, Meilenstein oder Review-Event. Alles ist Artefakt-Zustand. Ein strukturierter SE-Ansatz braucht die Frage "Sind wir CDR-reif?" als Systemobjekt.
- **Konzeptlücke 3, Validierung:** Verification (gegen Requirements) ist gut, Validation (gegen Needs) ist nur eine Trace-Richtung. Kein Testtyp, keine Coverage, kein Abnahmeartefakt.
- **Konzeptlücke 4, Entscheidungen:** ADR dokumentiert Ergebnisse, nicht den Weg. Trade Studies fehlen komplett.
- **Konzeptlücke 5, Requirement-Attribute:** Kein rationale, source, owner, priority auf Requirement. Jede INCOSE-Checkliste fragt genau diese Felder ab. Custom Fields können das tragen, aber dann fehlt es in Regeln, Exporten und ReqIF-Mapping.
- **Konzeptlücke 6, Stakeholder:** Needs ohne Stakeholder. Wer hat das Bedürfnis, mit welchem Gewicht? Ohne diese Entität ist MoSCoW auf Need eine Einzelmeinung.

### D3 Empfehlung (Reihenfolge)

1. Requirement-Attribute rationale, source, owner, priority nativ, inklusive ReqIF-Mapping und Audit-Regel "Requirement ohne Rationale".
2. Stakeholder-Entität mit Link `expressed-by` von Need.
3. Validierungs-Testtyp und Need-Coverage im CoverageCalculator und VCRM.
4. Meilenstein/Review-Event als Workspace-Objekt, das Baseline plus Gate-Regeln plus Audit-Report bündelt.
5. Funktions-Entität (element_type "function" reicht als erster Schritt) mit Level-Feld auf ArchitectureElement.
6. Trade-Study als ADR-Erweiterung (Alternativen, Kriterien, Gewichte).

---

## E. Konzept-Review: Plugin- und Integrationsfähigkeit

### E1 Vorhandene Integrationsflächen

| Fläche | Zustand | Bewertung |
|---|---|---|
| MCP-Server | 27 Gruppen, ca. 175 Tools, API-Key-Auth, RBAC fail-closed, Throttling | Primäre KI-Fläche. Tools-only, Protokoll 2024-11-05, keine Resources/Prompts, kein Streamable HTTP (C5). Keine ICD-Tools (C6) |
| REST + OpenAPI | `/api/v1/`, 27 ViewSets + 46 APIViews, drf-spectacular | Schema für 43 APIViews leer (C1). Ein handgeschriebenes `docs/api/workflow-permissions-global-default.openapi.yaml` (46 KB) läuft parallel zum generierten Schema, Drift garantiert |
| Webhooks | 33 EventTypes, Outbox at-least-once, HMAC-SHA256 `X-Webhook-Signature`, Retry, DLQ mit Replay, Beat alle 5 s | Technisch reif. Aber: Subscriptions nur über Django-Admin. Kein REST, kein MCP, keine UI. Kein Event-Katalog (AsyncAPI). Keine Events für ICD, Diagram, Glossary, TestRun, Baseline-Update |
| Import/Export | CSV, ReqIF (Import + Export), PDF-Report, Requirement-Bundle | Solide. Kein SysML/XMI, kein Excel |
| LLM-Provider | 6 Provider (Mock, Anthropic, OpenAI, Ollama, Azure, OpencodeGo), `register_provider()` | Einzige echte Plugin-Schnittstelle im Backend |
| Hermes-Plugin (TS) | `integrations/hermes-plugin/`, 14 Dateien, letzte Änderung 2026-08-28 | Laut eigener README "sehr wahrscheinlich toter Code", gebaut gegen einen falschen SDK-Vertrag. Nutzt MCP `interview.*` |
| Hermes-Agent-Plugin (Py) | `integrations/hermes-agent-plugin/`, POC vom 2026-08-23 | "Not yet verified against a live Hermes install". Slash-Command plus Stats-Tab. Nur Interview-Flow, 10 Client-Funktionen, Konfiguration per Env-Var |
| Agent-seitig | `.claude/agents/reqogniloom-operator.md` | Rolle für Claude Code, keine wiederverwendbare Skill-Bibliothek |

### E2 Befunde

**E2.1 (H) API-Keys ohne Scopes und Ablauf.** `auth_tenancy/models.py:62`: Felder user, name, key_hash, revoked_at, last_used_at. Ein Plugin-Key hat alle Rechte seines Users, tenantweit, unbefristet. Kein read-only-Key, kein Workspace-Scope, kein Expiry. Für Drittintegrationen nicht vertretbar.

**E2.2 (H) Webhooks nicht self-service.** Die beste Integrationskomponente des Systems ist von außen unsichtbar. Ein Integrator braucht Django-Admin-Zugang, um eine Subscription anzulegen. Es gibt keinen Test-Delivery-Endpoint, keine Secret-Rotation, keine Delivery-Log-Ansicht.

**E2.3 (H) Zwei Hermes-Plugins, beide nicht live verifiziert, beide nur Interview.** Zwei Implementierungen für zwei verschiedene Hermes-Oberflächen (CLI/Gateway/Web-Dashboard vs. Desktop-App), beide POC. Kein Plugin deckt Requirements-CRUD, Traceability oder Reviews ab. Die README des Python-Plugins nennt das TS-Plugin "sehr wahrscheinlich toter Code". Das ist falsch, siehe H3: das TS-Plugin zielt auf das real existierende Desktop Plugin SDK.

**E2.4 (M) Kein Client-SDK.** FE (`client.ts`), Hermes-Py (`reqogniloom_client.py`), Hermes-TS (`api.ts` + `mcpClient.ts`) sind drei handgeschriebene Clients gegen dieselbe API. Ohne vollständiges OpenAPI (C1) kann kein Client generiert werden. Jede API-Änderung bricht drei Stellen.

**E2.5 (M) Kein Backend-Plugin-Modell.** Tool-Gruppen (`tool_registry.py:555ff`), Presets (`presets/registry.py`), Audit-Regeln (`traceability/audit/rules/`) sind hartverdrahtet. Kein Entry-Point, kein Registry-Hook. Nur LLM-Provider haben `register_provider()`. Wer eine eigene Audit-Regel oder ein MCP-Tool ergänzen will, forkt.

**E2.6 (M) Event-Katalog unvollständig und undokumentiert.** 33 EventTypes decken Requirement, Architecture, TestCase, ADR, Risk, Issue, CR, TraceLink, Need, Goal, Interview. Fehlen: ICD, Diagram, Glossary, TestRun, Review/Approval, User/Permission. Kein AsyncAPI-Dokument, Payload-Schema nur im Code.

**E2.7 (N) Handgeschriebene OpenAPI-Datei neben generiertem Schema.** `docs/api/workflow-permissions-global-default.openapi.yaml` beschreibt genau die Views, die im generierten Schema leer sind. Zwei Quellen, keine Prüfung.

**E2.8 (+) Positiv.** Outbox-Pattern mit Idempotenz-Guard, DLQ-Replay über MCP `events.dlq_replay`, HMAC-Signatur, Rate-Limits pro Key und IP, MCP-RBAC fail-closed. Die Substanz für ein Integrations-Ökosystem ist da, nur die Türen fehlen.

### E3 Was verbessert werden muss (Reihenfolge)

1. **API-Key-Scopes:** read/write, Workspace-Liste, Ablaufdatum, Anzeige "zuletzt genutzt" in der UI. Blockiert jede externe Freigabe.
2. **Webhook-Verwaltung als REST + UI + MCP:** CRUD, Test-Delivery, Secret-Rotation, Delivery-Log. Dazu Events für ICD, Diagram, Glossary, TestRun, Review.
3. **OpenAPI vollständig, dann generierter TS- und Python-Client.** Ersetzt drei handgeschriebene Clients. Handgeschriebene YAML löschen.
4. **MCP modernisieren:** Protokoll 2025-06-18, Streamable HTTP mit `Mcp-Session-Id`, `resources/*` für Artefakt-Markdown, `prompts/*` für Prompt-Templates, ICD-Tool-Gruppe.
5. **Hermes bereinigen:** TS-Plugin löschen, Python-POC gegen echte Hermes-Instanz verifizieren oder ebenfalls löschen. Erst dann Scope über Interview hinaus erweitern.
6. **Backend-Extension-Points:** Registry-Hooks für Audit-Regeln und MCP-Tool-Gruppen nach dem Muster von `register_provider()`. Kleinster Schritt: Python Entry-Points `reqogniloom.audit_rules` und `reqogniloom.mcp_tools`.

---

## H. Funktionsprüfung der Client-Integrationen (Claude Code, OpenCode, Hermes)

Methode: statischer Abgleich der Repo-Konfiguration und des MCP-Servers gegen die echten Client-Verträge. Geprüft wurden die Claude-Code-Doku (code.claude.com/docs/en/mcp), der OpenCode-Quelltext (`packages/opencode/src/mcp/index.ts`, `config/variable.ts`), das MCP TypeScript SDK (`packages/client/src/client/streamableHttp.ts`) und der Hermes-Quelltext (`hermes_cli/plugins.py`, `plugins/disk-cleanup`, `plugins/hermes-achievements`, `website/docs/developer-guide/desktop-plugin-sdk.md`). Kein Live-Handshake, Docker lief nicht.

### H1 Claude Code: Nein, aktuell nicht verdrahtet

| Punkt | Befund |
|---|---|
| Wo steht die Config | `.claude/settings.json` unter `mcpServers` (Typ `sse`, `${MCP_REQOGNILOOM_URL}/mcp/sse/`, Bearer plus X-Project-ID, X-User-ID, X-Workspace-ID) |
| Liest Claude Code das | **Nein.** Laut Doku kommen MCP-Server nur aus `.mcp.json`, `~/.claude.json` oder `claude mcp add`. `settings.json` kennt keinen `mcpServers`-Key |
| `.mcp.json` | Enthält nur repowise und projectatlas. ReqogniLoom fehlt |
| Skill | `use-lazy-rules.md` verweist auf `mcp-reqogniloom`. `.claude/skills/` ist leer |
| Custom-Header | X-Project-ID, X-User-ID, X-Workspace-ID werden serverseitig nirgends gelesen. Harmlos, aber Fiktion |

**Würde es nach Umzug in `.mcp.json` laufen?**

- **Typ `sse`:** Ja. Server implementiert das Legacy-SSE-Modell korrekt: GET mit API-Key-Auth am Handshake, `event: endpoint` mit `session_id` (`sse_pubsub.py:218`), POST auf `/mcp/messages/`. Transport ist bei Claude Code deprecated.
- **Typ `http` (empfohlen):** Tool-Calls ja. POST `/mcp/` liefert JSON, `notifications/initialized` bekommt 202, Protokollversion 2024-11-05 ist im SDK erlaubt, direkte Tool-Namen als Methode funktionieren (`protocol_handler.py:~508`). **Ein Defekt:** das SDK öffnet nach `initialize` einen GET auf `/mcp/` für den Server-Stream. Der Server antwortet 200 mit Info-JSON statt 405. Das SDK behandelt 200 als SSE-Stream, der sofort endet, und startet eine Reconnect-Schleife mit Backoff gegen den Discovery-Endpoint. Der ist per IP rate-limited, also folgen 429 und `onerror`. Tool-Calls funktionieren trotzdem, die Verbindung ist aber dauerhaft "unruhig". Fix: GET `/mcp/` bei `Accept: text/event-stream` mit 405 beantworten.
- **Nebenbefund:** `views.py` mappt JSON-RPC `PARSE_ERROR` und `INVALID_REQUEST` auf HTTP 401. Das ist ein 400.

### H2 OpenCode: Nein, Auth schlägt fehl

| Punkt | Befund |
|---|---|
| Config | `opencode.json` im Root (gitignored, lokal): `type: remote`, URL `http://172.20.5.120:8001/mcp/sse/`, Header `X-API-Key: {reqlo_…}` |
| Zweite Config | `.opencode/mcp.local.json` (Juli): Port 5173, Bearer, Extra-Header. Kein Dateiname, den OpenCode liest. Tot |
| Transport | OpenCode versucht erst StreamableHTTP (POST auf die URL), dann SSE. POST auf `/mcp/sse/` ergibt Django 405 (View hat nur GET). Fallback auf SSE greift, GET mit Headern kommt an |
| Auth | Der Header-Wert steht in geschweiften Klammern. OpenCodes Config-Loader ersetzt nur `{env:NAME}` und `{file:pfad}`, alles andere bleibt wörtlich. Der Server hasht also `{reqlo_…}` und findet keinen Key. **AUTH_FAILED** |
| Secret | Klartext-Key im Working Tree. Gitignored, aber unverschlüsselt |

**Fix:** Klammern entfernen oder `"X-API-Key": "{env:REQOGNILOOM_API_KEY}"`. Danach läuft es über den SSE-Fallback. Besser: URL auf `/mcp/` und den GET-Fix aus H1, dann StreamableHTTP ohne Umweg.

### H3 Hermes: Python-Plugin strukturell lauffähig, TS-Plugin nicht tot

**Python-Plugin (`integrations/hermes-agent-plugin/`)**, Abgleich gegen `hermes_cli/plugins.py`:

| Vertrag | Referenz (hermes-agent) | ReqogniLoom-Plugin | OK |
|---|---|---|---|
| Entry | `register(ctx)` per `getattr(module, "register")` | `def register(ctx)` | ja |
| Slash-Command | `ctx.register_command(name, handler=, description=)`, Handler `fn(raw_args: str) -> str \| None` | identisch | ja |
| Manifest | `plugin.yaml` mit name, version, description, author, hooks | identisch, `hooks: []` | ja |
| Import-Modus | `spec_from_file_location(..., submodule_search_locations=[plugin_dir])` | relativer Import `.reqogniloom_client` | ja |
| Installationsort | `~/.hermes/plugins/<name>/` | README: Symlink dorthin | ja |
| Dashboard | `dashboard/manifest.json` (name, label, description, icon, version, tab, entry, css, api) plus `plugin_api.py` mit `router = APIRouter()` plus `dist/index.js` über `window.__HERMES_PLUGIN_SDK__` | key-identisch mit hermes-achievements | ja |
| REST-Pfade | `/api/v1/interviews/…`, `/version/`, `/workspaces/` | existieren im Router | ja |

Verdict: **würde sehr wahrscheinlich laden und laufen.** Nie live getestet. Risiken: Default-URL Port 8001, Deploy bindet 127.0.0.1:8010, README sagt 8000. API-Key hat Vollzugriff (E2.1). Nur Interview-Flow.

**TS-Plugin (`integrations/hermes-plugin/reqogniloom/`)**, Abgleich gegen `desktop-plugin-sdk.md`:

| Vertrag | Referenz (Desktop SDK) | ReqogniLoom-Plugin | OK |
|---|---|---|---|
| Entry | Default-Export `{ id, name, register(ctx) }` | `activate.ts:59/90` | ja |
| Contribution | `ctx.register({ area: 'panes', title, render })`, `'statusBar.right'` | `activate.ts:60-72` | ja |
| Bundle | ein ESM-File, nur `@hermes/plugin-sdk`, `react`, `react/jsx-runtime` importierbar, kein JSX | Vite lib, `formats: ["es"]`, exakt diese externals | ja |
| Manifest | `manifest.json { name, api }` | eigenes `hermes-plugin.json` im VS-Code-Stil (contributes, activationEvents, engines) | **nein** |
| Installationspfad | Desktop-Plugin-Ordner laut Doku | unverifiziert | offen |

Verdict: **Kern-Vertrag stimmt, Manifest ist falsch, Installation ungeklärt.** Die README des Python-Plugins ("gebaut gegen einen falschen SDK-Vertrag, sehr wahrscheinlich tot") irrt: sie hat gegen CLI- und Dashboard-Plugins verglichen, das TS-Plugin ist ein Desktop-Plugin. Beide Plugins sind komplementär, nicht redundant.

### H4 Doku-Defekte, die Integrationen scheitern lassen

- README "Claude Desktop": `curl -N` als stdio-Bridge kann nicht funktionieren. stdio erwartet bidirektionales NDJSON, ein SSE-Stream ist einseitig. Claude Desktop schreibt Requests in curls stdin, die nirgends ankommen.
- README nennt `transports: ["http","sse","stdio"]`, Server liefert `["http","sse"]` (`views.py:398`).
- Vier Ports für dasselbe Backend: README 8000, Hermes-Default 8001, Deploy 8010 (loopback), OpenCode 5173 über Vite-Proxy.

### H5 Reihenfolge der Fixes

1. `.mcp.json`: ReqogniLoom als `type: http`, URL `${MCP_REQOGNILOOM_URL}/mcp/`, Bearer aus `${MCP_REQOGNILOOM_API_KEY}`. Block aus `settings.json` löschen. Eine Stunde.
2. GET `/mcp/` bei `Accept: text/event-stream` mit 405 beantworten. Fünf Zeilen.
3. `opencode.json`: Klammern raus, `{env:…}` rein, URL auf `/mcp/`. Fünf Minuten.
4. README-Abschnitt 9 neu schreiben: `.mcp.json`-Beispiel, Cursor mit `http`, Claude-Desktop-Beispiel löschen oder auf `mcp-remote` verweisen. Port vereinheitlichen.
5. Hermes: Live-Test gegen echte Instanz für beide Plugins. TS-Plugin: Desktop-Manifest ergänzen, `hermes-plugin.json` löschen. README-Fehlaussage korrigieren.

---

## I. Vorschläge für Tiefenanalysen

| # | Thema | Warum | Methode | Aufwand |
|---|---|---|---|---|
| 1 | Live-Integrationstest MCP | H1 bis H3 sind statisch. Ein echter Handshake mit Claude Code (http und sse), OpenCode, MCP Inspector und beiden Hermes-Plugins entscheidet endgültig | Docker hoch, `claude mcp add`, Inspector, Hermes-Instanz; Protokoll-Konformität mit `mcp-validator` | 1 Tag |
| 2 | Datenmodell-Konsolidierung | B1 (drei Status-Achsen), B2 (vier Orte für Artefakt), B6 (zwei Versionierungen). Jede weitere Entität verdoppelt die Kosten | Migrationsplan: eine Status-Achse plus Workflow-State, application-Modelle als TenantScopedModel, Versionierung vereinheitlichen. Mit `get_risk` und Co-Change-Analyse absichern | 3 bis 5 Tage Analyse |
| 3 | OpenAPI-Vertrag und Drift-Erkennung | C1, B4, E2.4. Ohne Schema kein Client, kein Contract-Test | Alle 43 APIViews mit Serializer oder `extend_schema`; dann generierter TS-Client gegen `types/index.ts` diffen; CI-Gate "Schema-Drift" | 2 bis 3 Tage |
| 4 | Security-Tiefenprüfung Integrationsflächen | E2.1 (Keys ohne Scope), B2 (Tenant-Isolation über Join), MCP Workspace-Narrowing, Webhook-Secrets, Rate-Limit-Bypass über SSE-Sessions | Threat Model pro Fläche, gezielte Tests mit fremdem Tenant, Key-Rotation-Szenarien | 2 Tage |
| 5 | UI-Live-Audit | Kap. A ist Code-Sicht. Kontrast, Fokus-Reihenfolge, Tastatur, Responsive und die fünf Themes wurden nicht gerendert | Playwright: Screenshots pro Route und Theme, axe-core, 768/1024/1440 px | 1 Tag |
| 6 | SE-Domänenmodell-Workshop | D2 Lücken 1 bis 6. Funktionsebene, Meilenstein-Objekt, Validation, Stakeholder, Requirement-Attribute | Konzeptpapier gegen NASA SE Handbook Kap. 4 und INCOSE Guide for Writing Requirements; Ergebnis als ADR plus Migrationspfad | 2 Tage |
| 7 | MCP-Kontextkosten | ca. 175 Tools in `tools/list`. Jeder Client lädt alle Schemata in den Kontext. Bei 27 Gruppen sind das geschätzt 30 bis 50k Tokens pro Session | Manifest-Größe messen (`export_tool_manifest`), Gruppen-Lazy-Loading oder Tool-Sets pro Rolle prüfen | 0,5 Tage |
| 8 | Performance und N+1 | Repowise meldet 97 offene I/O-in-Loop-Findings, `llm_adapter/providers.py` Health 1.0/10 | `get_health(include=["signals"])`, Django-Debug-Toolbar auf den 10 meistgenutzten Endpoints, Query-Zählung im Test | 1 bis 2 Tage |
| 9 | Frontend-Architektur-Schnitt | A1, A4, A6. 1015 Inline-Styles, toter SplitView-Vertrag, kein Feedback-System | Codemod-Plan Inline-Style zu CSS-Modul, Entscheidung SplitView-Vertrag, Toast als globaler Provider | 1 Tag Analyse |
| 10 | Webhook-Vollständigkeit | E2.2, E2.6. Fehlende Events, kein Self-Service | Event-Katalog als AsyncAPI, Lücken gegen alle Services, REST-CRUD-Entwurf | 1 Tag |

Empfohlene Reihenfolge: 1, 3, 4, 2, 6. Die restlichen nach Bedarf.

---

## L. Feature-Review: Interview-Engine

### L1 Bestand

| Schicht | Was da ist |
|---|---|
| Modell | `InterviewSession` (workspace, artifact, artifact_type, session_kind single/multi, status in_progress/completed/abandoned, target_artifact, collected_fields, grounding_snapshot, resulting_artifact_ids, transcript als JSON) plus `InterviewSessionArtifact` |
| Service | `interview_service.py` 1522 Zeilen: start, get_state, answer, grounding_context, set_target, formalize, abandon, generate_chat_turn, propose, provenance_session_id, list_sessions, get |
| Protokoll | `interview_protocol.py`: Phasen und Pflichtfelder pro Typ als YAML in Prompt-Template-Slots `interview.protocol.<Typ>`. Default: 2 Phasen (Titel plus Rationale erheben, dann zur Freigabe vorlegen). 8 In-Scope-Typen: Requirement, ArchitectureElement, StakeholderNeed, Risk, TestCase, Adr, Issue, Goal |
| LLM | Capabilities `interview.chat_turn` und `interview.grounding_rank` mit Mock-Fallback, Memory-Kontext wird in den Chat-Prompt injiziert |
| REST | 7 Actions: state, answer, grounding, formalize, propose, abandon, chat |
| MCP | 10 Tools `interview.*` |
| FE | Always-mounted `InterviewWidget` (188 Zeilen, Overlay auf jeder Route, REST) plus Seite `/interviews` mit Liste und Detail (1821 Zeilen gesamt). `ProposalPreviewGraph` für Multi-Artefakt-Vorschläge |
| Events | `InterviewChatTurn`, `InterviewFormalized` im Outbox, einzige Quelle für Memory-Konsolidierung |
| Plugins | Beide Hermes-Plugins bauen ausschließlich auf diesem Feature auf (H3) |

### L2 Befunde

**L2.1 (H) formalize erzeugt immer ein Requirement, egal welcher Typ interviewt wurde.** `interview_service.py:870-915`: der Single-Pfad holt `RequirementService`, liest `title` und `rationale` aus `collected_fields` und ruft `create_requirement` bzw. `update_requirement`. Kein Dispatch nach `session.artifact_type`. Es gibt in der Datei keinen Verweis auf RiskService, AdrService, StakeholderNeedService, TestService, GoalService, IssueService oder ArchitectureService. Ein Interview für einen Risk startet, sammelt Felder, und formalisiert zu einem Requirement. Die 8 In-Scope-Typen sind ein Versprechen ohne Einlösung.

**L2.2 (H) Default-Protokoll erhebt nur Titel und Rationale.** `_default_protocol_yaml` kennt zwei Phasen mit zwei Feldern. Für einen Risk fehlen probability, impact, mitigation; für einen TestCase steps; für eine Need category und MoSCoW. Ohne handgeschriebenes YAML pro Typ im Prompt-Template-Slot ist das Interview ein Titel-Generator.

**L2.3 (M) Provenienz ist unsichtbar.** `provenance_session_id()` existiert im Service, `InterviewProvenanceBadge` existiert in `shared/`, wird aber von keinem Editor importiert. Kein Artefakt zeigt, dass es aus einem Interview stammt.

**L2.4 (M) Transkript wächst unbegrenzt.** `interview_service.py:1271` hängt jeden Turn an `session.transcript` (JSONField) an. Kein Cap, keine Zusammenfassung. Jeder Chat-Turn lädt und schreibt das komplette Transkript und schickt es als Prompt-Kontext mit.

**L2.5 (M) Zwei UIs für ein Feature.** Widget (Overlay, chat-orientiert) und `/interviews`-Seite (Liste, Detail) teilen keine Komponenten außer der API. Der Detail-View hat 157 Zeilen, der Chat-Pane 206. Welche Fläche ist die primäre? Nutzer sehen zwei Einstiege mit unterschiedlichem Funktionsumfang.

**L2.6 (M) i18n-Abdeckung dünn.** 15 Keys unter `interviews.*` für zwei komplette UIs. Keine hart codierten Strings gefunden, die Texte kommen aus anderen Namespaces oder vom Server (Phase-Namen, Fragen). Server-Texte sind nicht lokalisiert.

**L2.7 (N) Interview für Icd, Diagram, Glossary, MainGoal nicht möglich.** Vier Artefakttypen sind außerhalb des Scopes, ohne dass die UI das erklärt.

**L2.8 (+) Positiv.** Sauberes Zustandsmodell, Grounding gegen bestehende Artefakte mit LLM-Ranking und Mock-Fallback, Multi-Artefakt-Vorschläge mit Graph-Vorschau, Write-Permission zentral vor dem Dispatch, MCP-Parität vollständig.

### L3 Fix-Vorschläge

1. **Typ-Dispatch in formalize.** Tabelle `artifact_type -> (Service, create_fn, field_mapping)` für alle 8 Typen. Fehlt der Eintrag, `ValidationError` statt stillem Requirement. Ein Regressionstest pro Typ.
2. **Typ-Protokolle aus dem Attribut-Schema ableiten** (siehe N4). Pflichtfelder pro Typ und Preset kommen aus derselben Quelle wie die Formulare. Dann braucht es kein YAML pro Typ mehr, nur Prompt-Fragmente.
3. **Provenienz anzeigen.** `InterviewProvenanceBadge` in PageHeader jedes Artefakt-Editors, Link zurück zur Session.
4. **Transkript deckeln.** Letzte N Turns plus laufende Zusammenfassung als eigenes Feld. Zusammenfassung ist ohnehin das, was die Memory-Konsolidierung braucht.
5. **Eine UI.** Widget als Chat-Fläche behalten, `/interviews` nur als Liste mit "im Widget öffnen". Detail-View streichen oder in den Widget-Pane ziehen.

---

## M. Feature-Review: Memory und Honcho

### M1 Bestand

| Schicht | Was da ist |
|---|---|
| Backends | `MemoryBackend`-Interface (upsert, query, list_recent, forget, health_check) mit `register_memory_backend()`. Zwei Implementierungen: `PgvectorMemoryBackend` (Default, eigene Postgres mit pgvector, Image `pgvector/pgvector:pg16`) und `HonchoMemoryBackend` (honcho-ai 2.3.0, Peer je User, Workspace je Tenant) |
| Modelle | `WorkspaceMemory`, `UserTenantMemory` (content, confidence, source_event_id, superseded_by), `WorkspaceMemorySettings` (enabled je Workspace), `SystemMemorySettings` (embedding_provider, model, ollama_base_url, timeout, memory_backend, honcho_base_url, honcho_api_key verschlüsselt) |
| Pipeline | `MemoryProjector` abonniert genau zwei Events (`InterviewChatTurn`, `InterviewFormalized`), Celery-Task `memory.consolidate_interaction` schreibt Einträge |
| Konsum | `build_memory_context()` nur in `interview_service.generate_chat_turn` und als Prompt-Variable `memory_context` in `ai_derivation_service` |
| REST | 9 Endpoints in 3 Familien: `workspaces/<id>/memory-settings/`, `system/memory-settings/` (+reset), `system/memory/workspaces|entries|projection`, `memory/me/` |
| MCP | `memory.query`, `memory.list`, `memory.forget` |
| FE | SystemSettings: 3 Sektionen (Management, System-Settings, Visualization). UserProfile: MemorySection. API-Module: memoryAdmin, memory-self-service, memory-settings, memory-visualization, system-memory-settings |
| Deploy | Compose-Profil `honcho` mit honcho-postgres, honcho-redis, honcho-migrate, honcho |

### M2 Befunde

**M2.1 (H) Memory ist ein Interview-Feature, kein Systemfeature.** Nur Interview-Events werden konsolidiert. Requirement-Validate, Decompose, Consistency-Check, Audit-AI-Review, Suggest-Links: keiner dieser LLM-Pfade schreibt oder liest Memory. Die 9 REST-Endpoints, 3 MCP-Tools, 4 FE-Sektionen und das Compose-Profil verwalten einen Speicher, den fast nichts füllt und fast nichts liest.

**M2.2 (M) Honcho-Backend ist funktional beschnitten.** Laut `.env.example:219-226` und `honcho_backend.py`: `forget` funktioniert nicht (MCP-Tool prüft Eigentum gegen pgvector-Tabellen, Honcho-IDs sind Nanoids), `source_event_id` geht verloren, Query liefert keinen Distanz-Score. Der Nutzer sieht in der Visualisierung bei Honcho leere Provenienz und kann Einträge nicht löschen. Das Backend ist damit nicht DSGVO-tauglich (kein Löschrecht).

**M2.3 (M) Zwei Konfigurationsorte für dasselbe.** `MEMORY_BACKEND`, `HONCHO_BASE_URL`, `HONCHO_API_KEY` in `.env` und parallel in `SystemMemorySettings` (DB, per REST editierbar). Welcher gewinnt, entscheidet `_resolve_memory_backend_name()`. Ein Admin, der in der UI umstellt, weiß nicht, ob die Env-Variable ihn überschreibt.

**M2.4 (M) Drei REST-Familien, keine Ordnung.** `workspaces/<id>/memory-settings/` (Workspace-Toggle), `system/memory-settings/` (Tenant-Config), `system/memory/...` (Admin-Sicht auf Daten), `memory/me/` (User-Sicht). Vier Präfixe für ein Subsystem. Gehört unter `memory/` mit Sub-Ressourcen.

**M2.5 (N) Keine Qualitätssicherung der Einträge.** `confidence` existiert, wird aber weder in der UI gefiltert noch beim Kontext-Aufbau als Schwelle genutzt (prüfen: `context_builder.py` 3.4 KB). Kein Ablauf, keine Superseding-Logik in der UI sichtbar.

**M2.6 (+) Positiv.** Sauberes Backend-Interface mit Registry, Tenant-Isolation über Peer- und Workspace-Mapping, verschlüsselter Key, Self-Service-Endpoint für den eigenen Speicher, Visualisierung (Entries, Projection) vorhanden, Celery-Entkopplung.

### M3 Fix-Vorschläge

1. **Memory an alle LLM-Pfade hängen.** Ein `MemoryAwareCapability`-Mixin im `llm_adapter`: vor dem Call `build_memory_context(scope=workspace, user)`, nach dem Call optional `consolidate`. Dann lohnt sich das Subsystem.
2. **Honcho: entweder vollständig oder weg.** `forget` über Honcho-API implementieren (Conclusions löschen), Distanz durch Rang-Position ersetzen, Provenienz als Metadata mitschreiben. Geht das mit honcho-ai 2.3.0 nicht, Backend als "experimentell, kein Löschrecht" markieren und aus der System-Settings-UI ausblenden.
3. **Eine Konfigurationsquelle.** Env nur als Bootstrap, DB gewinnt, UI zeigt "überschrieben durch Env" als Banner.
4. **REST unter `memory/` konsolidieren**: `memory/settings/` (system), `memory/workspaces/<id>/settings/`, `memory/entries/`, `memory/me/`. Alte Pfade als Redirect ein Release lang.
5. **Confidence-Schwelle und Ablauf** als Settings, Filter in Visualisierung, Anzeige "verdrängt durch" in der Liste.

---

## N. Feature-Review: Artefakt-Formulare und Attribut-Definitionen

### N1 Warum Anforderungen anders aussehen als Bedarfe oder ADRs

Sieben handgeschriebene Formulare, jedes mit eigener Struktur:

| Form | Zeilen | Sektionen | Selects | Inline-Styles | Visibility-Config | Dirty-Tracking | Delete im Form | Status-Feld | Create-Flow |
|---|---|---|---|---|---|---|---|---|---|
| RequirementForm | 1009 | 4 (Allgemein, Klassifikation, Custom Fields, Change Control) | 6 | 27 | nein | ja | nein | Select plus Transition-Buttons | inline CreateForm |
| NeedForm | 631 | 0 | 2 | 23 | **ja** (einziges Form) | ja | ja | Select | inline CreateForm in Liste |
| AdrForm | 486 | 0 | 1 | 15 | nein | nein | ja | read-only (#263) | Modal-Dialog |
| RiskForm | 543 | 0 | 4 | 22 | nein | nein | ja | keins | Modal-Dialog |
| IssueForm | 260 | 0 | ? | ? | nein | nein | ja | keins | Modal-Dialog |
| TestCaseForm | 291 | 0 | ? | ? | nein | ja | ja | keins | Modal-Dialog |
| ArchitectureForm | 652 | 0 | ? | ? | nein | ja | ja | keins | inline CreateForm |

Konkrete Unterschiede, die der Nutzer sieht:

- **Struktur:** Nur Requirement hat Sektionen mit Überschriften. Alle anderen sind eine flache Feldliste.
- **Anlegen:** Requirement, Need, Architecture inline im Split-View. ADR, Risk, Issue, TestCase in einem Modal. Zwei Interaktionsmodelle für dieselbe Aufgabe.
- **Löschen:** Bei Need, ADR, Risk, Issue, TestCase, Architecture im Formular. Bei Requirement nicht.
- **Status:** Requirement hat Select plus Workflow-Transition-Buttons. Need hat nur Select. ADR zeigt Status read-only. Risk, Issue, TestCase, Architecture zeigen im Formular nichts.
- **Ungespeicherte Änderungen:** Requirement, Need, TestCase, Architecture warnen. ADR, Risk, Issue nicht.
- **Feldhinweise:** `FieldHints` in Requirement und Architecture. Sonst nirgends.
- **Sichtbarkeitskonfiguration:** `AttributeVisibilityConfig` existiert (Admin-Dialog, tenant-global, visible + required pro Feld). Das Schema kennt nur Requirement (`attribute_visibility_service.py:48`). Konsumiert wird es aber nur von NeedForm. Das Requirement-Formular ignoriert seine eigene Konfiguration.
- **Custom Fields:** Backend kennt text, number, dropdown. FE `CustomFieldsEditor` kennt string, number, boolean. Dropdown wird im Editor nicht gerendert, boolean gibt es im Backend nicht.
- **Pflichtfelder:** Presets definieren `mandatory_fields` nur für Requirement und nur `("title",)`.
- **Labels:** Terminologie-Profile mappen nur Entitätsnamen (requirement, workspace, baseline), nie Attribute.

Ursache: Es gibt keine Attribut-Definition. Jedes Formular ist die Definition. Vier halbfertige Mechanismen (Visibility-Config, Custom Fields, Preset-Mandatory, Terminologie) berühren jeweils einen Aspekt, keiner deckt alle Typen ab.

### N2 Was es schon gibt und wiederverwendbar ist

| Baustein | Ort | Taugt als |
|---|---|---|
| Workflow-Defaults-Modell | `GlobalWorkflowDefinition(item_type, preset, workflow_json)` plus `WorkflowEngineDefinition(workspace, source_global, is_customized)` mit initialize und reset | **Blaupause** für Attribut-Definitionen: global × item_type × preset, Workspace-Override, Reset auf Global |
| Workflow-Editor UI | `WorkflowEditor/` mit EntityTypeSelector, PresetSegmentedControl, InspectorPanel | Shell für den Attribut-Editor, gleiche Navigation |
| AttributeVisibilityConfig | visible, required pro (entity_type, attribute_name), tenant-global | Wird zur Kern-Attribut-Schicht, bekommt preset und workspace |
| CustomFieldDefinition | name, field_type, is_required, options, order, pro Workspace | Wird zur Zusatz-Attribut-Schicht, bekommt global-Ebene |
| CustomFieldsEditor, ArtifactCustomFields | Rendering dynamischer Felder | Wird zum generischen Feld-Renderer |
| FieldHints | Hinweistexte | Wird Teil der Attribut-Definition (help_text) |
| describe_schema | Feldliste je Typ | Wird für alle Typen ausgebaut und zur Quelle für FE, Interview-Protokoll, ReqIF-Mapping, Bundle-Export |
| Terminologie-Profile | Entitäts-Labels | Erweitert um Attribut-Labels |

### N3 Zielbild: Attribut-Definition als Systemobjekt

Ein Objekt pro (item_type, preset), global, mit Workspace-Override, exakt wie Workflows.

```
AttributeDefinition
  item_type        Requirement | StakeholderNeed | ArchitectureElement | TestCase | Adr | Risk | Issue | Goal | Icd | GlossaryTerm
  preset           minimal | standard | extended
  scope            global | workspace(<id>)      (workspace erbt global, is_customized, reset)
  attributes[]     
    name           z.B. "verification_method"
    kind           core | extended                 (core = Model-Feld, extended = custom_fields JSON)
    type           text | textarea | number | boolean | enum | multi-enum | date | reference | user
    options        für enum: Werte plus Labels DE/EN
    required       bool
    visible        bool
    editable       bool | "workflow"               (workflow = nur über Transition änderbar, z.B. status)
    section        "general" | "classification" | "change_control" | <frei>
    order          int
    label          DE/EN Override, sonst i18n-Key
    help_text      DE/EN
    default        Wert
    validation     regex | min/max | length
    ai_elicit      bool                             (Interview fragt dieses Feld ab)
    export         bool                             (ReqIF/CSV/Bundle)
```

**Kern vs. Zusatz:** Kern-Attribute sind Model-Felder. Der Editor kann sie nicht löschen oder umtypen, nur required, visible, editable, section, order, label, help_text, default, options-Untermenge, ai_elicit, export setzen. Zusatz-Attribute sind frei definierbar und landen in `Artifact.custom_fields`. Beide erscheinen in derselben Liste, Kern mit Schloss-Symbol.

**Drei Ebenen:** Global (Tenant-Admin, Editor unter `/system-settings`), Workspace (Workspace-Admin, Override-Ansicht unter `/settings`, zeigt Abweichungen vom Global), Preset-Wechsel behält Workspace-Overrides, die im neuen Preset zulässig sind (Downgrade-Prüfung wie `validate_downgrade`).

**Ein Renderer:** `ArtifactForm` bekommt `item_type` plus Artefakt, holt die aufgelöste Definition (global → workspace → preset), rendert Sektionen und Felder aus einer Komponentenbibliothek (`TextField`, `TextArea`, `EnumSelect`, `MultiEnum`, `BooleanToggle`, `DateField`, `ReferencePicker`, `UserPicker`), hängt Custom Fields in die Sektion, die die Definition nennt. Status wird als `editable: "workflow"` gerendert: Badge plus Transition-Buttons, überall gleich. Delete, Dirty-Warnung, Cancel, Create-Modal: einmal im Renderer, nicht siebenmal.

**Eine Quelle für vier Konsumenten:** Formulare, Interview-Protokoll (`ai_elicit`), ReqIF- und Bundle-Export (`export`), Serializer-Validierung (`required`, `validation`). Backend prüft required und validation serverseitig gegen dieselbe Definition.

### N4 Umsetzungsschritte

1. **Backend, Schema:** `describe_schema` für alle 10 Typen aus den Django-Feldern generieren (Name, Typ, Choices, Model-required). Das ist die Kern-Liste. Ein Tag.
2. **Backend, Modell:** `GlobalAttributeDefinition(item_type, preset, definition_json)` und `WorkspaceAttributeDefinition(workspace, source_global, is_customized, definition_json)` nach Vorbild Workflow. Migration: bestehende `AttributeVisibilityConfig` und `CustomFieldDefinition` hineinfalten. REST wie `workflow-defaults/` plus `workspaces/<id>/attribute-definition/` mit reset. Serializer-Validierung liest required und validation daraus. Zwei bis drei Tage.
3. **FE, Renderer:** `shared/ArtifactForm/` mit Feld-Komponentenbibliothek. Zuerst Risk und Issue umstellen (kleinste Formulare, kein Workflow-Sonderfall), dann ADR, TestCase, Need, Architecture, zuletzt Requirement. Jedes umgestellte Formular löscht sein handgeschriebenes Pendant. Fünf bis acht Tage.
4. **FE, Editor:** `AttributeEditorPage` unter `/system-settings` und `/settings`, Shell aus dem Workflow-Editor (EntityTypeSelector, PresetSegmentedControl, InspectorPanel), Liste statt Canvas: Sektionen als Gruppen, Attribute als Zeilen mit Drag-Order, Inspector für die Eigenschaften. Drei bis vier Tage.
5. **Konsumenten umhängen:** Interview-Protokoll aus `ai_elicit` (L3.2), Export-Filter aus `export`, Terminologie-Profile um Attribut-Labels ergänzen. Zwei Tage.
6. **Live-Anpassung:** Definitionen sind Daten, keine Deployments. Änderung im Editor wirkt sofort für neue Formular-Loads; `version`-Feld plus Audit-Log-Eintrag wie bei Workflows; Cache pro Workspace mit Invalidierung wie `presets/gate.py:_invalidate_workspace`.

Reihenfolge ist bewusst: erst Schema (billig, macht Lücken sichtbar), dann Renderer an den kleinen Typen (beweist das Konzept), dann Editor. Requirement zuletzt, weil es die meisten Sonderfälle hat und der Renderer bis dahin alle abdecken muss.

---

## Q. Fachliche Einschätzung: Was dringend fehlt, welche Konzepte zu kurz gedacht sind

Maßstab: die eigene Strategie (`PRODUCT_STRATEGY.md`): AI-nativ, Agenten als First-Class-Clients, zwei Zielgruppen (AI-first Software-Teams, Mid-Market Systems Engineers), Configurable Rigor. Ich urteile gegen dieses Ziel, nicht gegen DOORS.

### Q1 Dringend einbauen (Reihenfolge nach Schmerz pro Nutzer-Tag)

**1. Menschen im System: Owner, Kommentare, Benachrichtigungen.** Es gibt keine Comment-, Attachment-, Notification- oder Task-Entität. `owner` existiert nur auf Risk, `assignee` nur auf Issue. Ein Requirement hat keinen Verantwortlichen. Ein Workflow mit Signature-Gates, aber niemand erfährt, dass er unterschreiben soll. Ein Review-Queue, aber kein "warum abgelehnt" außer change_reason. Für die SE-Zielgruppe ist das der erste Grund, das Tool nicht zu nutzen: Requirements-Management ist zu 60 Prozent Kommunikation über das Requirement, nicht das Requirement selbst. Minimal: `owner` auf jedem Artefakt, `Comment(artifact, author, text, resolved)`, `Notification(user, kind, artifact, read)` mit Trigger aus Workflow-Transition, Review-Request, Suspect-Markierung, Zuweisung. Ein bis zwei Wochen, größter Nutzwert im ganzen Audit.

**2. Attribut-Definition als Systemobjekt (N3).** Ohne sie bleibt Configurable Rigor ein Feature-Schalter und wird nie ein Feld-Schalter. Ohne sie erhebt das Interview die falschen Felder. Ohne sie ist ReqIF-Mapping Handarbeit. Alles, was das Produkt "konfigurierbar" nennt, hängt hier.

**3. Tabellen-Ansicht und Massenbearbeitung.** Alles ist Split-View mit Liste links, Formular rechts. Es gibt keine Grid-Ansicht (`RequirementsList/` enthält nur `ModalDialogBase`), keinen Bulk-Edit-Endpoint (nur CSV-Import), keine Spaltenauswahl, keinen Inline-Edit. Ein Systems Engineer mit 400 Requirements arbeitet in Tabellen. Ein AI-Agent, der 40 Requirements einen Status setzen soll, braucht `PATCH /requirements/bulk/`. Beide Zielgruppen haben dieses Bedürfnis, keine wird bedient.

**4. Dokument-Sicht.** Der UI-Leitgedanke heißt "lebendes Spezifikationsdokument". Es gibt kein Dokument-Objekt, keine Kapitelstruktur, keinen Lesemodus, keinen Druck. Baseline hat einen Scope "Document" ohne Dokument-Entität. Export ist PDF-Report und ReqIF, kein Lastenheft mit Nummerierung. Für Mid-Market-SE ist das Dokument das Lieferobjekt an Kunden und Auditoren. Minimal: `Document(workspace, title, sections[] -> artifact-Query oder feste Liste)`, Lesemodus-Route, Export als DOCX oder Markdown mit Nummerierung, Baseline-Scope "Document" auf dieses Objekt binden.

**5. Requirement-Attribute rationale, source, owner, priority plus Stakeholder-Entität (D2).** Zwei Migrationen, ein Regelmodul. Ohne rationale ist jede Review-Diskussion Rätselraten, ohne source keine Rückverfolgung zum Kunden.

**6. Trace-Link-Semantik.** 15 Link-Typen, aber keine Matrix, welcher Typ zwischen welchen Artefakttypen erlaubt ist (`types.py` hat keine allowed-pairs-Struktur). `TraceLink` hat nur source, target, link_type: kein rationale, kein Status, kein created-by-agent-Marker auf dem Link. Ein Agent kann `verifies` von Risk nach Glossary anlegen. Suspect-Propagation existiert (`trace_link_service.py:1232`), aber der Nutzer sieht nicht, welche Änderung sie ausgelöst hat. Minimal: Erlaubt-Matrix in `types.py`, Validierung im Service, `rationale` und `suspect_reason` auf dem Link.

**7. Change-Management bis zum Ende (B3, D1 Prozess 14).** ChangeRequest hat Modell, REST, MCP, Events, Transition. Keine UI, keine CCB-Rolle, keine Verknüpfung "dieser CR ändert diese Artefakte" außer `ChangeRequestAffectedItem` ohne Oberfläche. Entweder fertig bauen oder rausnehmen. Halbfertig ist teurer als beides.

**8. Funktionsebene (D2 Lücke 1).** Für die SE-Zielgruppe der Unterschied zwischen "Requirements-Tool mit Architektur-Anhang" und "SE-Tool". `element_type = "function"` plus `performs` ist ein Tag Arbeit. Das Level-Feld auf ArchitectureElement ein zweiter.

**9. Meilenstein- und Review-Objekt (D2 Lücke 2).** Bündelt Baseline, Gate-Regeln, Audit-Report, Sign-off. "Sind wir PDR-reif?" als Systemfrage. Ohne das bleibt der Audit-Report ein Dashboard, kein Nachweis.

**10. Client-Integrationen reparieren (H5).** Zwei Stunden. Steht hier nur, weil es vor allem anderen passieren muss, sonst kann die Kernzielgruppe das Produkt nicht anschließen.

### Q2 Konzepte, die nicht weit genug gedacht sind

**Q2.1 "AI-nativ" ist "AI-angeschlossen".** Die Strategie sagt: Agenten sind First-Class-Clients. Der Code sagt: Agenten haben einen MCP-Server mit Tools, und LLM-Calls stecken in sechs Features mit sechs verschiedenen Bestätigungsmodellen (B7). Was fehlt, ist das Konzept "KI-Vorschlag als Zustand": jedes Artefakt, jeder Link, jede Transition, die ein Agent schreibt, ist `proposed_by_agent` bis ein Mensch bestätigt. Das Audit-Log kennt `actor_type = agent` mit `client_name` (`audit/writer.py:64`), das ist der richtige Ansatz, aber er bleibt im Log. Er müsste auf dem Artefakt sichtbar sein, filterbar, mit Bulk-Accept. Ohne das schreibt ein Agent direkt in die Wahrheit und die SE-Zielgruppe wird das Produkt aus Prinzip ablehnen. Zweiter fehlender Baustein: Agenten haben keine eigene Identität. Ein API-Key gehört einem User (E2.1). "Claude Code von Daniel" und "Daniel" sind im System dieselbe Person. Agenten brauchen einen Service-Account mit eigener Rolle, eigenem Rate-Limit, eigenem Scope. Dritter: Memory (M) speichert nur Interviews. Ein AI-natives Tool müsste jede Agenten-Interaktion als Kontext für die nächste nutzen.

**Q2.2 Configurable Rigor endet am Feature-Schalter.** Presets gaten Features, Baseline-Scopes, Workflow-Konfigurierbarkeit und ein Pflichtfeld (`title`). Sie gaten keine Attribute, keine Link-Typen, keine Review-Tiefe, keine Interview-Protokolle. Der Preset-Wechsel hat eine Downgrade-Prüfung, aber das UI zeigt nirgends "dieses Feld ist im Preset standard Pflicht, in minimal optional". Rigor ist ein Tenant-Schalter, müsste aber eine Eigenschaft der Definition sein (N3: `AttributeDefinition` pro Preset). Und: Rigor ist pro Workspace, nicht pro Artefakttyp. Ein Medizintechnik-Startup will Requirements extended, Issues minimal. Geht nicht.

**Q2.3 Das generische Artefaktmodell wurde begonnen und nicht beendet.** `Artifact` mit `artifact_type` und `custom_fields` ist das richtige Fundament: Traces, Baselines, Custom Fields, Search hängen daran. Aber vier Modellorte (B2), drei Status-Achsen (B1), zwei Versionierungen (B6), und jeder neue Typ (Goal, Icd, Diagram, Interview) wurde als eigene App mit eigenen Tabellen gebaut statt als Artifact-Spezialisierung. Konsequent zu Ende gedacht: Jeder Artefakttyp ist `Artifact` plus typisierte Attribute aus der Definition (N3), Versionierung und Diff einmal auf `Artifact`, Status einmal auf `Artifact` mit Workflow-State. Das ist die größte Konsolidierung und die Voraussetzung, dass Attribut-Editor, Interview und Export je "alle Typen" können.

**Q2.4 Traceability ist ein Link-Speicher, kein Modell.** 15 Typen ohne Semantik-Matrix, ohne Link-Attribute, ohne Richtungsregeln. Coverage rechnet requirement-zentriert. Impact-Analyse folgt Links, aber kennt keine Gewichtung (ein `documents`-Link ist kein `satisfies`-Link). Das UI-Signaturelement Trace-Spine zeigt die Kette, aber nur in der Hälfte der Views (A5). Zu Ende gedacht: Link-Typ hat erlaubte Paare, Richtung, Coverage-Relevanz, Impact-Gewicht, Suspect-Verhalten. Dann kann die Spine für jeden Typ dieselbe Frage beantworten: "Ist dieses Artefakt vollständig angebunden?"

**Q2.5 Der Workflow hat keine Menschen.** State-Machines pro Typ, Signature-Gates mit Passwort oder TOTP, Approval-Rollen, Review-Queue. Technisch besser als die meisten Tools. Aber: keine Zuweisung, keine Benachrichtigung, keine Frist, keine Eskalation, keine Delegation. Der Workflow weiß, was passieren darf, aber nicht, wer es tun soll und bis wann. Für Approval-Prozesse in regulierten Domänen ist das die halbe Miete, und die fehlende Hälfte ist die, die Auditoren fragen.

**Q2.6 Das Interview ist ein Chat, kein Elizitationsprozess.** L2. Es fragt Titel und Rationale, egal für welchen Typ, und macht daraus ein Requirement. Zu Ende gedacht ist das Interview der Einstieg für jede Artefakt-Erstellung: Protokoll aus der Attribut-Definition, Grounding gegen Bestand, Vorschlag als `proposed_by_agent`, Formalisierung typgerecht. Dann ist es das Feature, das die AI-first-Zielgruppe zuerst zeigt. Heute ist es ein Nebeneingang.

**Q2.7 Diagramme sind drei Editoren, kein Modell.** Canvas (Striche), Mermaid (Text), Node-Graph (Knoten mit Artefakt-Referenz). Nur Node-Graph kennt Artefakte. Kein gemeinsames Modell, keine Ableitung von Diagrammen aus Struktur (Architektur-Baum als Blockdiagramm), keine Ableitung von Struktur aus Diagrammen (Knoten wird ArchitectureElement). MBSE-kompatibel steht in der Beschreibung, das M fehlt. Zu Ende gedacht: Node-Graph ist der einzige Diagrammtyp mit Semantik, Mermaid ist Export, Canvas ist Skizze mit "in Node-Graph überführen".

**Q2.8 Multi-Tenancy ohne Produktstruktur.** Tenant, Workspace, fertig. Kein Projekt über Workspaces, keine Produktlinie, keine Variante, keine Wiederverwendung außer `copy-of` und Workspace-Clone. Automotive-Zulieferer arbeiten in Varianten. Ein Workspace pro Variante mit Copy-of-Links ist nach dem zweiten Change-Request unbeherrschbar. Das ist v2-Stoff, aber die Workspace-Grenze sollte heute schon nicht als Produktgrenze gebaut werden.

**Q2.9 Die UI hat ein Konzept, aber keine Bibliothek.** UI_KONZEPT.md ist gut. Der Code hat 1015 Inline-Styles, sieben Formulare, zwei SplitView-Verträge, sechs Feedback-Muster. Das Konzept beschreibt Flächen, nicht Komponenten. Deshalb baut jede View ihre eigene Interpretation. Zu Ende gedacht braucht das Konzept ein Kapitel "Komponentenkatalog" mit verbindlichen Bausteinen (ArtifactForm, FieldComponents, StatusControl, FeedbackToast, DataGrid), und ESLint-Regeln, die Inline-Styles und Fremdmuster ablehnen.

**Q2.10 Integration ist Einbahnstraße.** Import (CSV, ReqIF), Export (CSV, ReqIF, PDF, Bundle), MCP, Webhooks (nur Admin). Kein bidirektionaler Sync mit Jira, GitHub Issues, GitLab, Polarion, DOORS. Die AI-first-Zielgruppe hat ihre Tickets in Jira oder GitHub; sie wird ReqogniLoom nicht als zweite Wahrheit pflegen. Minimal für v1: GitHub-Issue-Link als Artefakt-Attribut plus Webhook-Empfänger, der Issue-Status spiegelt. Das ist der Grund, warum Webhooks Self-Service werden müssen (E2.2).

### Q3 Zusammenfassung in einem Satz pro Zielgruppe

- **AI-first Software-Teams** bekommen einen MCP-Server, den sie heute nicht anschließen können (H), Agenten ohne Identität (Q2.1) und keine Verbindung zu ihrem Ticket-System (Q2.10).
- **Mid-Market Systems Engineers** bekommen Traceability, Baselines und Signature-Gates auf Niveau teurer Tools, aber ohne Owner, Kommentare, Tabellen, Dokumente und Funktionsebene (Q1.1, Q1.3, Q1.4, Q1.8), also ohne die Hälfte ihres Arbeitstags.

Das Fundament ist ungewöhnlich stark für ein POC. Die Lücken liegen nicht in der Tiefe, sondern in der Breite der Alltagsfunktionen und in der Konsequenz der eigenen Konzepte.

---

## O. Priorisierung (gesamt)

| Rang | Befund | Warum zuerst |
|---|---|---|
| 0 | H5.1 bis H5.3 Claude Code verdrahten, GET-405, OpenCode-Klammern | Drei Quick-Fixes unter zwei Stunden. Danach funktionieren die zwei wichtigsten Clients überhaupt erst. |
| 1 | C1 OpenAPI leer für 43 Views | Jeder Client, auch das eigene FE, arbeitet ohne Vertrag. Ursache von B4, E2.4 und künftigen Drifts. |
| 2 | E2.1 API-Key-Scopes | Ohne Scopes kann kein Plugin an Dritte gehen. Kleiner Eingriff, große Wirkung. |
| 1a | Q1.1 Owner, Kommentare, Benachrichtigungen | Kein Konzeptbruch, schlicht fehlend. Größter Nutzwert pro Aufwand für die SE-Zielgruppe. |
| 1b | Q2.1 KI-Vorschlag als Zustand, Agenten-Identität | Der USP "AI-nativ" steht und fällt damit. Baut auf E2.1 und dem vorhandenen actor_type im Audit auf. |
| 2a | L2.1 formalize erzeugt immer Requirement | Funktionaler Defekt. Interview für Risk oder ADR liefert falschen Artefakttyp. Ein Dispatch-Table, ein Tag. |
| 2b | N3 + N4 Attribut-Definition als Systemobjekt | Löst A1 teilweise, B5, N1 komplett, liefert L3.2 und Export-Mapping mit. Größtes einzelnes Konsolidierungsvorhaben, 15 bis 20 Tage. |
| 3 | B1 Drei Status-Achsen, deutscher Default | Trifft Datenmodell, Workflow, Badge-Logik, Export. Wird mit jedem Feature teurer. Vor N4 Schritt 2 klären, sonst wird der Status-Sonderfall in die Definition einzementiert. |
| 3a | M2.1 Memory an alle LLM-Pfade | Sonst ist das Subsystem Ballast. Mixin im llm_adapter, zwei Tage. |
| 4 | E2.2 Webhooks self-service | Fertige Substanz, nur die Tür fehlt. Macht Integrationen ohne Admin-Zugang möglich. |
| 5 | D2 Lücke 5 + 6: Requirement-Attribute und Stakeholder-Entität | Kleinste Datenmodell-Änderung mit größtem SE-Reifegewinn. |
| 6 | A1 + A2 Inline-Styles und Roh-Farben | Blockiert Theming und Responsive strukturell. Mechanisch abbaubar. |
| 7 | C5 + C6 + E3.4 MCP modernisieren | KI-Integration ist Produktkern. Alte Protokollversion und fehlende Kernartefakte schwächen sie. |
| 8 | A5 + A4 Spine überall, toten SplitView-Vertrag entscheiden | Signaturelement des Konzepts ist halb umgesetzt. |
| 9 | E2.3 Hermes bereinigen | Zwei tote POCs kosten Pflege und täuschen Integrationsfähigkeit vor. |
| 10 | D2 Lücke 2 + 3: Meilenstein-Objekt, Validierung | Größere Konzeptarbeit, erst nach 1 bis 5. |

## P. Nicht bewertet

- Live-Rendering, Kontraste, Fokus-Reihenfolge, Tastaturpfade (Docker nicht verfügbar).
- Performance, N+1, Query-Pläne.
- Security-Tiefe jenseits der Sichtprüfung von Auth, RBAC-Gate und Tenancy-Registrierung.
- Diagramm-Editoren (Canvas, Mermaid, Graph) inhaltlich, nur Theming-Bruch erfasst.
