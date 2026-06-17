# ReqFlow — L2 Component Requirements

> Status: ENTWURF | Erstellt: 2026-06-17 | Quelle: REQUIREMENTS_L1.md + system-overview.md + KONZEPT.md
>
> Dieses Dokument definiert die L2 Component Requirements (COMP-REQ) für ReqFlow v1.
> Jede COMP-REQ ist von genau einer L1 SYS-REQ abgeleitet und genau einem Subsystem zugeordnet.
> Sprache: Deutsch (Beschreibungen), English (IDs, Code-Namen).

---

## Traceability Matrix (SYS-REQ → COMP-REQ)

| SYS-REQ | COMP-REQ(s) | Primäres Subsystem |
|---------|-------------|-------------------|
| SYS-REQ-01 (Artefakt-Hierarchie) | COMP-REQ-001, COMP-REQ-002 | C4:ApplicationService, C10:PersistenceLayer |
| SYS-REQ-02 (Requirements CRUD + Workflow) | COMP-REQ-003, COMP-REQ-004 | C4:ApplicationService, C5:WorkflowEngine |
| SYS-REQ-03 (Traceability) | COMP-REQ-005, COMP-REQ-006 | C7:TraceabilityEngine |
| SYS-REQ-04 (ArchitectureElement) | COMP-REQ-007 | C4:ApplicationService |
| SYS-REQ-05 (MCP Server) | COMP-REQ-009, COMP-REQ-010, COMP-REQ-011, COMP-REQ-012 | C3:McpServer |
| SYS-REQ-06 (REST API + OpenAPI) | COMP-REQ-013, COMP-REQ-014, COMP-REQ-015 | C2:RestApiAdapter |
| SYS-REQ-07 (Configurable-Rigor-Presets) | COMP-REQ-016, COMP-REQ-017, COMP-REQ-018 | C8:PresetConfigEngine |
| SYS-REQ-08 (Multi-Level-Baselines) | COMP-REQ-019, COMP-REQ-020, COMP-REQ-021 | C6:BaselineService |
| SYS-REQ-09 (Item-Level-Workflow) | COMP-REQ-022, COMP-REQ-023, COMP-REQ-024 | C5:WorkflowEngine |
| SYS-REQ-10 (RBAC) | COMP-REQ-025, COMP-REQ-026 | C11:AuthAndTenancy |
| SYS-REQ-11 (Audit-Trail) | COMP-REQ-027, COMP-REQ-028 | C12:AuditLog |
| SYS-REQ-12 (Testmanagement) | COMP-REQ-029, COMP-REQ-030 | C4:ApplicationService, C7:TraceabilityEngine |
| SYS-REQ-13 (LLM-Capabilities) | COMP-REQ-031, COMP-REQ-032 | C9:LlmAdapter |
| SYS-REQ-14 (Terminologie-Profile) | COMP-REQ-033, COMP-REQ-034 | C8:PresetConfigEngine |
| SYS-REQ-15 (Multi-Tenancy) | COMP-REQ-035, COMP-REQ-036 | C10:PersistenceLayer, C11:AuthAndTenancy |
| SYS-REQ-16 (i18n DE/EN) | COMP-REQ-037, COMP-REQ-038 | C1:ReactFrontend, C2:RestApiAdapter |
| SYS-REQ-17 (React-UI) | COMP-REQ-039, COMP-REQ-040, COMP-REQ-041, COMP-REQ-042 | C1:ReactFrontend |
| SYS-REQ-18 (Docker Compose) | COMP-REQ-043 | C4:ApplicationService |
| SYS-REQ-19 (Export JSON/CSV) | COMP-REQ-044, COMP-REQ-045 | C4:ApplicationService |
| SYS-REQ-20 (Volltextsuche) | COMP-REQ-046, COMP-REQ-047, COMP-REQ-048 | C4:ApplicationService, C10:PersistenceLayer |

---

## COMP-REQs gruppiert nach Subsystem

---

### C1: ReactFrontend (UI-Layer)

---

#### COMP-REQ-039: Dashboard mit Projektübersicht und Offenen Punkten

- **Beschreibung:** Das ReactFrontend muss ein Dashboard bereitstellen, das eine Übersicht über alle Workspaces des aktuellen Nutzers zeigt, inklusive Anzahl der Requirements pro Workspace, Anzahl offener Punkte (Requirements im Initial-State ohne TraceLink) und aktives Terminologie-Profil.
- **Abgeleitet von:** SYS-REQ-17 (SN-12: Gleichrangige Schnittstellen für manuelle Nutzer)
- **Zugeordnetes Subsystem:** C1:ReactFrontend
- **Abnahmekriterium:** Nach Login rendert das Dashboard innerhalb von 2 Sekunden eine Workspace-Kartenliste mit Requiremenszahl, Anzahl offener Punkte und dem aktiven Terminologie-Profil pro Workspace. Ein Workspace ohne offene Punkte zeigt den Zähler „0".
- **Priorität:** mandatory

#### COMP-REQ-040: Requirements-Editor mit Inline-Editing und Markdown

- **Beschreibung:** Das ReactFrontend muss einen Requirements-Editor bereitstellen, der Inline-Editing für Title, Description und Category eines Requirements unterstützt. Das Description-Feld muss Markdown rendern (Vorschau und Edit-Modus). Der Editor muss den aktuellen WorkflowState anzeigen und State-Übergänge über einen Dropdown auslösen können.
- **Abgeleitet von:** SYS-REQ-17 (SN-02: Skalierbare SE-Tiefe)
- **Zugeordnetes Subsystem:** C1:ReactFrontend
- **Abnahmekriterium:** Nutzer kann ein Requirement anklicken, Title/Description inline bearbeiten, Markdown-Vorschau toggle, und über ein Dropdown den WorkflowState wechseln. Nach dem Speichern zeigt der Editor den aktualisierten State. Integration-Test: Editiere Description → API-Call PATCH /requirements/{id} → Response 200.
- **Priorität:** mandatory

#### COMP-REQ-041: Architecture-Editor

- **Beschreibung:** Das ReactFrontend muss einen Architecture-Editor bereitstellen, der CRUD-Operationen für ArchitectureElements unterstützt — inkl. Element-Typ-Auswahl (Component, Interface, Subsystem, Layer, Module), Markdown-Description und Anzeige verknüpfter TraceLinks.
- **Abgeleitet von:** SYS-REQ-17 (SYS-REQ-04: ArchitectureElement als Artefakttyp)
- **Zugeordnetes Subsystem:** C1:ReactFrontend
- **Abnahmekriterium:** Nutzer kann ein ArchitectureElement anlegen, den Element-Typ aus einem Dropdown wählen, die Description in Markdown editieren und verknüpfte Requirements in einer Seitenleiste sehen. Unit-Test: Render ArchitectureEditor mit Mock-ArchitectureElement → alle Felder sichtbar und editierbar.
- **Priorität:** mandatory

#### COMP-REQ-042: Artefakt-Navigation als Baumstruktur

- **Beschreibung:** Das ReactFrontend muss eine Artefakt-Navigation in Baumstruktur (Tree-View) bereitstellen, die die hierarchische Artifact-Struktur eines Workspaces darstellt. Der Baum muss Lazy-Loading für Kindknoten unterstützen und per Klick ein Artefakt mit seinen Requirements im Editor öffnen.
- **Abgeleitet von:** SYS-REQ-17 (SYS-REQ-01: Artefakt-Hierarchie)
- **Zugeordnetes Subsystem:** C1:ReactFrontend
- **Abnahmekriterium:** Tree-View zeigt die Artefakt-Hierarchie korrekt verschachtelt. Klick auf einen Knoten lädt die Kindknoten asynchron nach (API: GET /artifacts/tree?parent_id=X) und öffnet das Artefakt im Editor. Bei 500 Artefakten beträgt die initiale Ladezeit unter 1 Sekunde (nur Root-Knoten).
- **Priorität:** mandatory

---

### C2: RestApiAdapter (REST-Schnittstelle)

---

#### COMP-REQ-013: REST-CRUD-Endpunkte für alle Entitäten

- **Beschreibung:** Der RestApiAdapter muss für jede Entität (Artifact, Requirement, ArchitectureElement, TestCase, TraceLink, Baseline, WorkflowDefinition) vollständige CRUD-Endpunkte unter `/api/v1/` bereitstellen. Jeder Endpunkt muss JSON-Request-Bodies validieren, serialisieren und an den ApplicationService delegieren. Keine Geschäftslogik darf in der Adapter-Schicht implementiert werden.
- **Abgeleitet von:** SYS-REQ-06 (SN-12: REST und MCP gleichrangig)
- **Zugeordnetes Subsystem:** C2:RestApiAdapter
- **Abnahmekriterium:** Für jede der 7 Entitäten existieren GET (Liste + Detail), POST, PATCH, DELETE Endpunkte. Integration-Test: POST /api/v1/requirements/ mit valide Body → 201 + JSON; GET /api/v1/requirements/{id}/ → 200 + JSON; PATCH → 200; DELETE → 204. OpenAPI-Spec unter /api/v1/schema/ listet alle Endpunkte.
- **Priorität:** mandatory

#### COMP-REQ-014: Auto-generierte OpenAPI-Spezifikation

- **Beschreibung:** Der RestApiAdapter muss unter `/api/v1/schema/` eine vollständige, auto-generierte OpenAPI-3.0-Spezifikation bereitstellen, die alle Endpunkte, Request/Response-Schemas, Authentifizierung und Fehlercodes dokumentiert. Ein Swagger-UI muss unter `/api/v1/schema/swagger-ui/` zugänglich sein.
- **Abgeleitet von:** SYS-REQ-06 (SN-01: Maschinenlesbarer Kontext)
- **Zugeordnetes Subsystem:** C2:RestApiAdapter
- **Abnahmekriterium:** GET /api/v1/schema/ liefert valides OpenAPI-3.0-JSON mit allen CRUD-Endpunkten für alle 7 Entitäten. GET /api/v1/schema/swagger-ui/ rendert eine interaktive API-Dokumentation. Ein OpenAPI-Client-Generator (z.B. openapi-generator-cli) erzeugt fehlerfrei einen TypeScript-Client aus der Spezifikation.
- **Priorität:** mandatory

#### COMP-REQ-015: API-Response-Performance unter 200ms

- **Beschreibung:** Der RestApiAdapter muss für Standard-Queries (GET Liste, GET Detail) Antwortzeiten unter 200ms bei bis zu 10.000 Requirements im Workspace einhalten. Dies umfasst Serialisierung und Datenbankabfrage, exklusive Netzwerk-Latenz.
- **Abgeleitet von:** SYS-REQ-06 (SN-02: Skalierbare SE-Tiefe)
- **Zugeordnetes Subsystem:** C2:RestApiAdapter
- **Abnahmekriterium:** Lasttest: 10.000 Requirements im Workspace, 100 gleichzeitige GET /api/v1/requirements/ Anfragen → p95-Latenz ≤ 200ms gemessen am Server. Datenbank-Indizes für die Standard-Query-Pfade (tenant_id, workspace_id, workflow_state) sind vorhanden.
- **Priorität:** mandatory

---

### C3: McpServer (MCP-Schnittstelle)

---

#### COMP-REQ-009: Requirements-Tool-Gruppe (6 Tools)

- **Beschreibung:** Der McpServer muss die sechs Tools `requirement.get`, `requirement.query`, `requirement.create`, `requirement.update`, `requirement.decompose` und `requirement.validate` implementieren. Jedes Tool validiert seine Eingabeparameter gegen ein JSON-Schema, delegiert an den ApplicationService und serialisiert das Ergebnis. `requirement.validate` ist nur bei konfiguriertem LLM-Provider ausführbar; ohne LLM gibt das Tool einen strukturierten Fehler „LLM nicht konfiguriert" zurück.
- **Abgeleitet von:** SYS-REQ-05 (Ref: L2-MCP-01)
- **Zugeordnetes Subsystem:** C3:McpServer
- **Abnahmekriterium:** Alle 6 Tools sind via MCP-Protokoll aufrufbar. `requirement.get(id)` liefert Requirement mit Traces, Workflow-History und Audit-Feldern. `requirement.create(title, description, type, artifact_id)` erzeugt ein Requirement und gibt die UUID zurück. `requirement.validate(id)` ohne LLM-Config → JSON-Error mit Code „LLM_NOT_CONFIGURED". Jede schreibende Operation erzeugt einen AuditLog-Eintrag.
- **Priorität:** mandatory

#### COMP-REQ-010: Architecture-Tool-Gruppe (5 Tools)

- **Beschreibung:** Der McpServer muss die fünf Tools `architecture.get`, `architecture.query`, `architecture.create`, `architecture.update` und `architecture.link` implementieren. `architecture.link` unterstützt das Verknüpfen eines ArchitectureElements mit einem Requirement, TestCase oder einem anderen ArchitectureElement unter Angabe des Link-Typs.
- **Abgeleitet von:** SYS-REQ-05 (Ref: L2-MCP-02)
- **Zugeordnetes Subsystem:** C3:McpServer
- **Abnahmekriterium:** Alle 5 Tools sind via MCP-Protokoll aufrufbar. `architecture.create(title, description, element_type, workspace_id)` erzeugt ein ArchitectureElement. `architecture.link(arch_id, target_id, target_type, link_type)` erzeugt einen TraceLink. Schreibende Operationen erzeugen AuditLog-Einträge mit Agent-Client-Identität und API-Key.
- **Priorität:** mandatory

#### COMP-REQ-011: Test-Tool-Gruppe (5 Tools)

- **Beschreibung:** Der McpServer muss die fünf Tools `test.get`, `test.query`, `test.create`, `test.update` und `test.link` implementieren. `test.create` erlaubt optionale direkte Verknüpfung mit einem Requirement. `test.update` ermöglicht das Schreiben des Test-Status (Passed/Failed/Not Run) nach Testausführung.
- **Abgeleitet von:** SYS-REQ-05 (Ref: L2-MCP-03)
- **Zugeordnetes Subsystem:** C3:McpServer
- **Abnahmekriterium:** Alle 5 Tools sind via MCP-Protokoll aufrufbar. `test.create(title, type, linked_req_id)` erzeugt TestCase und optional TraceLink. `test.update(id, {status: "Passed"})` aktualisiert den Test-Status. `test.link(test_id, req_id)` erzeugt nachträglich einen TraceLink vom Typ `verifies`. AuditLog für alle schreibenden Operationen.
- **Priorität:** mandatory

#### COMP-REQ-012: Übergreifende Tools (4 Tools)

- **Beschreibung:** Der McpServer muss die vier Tools `traceability.query`, `artifact.search`, `artifact.get_tree` und `workspace.get_context` implementieren. `workspace.get_context` liefert den kompletten Workspace-Status (offene Requirements, unverknüpfte Tests, Coverage-Summary, aktives Preset, aktives Terminologie-Profil, aktive WorkflowDefinitions) und dient als Orientierungspunkt für AI-Agenten beim Sitzungsstart.
- **Abgeleitet von:** SYS-REQ-05 (Ref: L2-MCP-04)
- **Zugeordnetes Subsystem:** C3:McpServer
- **Abnahmekriterium:** `traceability.query(artifact_id, direction)` liefert Upstream/Downstream-Graph. `artifact.search(query)` liefert gemischte Ergebnisliste über alle Artefakttypen. `artifact.get_tree(root_id)` liefert hierarchische Struktur. `workspace.get_context()` liefert JSON mit allen Workspace-Metadaten. Alle 4 Tools funktionieren ohne schreibenden Zugriff und benötigen keine LLM-Konfiguration.
- **Priorität:** mandatory

---

### C4: ApplicationService (Domain-Service-Schicht)

---

#### COMP-REQ-001: Artifact-Hierarchy Cycle Detection

- **Beschreibung:** Das ArtifactService muss beim Erstellen oder Ändern einer Eltern-Kind-Beziehung (parent-Feld) prüfen, dass keine zyklischen Abhängigkeiten entstehen. Ein Zyklus ist definiert als Pfad von einem Artifact-Knoten zurück zu sich selbst über die parent-Beziehung. Die Prüfung muss vor der Persistierung erfolgen und bei Zyklus-Erkennung die Operation mit einer klaren Fehlermeldung abbrechen.
- **Abgeleitet von:** SYS-REQ-01 (SN-02: Skalierbare SE-Tiefe)
- **Zugeordnetes Subsystem:** C4:ApplicationService (ArtifactService)
- **Abnahmekriterium:** Unit-Test: Erstelle Kette A→B→C (C.parent=B, B.parent=A). Versuche C.parent=A zu setzen → Exception „Cycle detected: A→B→C→A". Versuche A.parent=C zu setzen → Exception „Cycle detected: A→C→B→A". Versuche A.parent=A zu setzen → Exception „Cycle detected: self-reference".
- **Priorität:** mandatory

#### COMP-REQ-002: Artifact Tree Query mit beliebiger Tiefe

- **Beschreibung:** Das ArtifactService muss eine Tree-Query-Operation bereitstellen, die die vollständige Hierarchie eines Workspaces (oder ab einem optionalen Root-Knoten) als verschachtelte Struktur zurückgibt. Die Abfrage muss über PostgreSQL Recursive CTEs implementiert werden und in der PersistenceLayer die entsprechenden Index-Strukturen vorhalten.
- **Abgeleitet von:** SYS-REQ-01 (SN-03: Traceability)
- **Zugeordnetes Subsystem:** C4:ApplicationService (ArtifactService)
- **Abnahmekriterium:** Tree-Query über 500 Artefakte in 5 Hierarchie-Ebenen liefert die vollständige verschachtelte Struktur in unter 200ms. Unit-Test: Erstelle 3-stufige Hierarchie, rufe `get_tree(workspace_id)` auf → Ergebnis enthält alle 3 Ebenen korrekt verschachtelt. Rufe `get_tree(root_id=B)` auf → Ergebnis enthält nur B und Nachkommen.
- **Priorität:** mandatory

#### COMP-REQ-003: Requirement CRUD mit Workflow-Integration

- **Beschreibung:** Das RequirementService muss vollständiges CRUD für Requirements bereitstellen. Bei Create wird automatisch der initiale WorkflowState (gemäß WorkflowDefinition des Workspaces) zugewiesen. Bei Update wird der change_reason validiert (Pflichtfeld im Extended-Preset). Bei Delete werden alle zugehörigen TraceLinks mitgelöscht. Jede Operation delegiert die Workflow-Validierung an die WorkflowEngine.
- **Abgeleitet von:** SYS-REQ-02 (SN-02: Skalierbare SE-Tiefe)
- **Zugeordnetes Subsystem:** C4:ApplicationService (RequirementService)
- **Abnahmekriterium:** Unit-Test: `create_requirement(title, desc, type, artifact_id)` → Requirement mit initialem WorkflowState (z.B. „draft") erzeugt. `update_requirement(id, fields, change_reason)` im Extended-Preset ohne change_reason → Fehler „change_reason required". `delete_requirement(id)` → Requirement und alle TraceLinks mit source/target = id gelöscht.
- **Priorität:** mandatory

#### COMP-REQ-007: ArchitectureElement CRUD mit Versionierung

- **Beschreibung:** Das ArchitectureService muss vollständiges CRUD für ArchitectureElements bereitstellen. Jedes ArchitectureElement wird mit einem Element-Typ (Component, Interface, Subsystem, Layer, Module) angelegt. Bei jedem Update wird das Versions-Feld automatisch inkrementiert (Optimistic Locking). Das ArchitectureElement kann optional mit einem Artifact verknüpft werden.
- **Abgeleitet von:** SYS-REQ-04 (SN-03: Traceability)
- **Zugeordnetes Subsystem:** C4:ApplicationService (ArchitectureService)
- **Abnahmekriterium:** Unit-Test: `create_architecture_element(title, desc, element_type, workspace_id)` → ArchitectureElement mit version=1 und initialem WorkflowState. `update_architecture_element(id, fields)` → version=2. Parallel-Update mit stale version → Fehler „OptimisticLockError: version mismatch". Delete löscht alle zugehörigen TraceLinks.
- **Priorität:** mandatory

#### COMP-REQ-029: TestCase CRUD mit Test-Status-Verwaltung

- **Beschreibung:** Das TestService muss vollständiges CRUD für TestCases bereitstellen. Jeder TestCase hat einen Test-Typ (Unit, Integration, System, Acceptance) und einen WorkflowState. Der Test-Ausführungsstatus (Passed, Failed, Not Run) wird als separates Feld verwaltet und kann via Update gesetzt werden.
- **Abgeleitet von:** SYS-REQ-12 (SN-03: Traceability)
- **Zugeordnetes Subsystem:** C4:ApplicationService (TestService)
- **Abnahmekriterium:** Unit-Test: `create_test_case(title, test_type, workspace_id)` → TestCase mit test_type und WorkflowState initial. `update_test_status(id, "Passed")` → execution_status = „Passed". `query_test_cases(filters={test_type: "Unit", workspace_id: X})` → gefilterte Liste. Delete löscht alle zugehörigen TraceLinks.
- **Priorität:** mandatory

#### COMP-REQ-044: Export in JSON und CSV

- **Beschreibung:** Der ExportService muss Export-Funktionen für Requirements, ArchitectureElements, TestCases und TraceLinks in den Formaten JSON und CSV bereitstellen. Der Export akzeptiert einen Scope (Workspace oder einzelnes Artefakt) und gibt eine Datei im angeforderten Format zurück. Das aktive Terminologie-Profil wird als Metadatum im Export hinterlegt.
- **Abgeleitet von:** SYS-REQ-19 (SN-12: Gleichrangige Schnittstellen)
- **Zugeordnetes Subsystem:** C4:ApplicationService (ExportService)
- **Abnahmekriterium:** Integration-Test: `export(format="json", scope=workspace_id)` → gültige JSON-Datei mit allen Requirements, ArchitectureElements, TestCases, TraceLinks und Metadatum `terminology_profile`. `export(format="csv", scope=workspace_id)` → CSV-Datei mit Header-Zeile und allen Entitäten, trennbar in Excel importierbar. Export von 1.000 Requirements completes in unter 5 Sekunden.
- **Priorität:** mandatory

#### COMP-REQ-045: Export mit Terminologie-Profil-Metadatum

- **Beschreibung:** Der ExportService muss das aktive Terminologie-Profil des Workspaces als Metadatum in jeden Export (JSON und CSV) einbetten. Im JSON-Export als Top-Level-Feld `metadata.terminology_profile`. Im CSV-Export als Kommentar-Zeile am Dateianfang oder als zusätzliche Spalte.
- **Abgeleitet von:** SYS-REQ-19 (SYS-REQ-14: Terminologie-Profile)
- **Zugeordnetes Subsystem:** C4:ApplicationService (ExportService)
- **Abnahmekriterium:** JSON-Export eines Workspaces im SE-Modus enthält `"metadata": {"terminology_profile": "se_mode"}`. CSV-Export enthält in der ersten Zeile `# terminology_profile: se_mode`. Nach Profilwechsel auf Dev-Modus und erneutem Export enthält die Datei `"terminology_profile": "dev_mode"`.
- **Priorität:** mandatory

#### COMP-REQ-046: Volltextsuche über alle Artefakttypen

- **Beschreibung:** Der SearchService muss eine artefakttyp-übergreifende Volltextsuche über Requirements, ArchitectureElements und TestCases bereitstellen. Die Suche nutzt PostgreSQL Full-Text-Search (tsvector) und durchsucht Title, Description und Tags. Ergebnisse werden nach Relevanz sortiert und enthalten eine Artefakttyp-Annotation.
- **Abgeleitet von:** SYS-REQ-20 (SN-01: Maschinenlesbarer Kontext)
- **Zugeordnetes Subsystem:** C4:ApplicationService (SearchService)
- **Abnahmekriterium:** Integration-Test: Erstelle 5 Requirements, 3 ArchitectureElements, 2 TestCases mit verschiedenen Titles/Descriptions. `search(query="Authentifizierung")` → Ergebnisliste mit allen Matches, jeweils mit `artifact_type`-Feld („requirement", „architecture_element", „test_case"), sortiert nach Relevanz. Suche über 10.000 Items in unter 500ms.
- **Priorität:** mandatory

#### COMP-REQ-047: Search Type-Filter und Workspace-Filter

- **Beschreibung:** Der SearchService muss optionale Filter für Artefakttyp und Workspace unterstützen. Der Typ-Filter erlaubt die Einschränkung der Suche auf eine oder mehrere Artefakttypen (z.B. nur Requirements). Der Workspace-Filter schränkt die Suche auf einen bestimmten Workspace ein.
- **Abgeleitet von:** SYS-REQ-20 (SN-01: Maschinenlesbarer Kontext)
- **Zugeordnetes Subsystem:** C4:ApplicationService (SearchService)
- **Abnahmekriterium:** `search(query="test", types=["requirement"])` → nur Requirement-Treffer, keine ArchitectureElements oder TestCases. `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X. Kombiniert: `search(query="test", types=["requirement", "test_case"], workspace_id=X)` → nur Requirements und TestCases aus Workspace X.
- **Priorität:** mandatory

---

### C5: WorkflowEngine (Item-Lifecycle)

---

#### COMP-REQ-004: Workflow-Transition-Validierung

- **Beschreibung:** Die WorkflowEngine muss bei jedem State-Übergang eines Items (Requirement, ArchitectureElement, TestCase) validieren: (1) Die Transition `from_state → to_state` ist in der aktiven WorkflowDefinition erlaubt, (2) die Rolle des anfragenden Nutzers ist in den `allowed_roles` der Transition enthalten, (3) falls `requires_change_reason=true`, ist ein nicht-leerer `change_reason` vorhanden. Bei Regelverletzung wird die Transition mit einer spezifischen Fehlermeldung abgelehnt.
- **Abgeleitet von:** SYS-REQ-02, SYS-REQ-09 (Ref: L2-WF-02)
- **Zugeordnetes Subsystem:** C5:WorkflowEngine (TransitionValidator)
- **Abnahmekriterium:** Unit-Test: WorkflowDefinition mit Transition draft→approved, allowed_roles=[„approver"], requires_change_reason=true. (a) Nutzer mit Rolle „editor" versucht draft→approved → Fehler „Role not allowed". (b) Nutzer mit Rolle „approver" ohne change_reason → Fehler „change_reason required". (c) Transition draft→deprecated (nicht definiert) → Fehler „Transition not allowed". (d) Valider Übergang → State aktualisiert, History-Eintrag geschrieben.
- **Priorität:** mandatory

#### COMP-REQ-022: WorkflowDefinition-Verwaltung pro Item-Typ und Workspace

- **Beschreibung:** Die WorkflowEngine muss WorkflowDefinitions pro Item-Typ (Requirement, ArchitectureElement, TestCase) und Workspace verwalten. Es müssen vordefinierte Default-Workflows für alle drei Presets bereitgestellt werden: Minimal (Draft/Done), Standard (Draft/Approved/Deprecated), Extended (konfigurierbar mit Approval-Gate). Workflow-Änderungen dürfen nicht Items in existierenden States invalidieren.
- **Abgeleitet von:** SYS-REQ-09 (Ref: L2-WF-01)
- **Zugeordnetes Subsystem:** C5:WorkflowEngine (WorkflowDefinitionStore)
- **Abnahmekriterium:** Unit-Test: Erstelle Workspace im Minimal-Preset → Default-Workflow hat States [draft, done], alle Transitions für editor erlaubt. Erstelle Workspace im Extended-Preset → Default-Workflow hat States [draft, in_review, approved, deprecated], Transition in_review→approved nur für approver. `create_workflow_definition(workspace_id, item_type, states, transitions)` → neue Definition persistiert.
- **Priorität:** mandatory

#### COMP-REQ-023: WorkflowState History mit Audit-Trail

- **Beschreibung:** Die WorkflowEngine muss bei jedem State-Übergang einen History-Eintrag in `WorkflowState.history` schreiben, der folgende Felder enthält: `from_state`, `to_state`, `transitioned_by` (User-ID), `transitioned_at` (Zeitstempel), `change_reason` (optional). Die History ist append-only und darf nicht manipuliert werden.
- **Abgeleitet von:** SYS-REQ-09 (SN-05: Konfigurierbarer Item-Lifecycle)
- **Zugeordnetes Subsystem:** C5:WorkflowEngine (StateMutator)
- **Abnahmekriterium:** Unit-Test: Führe 3 aufeinanderfolgende Transitionen durch (draft→in_review→approved). `WorkflowState.history` enthält 3 Einträge in korrekter Reihenfolge mit from/to, user, timestamp und change_reason. Versuch, einen History-Eintrag zu löschen oder zu ändern → Exception „History is append-only".
- **Priorität:** mandatory

#### COMP-REQ-024: Workflow-Migration bei Definition-Änderung

- **Beschreibung:** Die WorkflowEngine muss beim Ändern einer WorkflowDefinition prüfen, ob Items in States existieren, die in der neuen Definition nicht mehr vorkommen (verwaiste States). Falls verwaiste States existieren, wird die Definition-Änderung blockiert und eine Fehlermeldung mit Liste der betroffenen Items zurückgegeben. (v1-Default gemäß OP-03; endgültige Semantik nach Klärung.)
- **Abgeleitet von:** SYS-REQ-09 (OP-03: Workflow-Wechsel-Semantik)
- **Zugeordnetes Subsystem:** C5:WorkflowEngine (WorkflowMigrationHandler)
- **Abnahmekriterium:** Unit-Test: WorkflowDefinition mit States [draft, in_progress, approved]. 5 Items im State „in_progress". Ändere Definition zu [draft, ready_for_review, approved] (State „in_progress" entfernt) → Fehler „Workflow change blocked: 5 items in orphaned state 'in_progress'". After Migration der Items (manuell auf „draft" gesetzt) → Definition-Änderung erfolgreich.
- **Priorität:** should-have

---

### C6: BaselineService (Snapshot-Engine)

---

#### COMP-REQ-019: Baseline Scope-Auflösung und Snapshot-Erstellung

- **Beschreibung:** Der BaselineService muss beim Erstellen einer Baseline alle betroffenen Item-IDs und deren Versionen für den angeforderten Scope (document, project, global) ermitteln. Der Snapshot wird atomar als JSON-Dokument persistiert und ist nach Erstellung unveränderlich. Der Scope `document` umfasst ein Artefakt und alle Nachkommen. Der Scope `project` umfasst einen Workspace. Der Scope `global` umfasst alle Workspaces des Tenants.
- **Abgeleitet von:** SYS-REQ-08 (Ref: L2-BL-01, SN-04: Baselines)
- **Zugeordnetes Subsystem:** C6:BaselineService (ScopeResolver + SnapshotBuilder)
- **Abnahmekriterium:** Integration-Test: Erstelle Baseline scope=project für Workspace mit 10 Requirements, 3 ArchitectureElements, 5 TestCases → JSON-Snapshot enthält 18 Item-IDs mit Versionen. Ändere nachfolgend ein Requirement → Baseline-Snapshot unverändert (Version bleibt). Erstelle Baseline scope=document für Artifact A mit 2 Kindern → Snapshot enthält A + 2 Kinder + zugehörige Requirements/Tests.
- **Priorität:** mandatory

#### COMP-REQ-020: Baseline-Vergleich (Diff)

- **Beschreibung:** Der BaselineService muss den Vergleich zweier Baselines desselben Scopes unterstützen und eine Diff-Darstellung liefern. Der Diff enthält drei Kategorien: hinzugefügte Items (in Baseline B aber nicht A), entfernte Items (in Baseline A aber nicht B) und geänderte Items (in beiden, aber mit unterschiedlicher Version).
- **Abgeleitet von:** SYS-REQ-08 (Ref: L2-BL-02)
- **Zugeordnetes Subsystem:** C6:BaselineService (BaselineDiff)
- **Abnahmekriterium:** Integration-Test: Erstelle Baseline A (5 Items, Versionen 1-5). Ändere 2 Items (Version 2→3, 4→5), lösche 1 Item, füge 1 neues Item hinzu. Erstelle Baseline B. `diff(A, B)` → `{added: [new_item_id], removed: [deleted_item_id], changed: [{id: item2, old_version: 2, new_version: 3}, {id: item4, old_version: 4, new_version: 5}]}`.
- **Priorität:** mandatory

#### COMP-REQ-021: Baseline Preset-Gate (Scope-Verfügbarkeit)

- **Beschreibung:** Der BaselineService muss vor der Erstellung einer Baseline die PresetConfigEngine konsultieren, um zu prüfen, ob der angeforderte Scope im aktiven Workspace-Preset erlaubt ist. Scope `document` und `project` sind ab Standard-Preset erlaubt. Scope `global` ist nur im Extended-Preset erlaubt. Bei nicht erlaubtem Scope wird die Erstellung mit einer klaren Fehlermeldung abgelehnt.
- **Abgeleitet von:** SYS-REQ-08 (SYS-REQ-07: Configurable-Rigor-Presets)
- **Zugeordnetes Subsystem:** C6:BaselineService (PresetGate)
- **Abnahmekriterium:** Unit-Test: Workspace im Minimal-Preset → `create_baseline(scope="document")` → Fehler „Baselines not available in Minimal preset". Workspace im Standard-Preset → `create_baseline(scope="document")` → OK; `create_baseline(scope="global")` → Fehler „Global baselines require Extended preset". Workspace im Extended-Preset → alle drei Scopes erlaubt.
- **Priorität:** mandatory

---

### C7: TraceabilityEngine (Verknüpfungs-Logik)

---

#### COMP-REQ-005: TraceLink-CRUD mit 6 Link-Typen

- **Beschreibung:** Die TraceabilityEngine muss TraceLinks zwischen Requirements, ArchitectureElements und TestCases verwalten. Unterstützte Link-Typen: `parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`. Jeder TraceLink hat genau eine Source-Entität und genau eine Target-Entität (DB-Constraint). Source und Target müssen demselben Tenant angehören.
- **Abgeleitet von:** SYS-REQ-03 (SN-03: Traceability)
- **Zugeordnetes Subsystem:** C7:TraceabilityEngine
- **Abnahmekriterium:** Unit-Test: Erstelle TraceLink (source=Requirement-A, target=Requirement-B, type=derives-from) → OK. Erstelle TraceLink ohne Source → DB-Constraint-Fehler. Erstelle TraceLink mit source aus Tenant-1 und target aus Tenant-2 → Fehler „Cross-tenant link not allowed". Lösche TraceLink → OK. Query alle TraceLinks für Requirement-A → Liste mit erstelltem Link.
- **Priorität:** mandatory

#### COMP-REQ-006: Upstream/Downstream Query Performance unter 200ms

- **Beschreibung:** Die TraceabilityEngine muss Upstream- und Downstream-Queries für ein beliebiges Artefakt (Requirement, ArchitectureElement, TestCase) in unter 200ms beantworten können — bei bis zu 10.000 Items und 50.000 TraceLinks im Workspace. Das Ergebnis enthält alle erreichbaren Knoten mit Link-Typ-Annotation und Richtung.
- **Abgeleitet von:** SYS-REQ-03 (SN-03: Traceability)
- **Zugeordnetes Subsystem:** C7:TraceabilityEngine
- **Abnahmekriterium:** Lasttest: 10.000 Items, 50.000 TraceLinks (durchschnittlich 5 Links pro Item). `query_upstream(requirement_id)` → vollständiger Upstream-Graph in ≤ 200ms (p95). `query_downstream(requirement_id)` → vollständiger Downstream-Graph in ≤ 200ms (p95). PostgreSQL-Indizes (GIST/GIN) für TraceLink-Graph-Queries vorhanden.
- **Priorität:** mandatory

#### COMP-REQ-030: Coverage-Berechnung (Requirement → Test-Abdeckung)

- **Beschreibung:** Die TraceabilityEngine muss eine Coverage-Übersicht bereitstellen, die für jeden Workspace berechnet, welche Requirements mindestens einen verknüpften TestCase haben (via TraceLink vom Typ `verifies`). Die Coverage wird als Prozentsatz und als Liste der ungedeckten Requirements zurückgegeben.
- **Abgeleitet von:** SYS-REQ-12 (SN-03: Traceability)
- **Zugeordnetes Subsystem:** C7:TraceabilityEngine
- **Abnahmekriterium:** Integration-Test: 10 Requirements, 7 davon haben je mindestens einen TraceLink vom Typ `verifies` zu einem TestCase. `coverage(workspace_id)` → `{total: 10, covered: 7, uncovered: [req_id_8, req_id_9, req_id_10], percentage: 70.0}`. Coverage-Berechnung für 10.000 Requirements in unter 500ms.
- **Priorität:** mandatory

---

### C8: PresetConfigEngine (Configurable Rigor)

---

#### COMP-REQ-016: Preset-Verwaltung (Minimal / Standard / Extended)

- **Beschreibung:** Die PresetConfigEngine muss drei vordefinierte Presets (Minimal, Standard, Extended) auf Workspace-Ebene verwalten. Das Preset wird als JSON-Konfiguration im Workspace-Modell gespeichert und bestimmt zur Laufzeit: Pflichtfelder, sichtbare Funktionen, Baseline-Scope-Verfügbarkeit, Workflow-Konfigurierbarkeit und `change_reason`-Pflicht. Die Engine bietet eine Schnittstelle `get_preset(workspace_id)` und `is_feature_enabled(feature_key, workspace_id)` für alle konsultierenden Komponenten.
- **Abgeleitet von:** SYS-REQ-07 (SN-02: Skalierbare SE-Tiefe)
- **Zugeordnetes Subsystem:** C8:PresetConfigEngine
- **Abnahmekriterium:** Unit-Test: `get_preset(workspace_minimal)` → Preset-Regeln: keine Baselines, keine Approval-Workflows, change_reason optional. `is_feature_enabled("baselines", workspace_minimal)` → false. `is_feature_enabled("baselines", workspace_standard)` → true. `is_feature_enabled("global_baselines", workspace_standard)` → false. `is_feature_enabled("global_baselines", workspace_extended)` → true.
- **Priorität:** mandatory

#### COMP-REQ-017: Preset-Wechsel ohne Datenmigration (aufsteigend)

- **Beschreibung:** Die PresetConfigEngine muss den Wechsel zwischen Presets in aufsteigender Richtung (Minimal → Standard → Extended) ohne Datenmigration oder Datenverlust ermöglichen. Beim Wechsel werden keine bestehenden Daten gelöscht oder verändert; neue Funktionen werden schrittweise aktiviert.
- **Abgeleitet von:** SYS-REQ-07 (SN-02: Skalierbare SE-Tiefe)
- **Zugeordnetes Subsystem:** C8:PresetConfigEngine
- **Abnahmekriterium:** Integration-Test: Workspace im Minimal-Preset mit 50 Requirements. Wechsel zu Standard → alle 50 Requirements unverändert, Baseline-Funktionen verfügbar, erweiterter Workflow verfügbar. Wechsel zu Extended → alle 50 Requirements unverändert, Global-Baselines verfügbar, konfigurierbare Workflows verfügbar. Kein Datenverlust, keine Schema-Änderung messbar.
- **Priorität:** mandatory

#### COMP-REQ-018: Preset-Downgrade-Validierung

- **Beschreibung:** Die PresetConfigEngine (Subservice PresetPolicyService) muss beim Wechsel auf ein niedrigeres Preset (Downgrade) prüfen, ob inkompatible Daten existieren: Global-Baselines beim Wechsel von Extended → Standard, Approved-Items mit Approval-Gate beim Wechsel von Extended → Minimal. Bei Inkompabilität wird der Downgrade blockiert und eine Fehlermeldung mit Liste der betroffenen Items zurückgegeben. (Endgültige Semantik nach Klärung von OP-02.)
- **Abgeleitet von:** SYS-REQ-07 (OP-02: Preset-Downgrade-Semantik)
- **Zugeordnetes Subsystem:** C8:PresetConfigEngine (PresetPolicyService)
- **Abnahmekriterium:** Unit-Test: Workspace im Extended mit 1 Global-Baseline. `switch_preset(workspace_id, "standard")` → Fehler „Downgrade blocked: 1 global baseline exists. Delete global baselines before downgrading." Nach Löschen der Global-Baseline → Downgrade erfolgreich. Workspace im Extended mit 3 Items im State „approved" (via Approval-Gate). `switch_preset(workspace_id, "minimal")` → Fehler „Downgrade blocked: 3 items in approval-gated state."
- **Priorität:** should-have

#### COMP-REQ-033: Terminologie-Profil-Verwaltung (Dev-Modus / SE-Modus)

- **Beschreibung:** Die PresetConfigEngine muss mindestens zwei vordefinierte Terminologie-Profile (Dev-Modus, SE-Modus) auf Workspace-Ebene verwalten. Ein Profil definiert das Mapping von generischen Entitätsnamen zu domänenspezifischen Labels (z.B. Artifact → Epic/System Requirement). Die Profile werden als JSON-Konfiguration im Workspace-Modell gespeichert.
- **Abgeleitet von:** SYS-REQ-14 (SN-10: Terminologie-Flexibilität)
- **Zugeordnetes Subsystem:** C8:PresetConfigEngine
- **Abnahmekriterium:** Unit-Test: `get_terminology_profile(workspace_dev)` → `{artifact_l1: "Epic", artifact_l2: "Story", requirement: "Acceptance Criterion", ...}`. `get_terminology_profile(workspace_se)` → `{artifact_l1: "System Requirement", artifact_l2: "Function", requirement: "Verification Criterion", ...}`. `switch_terminology_profile(workspace_id, "se_mode")` → Profil geändert, keine DB-Änderung an Artefakt-Daten.
- **Priorität:** mandatory

#### COMP-REQ-034: Profilwechsel ohne Datenmigration

- **Beschreibung:** Die PresetConfigEngine muss einen Wechsel des Terminologie-Profils ausschließlich als Label-Änderung durchführen — ohne Datenbank-Schema-Änderung, ohne Datenmigration und ohne Änderung der API-Response-Struktur. Die REST API und der MCP Server nutzen immer generische Entitätsnamen unabhängig vom aktiven Profil.
- **Abgeleitet von:** SYS-REQ-14 (SN-10: Terminologie-Flexibilität)
- **Zugeordnetes Subsystem:** C8:PresetConfigEngine
- **Abnahmekriterium:** Integration-Test: Workspace im Dev-Modus mit 100 Requirements. Wechsel zu SE-Modus → API-Response `GET /api/v1/requirements/` identisch (generische Feldnamen). UI zeigt geänderte Labels („Epic" → „System Requirement"). Datenbank hat keine Schema-Änderung (kein Migration-Script ausgeführt). Profilwechsel in unter 1 Sekunde abgeschlossen.
- **Priorität:** mandatory

---

### C9: LlmAdapter (Provider-Abstraktion)

---

#### COMP-REQ-031: LLM-Capability-Interface mit Provider-Abstraktion

- **Beschreibung:** Der LlmAdapter muss eine stabile interne Schnittstelle (`LlmCapabilityInterface`) mit drei Operationen bereitstellen: `validate_artifact(artifact_id)`, `decompose_requirement(requirement_id)` und `check_consistency(workspace_id)`. Provider-Implementierungen (Anthropic, OpenAI, Ollama) sind über ein Plugin-Interface austauschbar. Der aktive Provider wird über die Deployment-Konfiguration (.env) gewählt.
- **Abgeleitet von:** SYS-REQ-13 (SN-07: LLM als optionale Capability)
- **Zugeordnetes Subsystem:** C9:LlmAdapter (LlmCapabilityInterface)
- **Abnahmekriterium:** Unit-Test: Konfiguriere Anthropic-Provider → `validate_artifact(req_id)` liefert `{score: 0.85, suggestions: [...]}`. Konfiguriere OpenAI-Provider → identische Schnittstelle, anderes Ergebnis. Konfiguriere Ollama-Provider → identische Schnittstelle. Alle drei Provider implementieren dasselbe Interface; kein Domain-Modul kennt den konkreten Provider.
- **Priorität:** mandatory

#### COMP-REQ-032: Graceful Degradation bei fehlender LLM-Konfiguration

- **Beschreibung:** Der LlmAdapter muss bei fehlender oder nicht erreichbarer LLM-Konfiguration einen strukturierten Fehler „LLM nicht konfiguriert" (Code: `LLM_NOT_CONFIGURED`) zurückgeben, anstatt eine Exception zu werfen. Das System bleibt ohne LLM-Zugang vollständig funktionsfähig — alle Kernoperationen (CRUD, Traceability, Baselines, Workflows) arbeiten normal weiter.
- **Abgeleitet von:** SYS-REQ-13 (SN-07: LLM als optionale Capability)
- **Zugeordnetes Subsystem:** C9:LlmAdapter (CapabilityRegistry)
- **Abnahmekriterium:** Integration-Test: Deployment ohne LLM-Konfiguration (.env: LLM_PROVIDER=none). `requirement.validate(id)` via MCP → JSON-Response `{error: {code: "LLM_NOT_CONFIGURED", message: "LLM provider not configured"}}`. `requirement.create(...)` → funktioniert normal. `requirement.decompose(id)` → Error `LLM_NOT_CONFIGURED`. Alle Nicht-LLM-Operationen funktionieren ohne Einschränkung. LLM-Provider nicht erreichbar (Timeout) → gleicher Fehler, kein Crash.
- **Priorität:** mandatory

---

### C10: PersistenceLayer (Datenhaltung)

---

#### COMP-REQ-035: Tenant-Isolation via Custom Django Manager

- **Beschreibung:** Die PersistenceLayer muss einen Custom Django Manager auf allen Entitäten implementieren, der jede Datenbankabfrage automatisch mit einem `tenant_id`-Filter versieht. Kein Query darf den Filter umgehen — auch nicht über Raw-SQL oder direkte ORM-Calls ohne Manager. Der aktive Tenant wird aus dem Request-Context (gesetzt durch AuthAndTenancy) bezogen.
- **Abgeleitet von:** SYS-REQ-15 (Ref: L2-TI-01, SN-08: Mandantenfähigkeit)
- **Zugeordnetes Subsystem:** C10:PersistenceLayer (CustomManager)
- **Abnahmekriterium:** Integration-Test: Erstelle 2 Tenants (T1, T2). Erstelle 5 Requirements in T1, 3 in T2. Request im Kontext T1 → `Requirement.objects.all()` liefert exakt 5. Raw-Query `SELECT * FROM requirements WHERE tenant_id=T2.id` via Manager → liefert 0 (Manager injiziert T1-Filter). Unit-Test: Mock Request ohne Tenant-Context → Query wirft Exception „Tenant context not set".
- **Priorität:** mandatory

#### COMP-REQ-048: PostgreSQL-Indizes für Hierarchie-, Graph- und Full-Text-Queries

- **Beschreibung:** Die PersistenceLayer muss PostgreSQL-Indizes für die drei performance-kritischen Query-Pfade bereitstellen: (1) Recursive CTE für Artifact-Hierarchie (BTree-Index auf `parent_id`), (2) Graph-Queries für TraceLinks (GIST/GIN-Index für Source/Target-Lookups), (3) Full-Text-Search (tsvector-Index auf Title+Description für Requirement, ArchitectureElement, TestCase).
- **Abgeleitet von:** SYS-REQ-20, SYS-REQ-01, SYS-REQ-03
- **Zugeordnetes Subsystem:** C10:PersistenceLayer
- **Abnahmekriterium:** Django-Migration enthält `CREATE INDEX` für: `artifact_parent_id_btree`, `tracelink_source_gist`, `tracelink_target_gist`, `requirement_tsvector`, `architectureelement_tsvector`, `testcase_tsvector`. EXPLAIN ANALYZE für Tree-Query (500 Artefakte) zeigt Index-Scan statt Seq-Scan. EXPLAIN ANALYZE für Full-Text-Search (10.000 Items) zeigt tsvector-Index-Nutzung.
- **Priorität:** mandatory

---

### C11: AuthAndTenancy (Auth-Middleware)

---

#### COMP-REQ-025: Rollenbasierte Zugriffskontrolle (4 Rollen)

- **Beschreibung:** Die AuthAndTenancy-Komponente muss vier Rollen (Admin, Editor, Viewer, Approver) auf Workspace-Ebene verwalten. Die Berechtigungsprüfung erfolgt pro Operation und Ressource: Admin hat Vollzugriff, Editor darf CRUD auf Requirements/ArchitectureElements/TestCases, Viewer hat nur Lesezugriff, Approver darf Workflow-Transitionen auslösen, die die Approver-Rolle erfordern. Viewer darf keine schreibenden Operationen ausführen.
- **Abgeleitet von:** SYS-REQ-10 (SN-05: Konfigurierbarer Item-Lifecycle)
- **Zugeordnetes Subsystem:** C11:AuthAndTenancy
- **Abnahmekriterium:** Unit-Test: Nutzer mit Rolle Viewer versucht `POST /api/v1/requirements/` → 403 Forbidden. Nutzer mit Rolle Editor versucht `POST /requirements/{id}/transition` mit Transition die Approver erfordert → 403. Nutzer mit Rolle Approver versucht dieselbe Transition → 200 OK. Admin kann alle Operationen ausführen.
- **Priorität:** mandatory

#### COMP-REQ-026: Approver-Rolle nur im Extended-Preset

- **Beschreibung:** Die AuthAndTenancy-Komponente muss die Approver-Rolle nur im Extended-Preset aktivieren. In Workspaces im Minimal- oder Standard-Preset ist die Approver-Rolle nicht zuweisbar und Transitionen, die `allowed_roles=["approver"]` erfordern, sind nicht ausführbar.
- **Abgeleitet von:** SYS-REQ-10 (SYS-REQ-07: Configurable-Rigor-Presets)
- **Zugeordnetes Subsystem:** C11:AuthAndTenancy
- **Abnahmekriterium:** Unit-Test: Workspace im Standard-Preset → `assign_role(user, "approver")` → Fehler „Approver role not available in Standard preset". Workspace im Extended-Preset → `assign_role(user, "approver")` → OK. Transition mit allowed_roles=[„approver"] im Standard-Preset → Fehler „Role not available in current preset".
- **Priorität:** mandatory

#### COMP-REQ-036: Tenant-Extraktion aus Authentifizierungstoken

- **Beschreibung:** Die AuthAndTenancy-Komponente muss bei jeder API-Anfrage (REST und MCP) den aktiven Tenant aus dem Authentifizierungstoken (Bearer Token / API Key) extrahieren und in den Request-Context setzen. Der Tenant wird an die PersistenceLayer (Custom Manager) weitergegeben, sodass alle Queries automatisch gefiltert werden.
- **Abgeleitet von:** SYS-REQ-15 (SN-08: Mandantenfähigkeit)
- **Zugeordnetes Subsystem:** C11:AuthAndTenancy
- **Abnahmekriterium:** Integration-Test: API-Key gehört zu Tenant T1 → Request-Kontext enthält `tenant_id=T1.id`. Alle nachfolgenden DB-Queries filtern nach T1. API-Key ungültig → 401 Unauthorized. API-Key ohne Tenant-Zuordnung (Fehlerfall) → 500 mit klarer Fehlermeldung „Tenant resolution failed".
- **Priorität:** mandatory

---

### C12: AuditLog (Änderungshistorie)

---

#### COMP-REQ-027: Append-Only Audit-Log für alle Schreiboperationen

- **Beschreibung:** Der AuditLog muss alle schreibenden Operationen (Create, Update, Delete) auf Requirements, ArchitectureElements, TestCases und TraceLinks als append-only Log persistieren. Jeder Eintrag enthält: Akteur (User-ID oder Agent-Client-ID), Operation (create/update/delete), Entitäts-Typ, Entitäts-ID, Zeitstempel. Der AuditLog wird von der ApplicationService-Komponente nach jeder erfolgreichen Schreiboperation befüllt.
- **Abgeleitet von:** SYS-REQ-11 (SN-11: Vollständiger Audit-Trail)
- **Zugeordnetes Subsystem:** C12:AuditLog
- **Abnahmekriterium:** Integration-Test: Erstelle Requirement → AuditLog-Eintrag: `{actor: user_id, operation: "create", entity_type: "requirement", entity_id: req_id, timestamp: T1}`. Update Requirement → Eintrag: `{operation: "update", ...}`. Delete Requirement → Eintrag: `{operation: "delete", ...}`. Versuch, einen AuditLog-Eintrag zu ändern → DB-Constraint-Fehler oder Exception. AuditLog-Query via `GET /api/v1/audit-log?entity_id=X` → alle Einträge für Entität X.
- **Priorität:** mandatory

#### COMP-REQ-028: MCP-Audit-Log mit Agent-Identität und API-Key

- **Beschreibung:** Der AuditLog muss bei MCP-Schreiboperationen zusätzlich zur User-ID die Agent-Client-Identität (Client-Name/Version) und den verwendeten API-Key (gehashed) erfassen. Dies ermöglicht die Unterscheidung zwischen manuellen Änderungen (via REST/UI) und agentengesteuerten Änderungen (via MCP).
- **Abgeleitet von:** SYS-REQ-11, SYS-REQ-05 (SN-11: Audit-Trail für Agenten)
- **Zugeordnetes Subsystem:** C12:AuditLog
- **Abnahmekriterium:** Integration-Test: AI-Agent ruft via MCP `requirement.create(...)` mit API-Key „ak_test123" und Client-Header „claude-code/1.0" auf → AuditLog-Eintrag: `{actor: user_id, actor_type: "agent", client_name: "claude-code/1.0", api_key_hash: "sha256:abc...", operation: "create", source: "mcp"}`. Manueller Nutzer via REST → Eintrag: `{actor_type: "user", source: "rest", client_name: null}`.
- **Priorität:** mandatory

---

### Deployment (System-Level)

---

#### COMP-REQ-043: Docker-Compose-Deployment mit drei Services

- **Beschreibung:** Das System muss vollständig via Docker Compose deploybar sein — drei Services: Backend (Django), Frontend (React/Node), Datenbank (PostgreSQL). Ein einziger Befehl `docker-compose up` startet eine produktionsfähige Instanz. Alle Konfigurationen (LLM-API-Key, DB-Credentials, Secret Key) erfolgen über Umgebungsvariablen (.env-Datei). Keine externen Cloud-Abhängigkeiten zur Laufzeit.
- **Abgeleitet von:** SYS-REQ-18 (SN-06: Self-Hosted Deployment)
- **Zugeordnetes Subsystem:** Deployment (system-level, alle Container)
- **Abnahmekriterium:** Auf einem frischen Docker-Host: `docker-compose up -d` → alle 3 Container starten erfolgreich. `curl http://localhost:3000` → React-UI erreichbar. `curl http://localhost:8000/api/v1/schema/` → OpenAPI-Spec erreichbar. PostgreSQL ist nur intern (Docker-Network) erreichbar, nicht exponiert. `.env`-Datei mit `LLM_API_KEY`, `DB_PASSWORD`, `SECRET_KEY` → alle von Backend und Frontend korrekt eingelesen.
- **Priorität:** mandatory

---

### C1: ReactFrontend — i18n (ergänzend zu COMP-REQ-39..42)

---

#### COMP-REQ-037: Frontend-i18n mit react-i18next (DE/EN)

- **Beschreibung:** Das ReactFrontend muss alle UI-Texte über react-i18next in Deutsch und Englisch bereitstellen. Jeder UI-String hat einen Translation-Key in beiden Sprachdateien (de.json, en.json). Die Sprache ist pro Nutzer-Präferenz umschaltbar (Profil-Setting oder Browser-Sprache als Default). Fehlende Translation-Keys werden als Build-Fehler behandelt (Lint-Regel im CI).
- **Abgeleitet von:** SYS-REQ-16 (SN-09: Zweisprachige Benutzeroberfläche)
- **Zugeordnetes Subsystem:** C1:ReactFrontend
- **Abnahmekriterium:** UI-Sprache auf Deutsch → alle Labels, Buttons, Platzhalter, Bestätigungstexte in Deutsch. Sprache auf Englisch → alle Texte in Englisch. CI-Pipeline: Füge neuen UI-String hinzu ohne DE-Translation → Build schlägt fehl mit „Missing translation key: xyz in de.json". Sprachwechsel während der Session → UI aktualisiert ohne Reload.
- **Priorität:** mandatory

---

### C2: RestApiAdapter — i18n (ergänzend zu COMP-REQ-13..15)

---

#### COMP-REQ-038: Backend-Fehlermeldungen i18n (DE/EN)

- **Beschreibung:** Der RestApiAdapter muss alle API-Fehlermeldungen (Validation-Errors, Permission-Denied, Not-Found, etc.) in Deutsch und Englisch bereitstellen. Die Sprache wird über den `Accept-Language`-Header des Requests bestimmt (Fallback: Englisch). Die Übersetzung erfolgt über ein zentrales i18n-Modul (Django gettext / python-babel). Fehlende Translation-Keys sind Build-Fehler (Lint-Regel).
- **Abgeleitet von:** SYS-REQ-16 (SN-09: Zweisprachige Benutzeroberfläche)
- **Zugeordnetes Subsystem:** C2:RestApiAdapter
- **Abnahmekriterium:** API-Request mit `Accept-Language: de` und ungültigem Body → Fehlermeldung auf Deutsch (z.B. „Feld 'title' ist ein Pflichtfeld"). Derselbe Request mit `Accept-Language: en` → „Field 'title' is required". Request ohne Header → Englisch als Fallback. CI-Pipeline: Neue Fehlermeldung ohne DE-Translation → Build-Fehler.
- **Priorität:** mandatory

---

## Offene Punkte (aus L1 übernommen)

| OP-ID | Beschreibung | Einfluss auf COMP-REQs | Status |
|-------|-------------|----------------------|--------|
| OP-01 | **LLM-Capability-Scope v1:** Welche der vier LLM-Capabilities (Generierung, Validierung, Decomposition, Konsistenz-Checks) werden in v1 operativ implementiert? Empfehlung: Validierung + Decomposition. | COMP-REQ-031 (LlmAdapter): Die `LlmCapabilityInterface` muss alle vier Operationen als Plugin-Interface definieren, aber nur `validate_artifact` und `decompose_requirement` werden in v1 mit Provider-Implementierungen ausgeliefert. `check_consistency` und Generierung sind als leere Plugin-Slots vorbereitet. | Offen — Config-Entscheidung |
| OP-02 | **Preset-Downgrade-Semantik:** Was passiert mit Baselines, Approved-Items und Workflows beim Wechsel auf eine niedrigere SE-Stufe (z.B. Extended → Standard)? | COMP-REQ-018 (PresetPolicyService): v1-Default ist „Block-Downgrade solange inkompatible Items existieren". Endgültige Semantik muss vor Implementierung entschieden werden. Alternative: „Soft-Downgrade mit Warnung und Freeze". | Offen — Semantik-Entscheidung |
| OP-03 | **Workflow-Wechsel-Semantik:** Was passiert mit Items in States, die nach einer WorkflowDefinition-Änderung nicht mehr existieren? | COMP-REQ-024 (WorkflowMigrationHandler): v1-Default ist „Block-Wechsel solange Items im verwaisten State sind". Endgültige Semantik muss vor Implementierung entschieden werden. Alternative: „Auto-Migration auf nächstliegenden neuen State". | Offen — Semantik-Entscheidung |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl COMP-REQs | 47 |
| SYS-REQ-Abdeckung | 20/20 (100%) |
| Subsystem-Abdeckung | 12/12 Komponenten + Deployment |
| Mandatory | 45 |
| Should-Have | 2 (COMP-REQ-024, COMP-REQ-018) |
| Nice-to-Have | 0 |
| Offene Punkte | 3 (OP-01, OP-02, OP-03) |

### COMP-REQ-Verteilung nach Subsystem

| Subsystem | Anzahl COMP-REQs |
|-----------|-----------------|
| C1: ReactFrontend | 5 (COMP-REQ-037, 039, 040, 041, 042) |
| C2: RestApiAdapter | 4 (COMP-REQ-013, 014, 015, 038) |
| C3: McpServer | 4 (COMP-REQ-009, 010, 011, 012) |
| C4: ApplicationService | 10 (COMP-REQ-001, 002, 003, 007, 029, 043, 044, 045, 046, 047) |
| C5: WorkflowEngine | 4 (COMP-REQ-004, 022, 023, 024) |
| C6: BaselineService | 3 (COMP-REQ-019, 020, 021) |
| C7: TraceabilityEngine | 3 (COMP-REQ-005, 006, 030) |
| C8: PresetConfigEngine | 5 (COMP-REQ-016, 017, 018, 033, 034) |
| C9: LlmAdapter | 2 (COMP-REQ-031, 032) |
| C10: PersistenceLayer | 2 (COMP-REQ-035, 048) |
| C11: AuthAndTenancy | 3 (COMP-REQ-025, 026, 036) |
| C12: AuditLog | 2 (COMP-REQ-027, 028) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-17*
*Nächster Schritt: Übergabe an se-critic für Quality-Gate-Validierung*
