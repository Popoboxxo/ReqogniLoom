# ReqFlow — L3 Component-Unit Requirements

> Status: ENTWURF | Erstellt: 2026-06-17 | Quelle: REQUIREMENTS_L2.md + architecture-elements.md + system-overview.md
> Sprache: Deutsch (Beschreibungen), English (IDs, Code-Namen).

---

## 1. Übersicht

Dieses Dokument definiert die **L3 Component-Unit Requirements (UNIT-REQ)** für die fünf kritischsten Architecture Elements der ReqFlow-Plattform. Jede UNIT-REQ ist von genau einer L2 COMP-REQ abgeleitet und auf genau eine implementierbare Code-Unit (Klasse, Modul, Funktion) abbildbar.

### Abgedeckte Architecture Elements

| AE | Name | Priorität | COMP-REQs | UNIT-REQs |
|----|------|-----------|-----------|-----------|
| AE-004 | ApplicationService | P0 | 9 (COMP-REQ-043 übersprungen) | 25 |
| AE-003 | McpServer | P0 | 4 | 22 |
| AE-005 | WorkflowEngine | P1 | 4 | 14 |
| AE-006 | BaselineService | P1 | 3 | 10 |
| AE-009 | LlmAdapter | P2 | 2 | 10 |
| **Gesamt** | | | **22** | **81** |

### Traceability-Prinzip

Jede UNIT-REQ trägt eine vollständige, lückenlose Traceability-Kette:

```
SN-XX → SYS-REQ-XX → COMP-REQ-XXX → UNIT-REQ-XXX
```

Die Kette ist rückwärts-traceierbar: Jeder Stakeholder-Need lässt sich bis zu einer konkreten, testbaren Code-Unit zurückverfolgen.

### ID-Schema

- `UNIT-REQ-001` bis `UNIT-REQ-081`, fortlaufend nummeriert
- Gruppierung nach AE (AE-004 beginnend, nach Priorität absteigend)
- Innerhalb jedes AE: Sub-Komponenten-Reihenfolge gemäß system-overview.md §4

### Hinweis zu COMP-REQ-043

COMP-REQ-043 (Docker-Compose-Deployment) ist auf System-Level angesiedelt und hat keine Sub-Komponenten-Zerlegung in der L2-Whitebox. Diese COMP-REQ wird für L3 übersprungen.

---

## 2. AE-004: ApplicationService

> **Typ:** Service | **Priorität:** P0 | **SYS-REQs:** SYS-REQ-01, 02, 04, 12, 19, 20
>
> Der ApplicationService ist die zentrale Domain-Service-Fassade. Er ist nach Use-Case-Gruppen (Subservices) partitioniert und orchestriert die untergeordneten Domain-Services.

---

### 2.1 ArtifactService

> **Zuständigkeit:** Artifact-Hierarchie-CRUD, Zyklus-Prüfung, Tree-Queries
> **COMP-REQs:** COMP-REQ-001, COMP-REQ-002

---

#### UNIT-REQ-001: Zyklus-Erkennungsalgorithmus (DFS-basiert)

- **Beschreibung:** Die Klasse `CycleDetector` implementiert einen DFS-basierten Algorithmus, der beim Setzen des `parent`-Felds eines Artifacts prüft, ob ein Pfad vom Zielknoten zurück zum Ursprungsknoten existiert. Der Algorithmus traversiert die parent-Kette ausgehend vom vorgeschlagenen Elternknoten aufwärts und erkennt sowohl direkte Selbstreferenzen (A.parent=A) als auch indirekte Zyklen (A→B→C→A). Bei Zyklus-Erkennung wird eine `CycleDetectedException` mit dem vollständigen Zykluspfad als Nachricht ausgelöst.
- **Abgeleitet von:** COMP-REQ-001 (Artifact-Hierarchy Cycle Detection)
- **Traceability:** SN-02 → SYS-REQ-01 → COMP-REQ-001 → UNIT-REQ-001
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArtifactService.CycleDetector.detect_cycle(artifact_id, proposed_parent_id)`
- **Abnahmekriterium:** Unit-Test: (a) Kette A→B→C, setze C.parent=A → `CycleDetectedException` mit Pfad „A→B→C→A". (b) Setze A.parent=A → `CycleDetectedException` mit „self-reference". (c) Setze C.parent=A (A ist Root) → `CycleDetectedException`. (d) Valider Parent-Change D.parent=B (kein Zyklus) → keine Exception, Rückgabe `False`.
- **Priorität:** mandatory

---

#### UNIT-REQ-002: Zyklus-Prüf-Hook vor Persistierung

- **Beschreibung:** Die Methode `ArtifactService.set_parent(artifact_id, new_parent_id)` ruft vor der Persistierung der parent-Änderung den `CycleDetector` auf. Bei erkanntem Zyklus wird die Operation abgebrochen und die `CycleDetectedException` an den Aufrufer (REST-Adapter oder MCP-Server) propagiert — die Datenbank-Transaktion wird zurückgerollt. Die Prüfung erfolgt innerhalb derselben Datenbank-Transaktion wie die Persistierung, um Race Conditions zu vermeiden.
- **Abgeleitet von:** COMP-REQ-001 (Artifact-Hierarchy Cycle Detection)
- **Traceability:** SN-02 → SYS-REQ-01 → COMP-REQ-001 → UNIT-REQ-002
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArtifactService.set_parent(artifact_id, new_parent_id)`
- **Abnahmekriterium:** Integration-Test: Erstelle Kette A→B→C. `set_parent(A.id, C.id)` → `CycleDetectedException`, A.parent in DB unverändert (B). `set_parent(D.id, B.id)` (valide) → A.parent=C in DB persistiert. Parallel-Test: Zwei gleichzeitige set_parent-Calls auf dasselbe Artifact → einer erfolgreich, anderer entweder erfolgreich oder CycleDetectedException (keine korrumpierte Hierarchie).
- **Priorität:** mandatory

---

#### UNIT-REQ-003: Recursive-CTE-Tree-Query

- **Beschreibung:** Die Methode `ArtifactService.get_tree(workspace_id, root_id=None)` nutzt eine PostgreSQL Recursive CTE (`WITH RECURSIVE`), um die vollständige Artefakt-Hierarchie eines Workspaces (oder ab einem optionalen Root-Knoten) als verschachtelte Struktur abzufragen. Das Ergebnis wird als Liste von `ArtifactTreeNode`-Objekten zurückgegeben, wobei jeder Knoten die Kindknoten als rekursiv verschachtelte Liste enthält. Die Abfrage nutzt den BTree-Index auf `parent_id` für effiziente Traversierung.
- **Abgeleitet von:** COMP-REQ-002 (Artifact Tree Query mit beliebiger Tiefe)
- **Traceability:** SN-03 → SYS-REQ-01 → COMP-REQ-002 → UNIT-REQ-003
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArtifactService.get_tree(workspace_id, root_id=None)`
- **Abnahmekriterium:** Integration-Test: Erstelle 3-stufige Hierarchie (A→B→C, A→D). `get_tree(workspace_id)` → Ergebnis enthält A als Root mit Kindern [B, D], B hat Kind [C]. `get_tree(workspace_id, root_id=B)` → Ergebnis enthält nur B mit Kind [C]. Performance-Test: 500 Artefakte in 5 Ebenen → Antwortzeit ≤ 200ms (p95).
- **Priorität:** mandatory

---

#### UNIT-REQ-004: Tree-Node-Struktur und Serialisierung

- **Beschreibung:** Die Datenklasse `ArtifactTreeNode` repräsentiert einen Knoten im Artefakt-Baum mit den Feldern `artifact` (Artifact-Instanz), `children` (Liste von `ArtifactTreeNode`), `depth` (Integer, relative Tiefe im Baum) und `path` (Liste von Artifact-IDs vom Root zu diesem Knoten). Die Methode `to_dict()` serialisiert den Baum als rekursives JSON-Objekt. Die Klasse wird von `get_tree()` zurückgegeben und von REST- und MCP-Adaptern für die Response-Serialisierung genutzt.
- **Abgeleitet von:** COMP-REQ-002 (Artifact Tree Query mit beliebiger Tiefe)
- **Traceability:** SN-03 → SYS-REQ-01 → COMP-REQ-002 → UNIT-REQ-004
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArtifactService.ArtifactTreeNode`
- **Abnahmekriterium:** Unit-Test: Erstelle `ArtifactTreeNode` mit 2 Ebenen. `to_dict()` → JSON mit verschachtelter `children`-Liste, `depth`-Feld korrekt (0 für Root, 1 für Kinder), `path`-Feld enthält korrekte ID-Sequenz. Leerer Baum (keine Artefakte) → leere Liste.
- **Priorität:** mandatory

---

### 2.2 RequirementService

> **Zuständigkeit:** Requirement-CRUD, Workflow-Initialisierung, change_reason-Validierung
> **COMP-REQs:** COMP-REQ-003

---

#### UNIT-REQ-005: Requirement-Erstellung mit Workflow-Initialisierung

- **Beschreibung:** Die Methode `RequirementService.create_requirement(title, description, category, artifact_id, priority=None, tags=None)` erzeugt ein neues Requirement im initialen WorkflowState (gemäß der aktiven WorkflowDefinition des Workspaces). Der initiale State wird durch Aufruf von `WorkflowEngine.initialize_workflow_state(item_type="requirement", workspace_id)` ermittelt. Das Requirement wird mit `version=1` und den Audit-Feldern `created_by` (aus Request-Kontext) und `created_at` (aktueller Zeitstempel) persistiert.
- **Abgeleitet von:** COMP-REQ-003 (Requirement CRUD mit Workflow-Integration)
- **Traceability:** SN-02 → SYS-REQ-02 → COMP-REQ-003 → UNIT-REQ-005
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `RequirementService.create_requirement(title, description, category, artifact_id, ...)`
- **Abnahmekriterium:** Unit-Test: `create_requirement("Login", "User can login", "Functional", artifact_id)` → Requirement mit `workflow_state.key="draft"`, `version=1`, `created_by=user_id`. Minimal-Preset → initialer State „draft". Extended-Preset → initialer State „draft" (gemäß Extended-WorkflowDefinition).
- **Priorität:** mandatory

---

#### UNIT-REQ-006: Requirement-Update mit change_reason-Validierung

- **Beschreibung:** Die Methode `RequirementService.update_requirement(requirement_id, fields, change_reason=None)` aktualisiert die angegebenen Felder eines Requirements. Vor der Persistierung wird die PresetConfigEngine konsultiert: Im Extended-Preset ist `change_reason` ein Pflichtfeld — fehlt es, wird eine `ValidationError("change_reason required in Extended preset")` ausgelöst. Das Versions-Feld wird bei jedem erfolgreichen Update automatisch inkrementiert (Optimistic Locking). Die Änderung wird im AuditLog protokolliert.
- **Abgeleitet von:** COMP-REQ-003 (Requirement CRUD mit Workflow-Integration)
- **Traceability:** SN-02 → SYS-REQ-02 → COMP-REQ-003 → UNIT-REQ-006
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `RequirementService.update_requirement(requirement_id, fields, change_reason=None)`
- **Abnahmekriterium:** Unit-Test: (a) Extended-Preset, `update_requirement(id, {title: "neu"}, change_reason=None)` → `ValidationError`. (b) Extended-Preset mit `change_reason="Review-Feedback"` → Update erfolgreich, `version` inkrementiert. (c) Minimal-Preset ohne `change_reason` → Update erfolgreich. (d) Stale version (parallel update) → `OptimisticLockError`.
- **Priorität:** mandatory

---

#### UNIT-REQ-007: Requirement-Löschung mit TraceLink-Cascade

- **Beschreibung:** Die Methode `RequirementService.delete_requirement(requirement_id)` löscht ein Requirement und alle zugehörigen TraceLinks (sowohl Source- als auch Target-Position) in einer atomaren Datenbank-Transaktion. Vor der Löschung wird geprüft, ob das Requirement in einem terminalen WorkflowState ist oder ob der Nutzer die Berechtigung zum Löschen hat (RBAC-Check via AuthAndTenancy). Der Löschvorgang wird im AuditLog protokolliert.
- **Abgeleitet von:** COMP-REQ-003 (Requirement CRUD mit Workflow-Integration)
- **Traceability:** SN-02 → SYS-REQ-02 → COMP-REQ-003 → UNIT-REQ-007
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `RequirementService.delete_requirement(requirement_id)`
- **Abnahmekriterium:** Integration-Test: Erstelle Requirement A mit 3 TraceLinks (2 als Source, 1 als Target). `delete_requirement(A.id)` → Requirement A gelöscht, alle 3 TraceLinks gelöscht, verbleibende Requirements unverändert. AuditLog enthält Eintrag `{operation: "delete", entity_type: "requirement", entity_id: A.id}`. Viewer-Rolle versucht Löschung → `PermissionDenied`.
- **Priorität:** mandatory

---

### 2.3 ArchitectureService

> **Zuständigkeit:** ArchitectureElement-CRUD, Optimistic Locking, Versionierung
> **COMP-REQs:** COMP-REQ-007

---

#### UNIT-REQ-008: ArchitectureElement-Erstellung mit Typ-Validierung

- **Beschreibung:** Die Methode `ArchitectureService.create_architecture_element(title, description, element_type, workspace_id, artifact_id=None)` erzeugt ein neues ArchitectureElement. Der `element_type` wird gegen das Enum `(Component, Interface, Subsystem, Layer, Module)` validiert — ungültige Typen werden mit `ValidationError` abgelehnt. Das Element wird mit `version=1`, initialem WorkflowState und Audit-Feldern persistiert. Die optionale Verknüpfung zu einem Artifact wird als FK gesetzt.
- **Abgeleitet von:** COMP-REQ-007 (ArchitectureElement CRUD mit Versionierung)
- **Traceability:** SN-03 → SYS-REQ-04 → COMP-REQ-007 → UNIT-REQ-008
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArchitectureService.create_architecture_element(title, description, element_type, workspace_id, ...)`
- **Abnahmekriterium:** Unit-Test: `create_architecture_element("Auth Service", "...", "Component", ws_id)` → ArchitectureElement mit `version=1`, `element_type="Component"`, `workflow_state.key="draft"`. Ungültiger Typ „InvalidType" → `ValidationError`. Mit `artifact_id` → FK korrekt gesetzt. Ohne `artifact_id` → FK = null.
- **Priorität:** mandatory

---

#### UNIT-REQ-009: Optimistic-Locking-Versionierung

- **Beschreibung:** Die Methode `ArchitectureService.update_architecture_element(architecture_element_id, fields, expected_version)` implementiert Optimistic Locking: Das `version`-Feld wird bei jedem erfolgreichen Update automatisch inkrementiert. Der Aufrufer muss die erwartete Version (`expected_version`) übergeben. Stimmt diese nicht mit der aktuellen Version in der Datenbank überein, wird ein `OptimisticLockError` ausgelöst und die Transaktion zurückgerollt. Dies verhindert verlustfreie Parallel-Updates.
- **Abgeleitet von:** COMP-REQ-007 (ArchitectureElement CRUD mit Versionierung)
- **Traceability:** SN-03 → SYS-REQ-04 → COMP-REQ-007 → UNIT-REQ-009
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArchitectureService.update_architecture_element(id, fields, expected_version)`
- **Abnahmekriterium:** Unit-Test: Erstelle ArchitectureElement (version=1). `update(id, {title: "neu"}, expected_version=1)` → version=2. `update(id, {title: "neu2"}, expected_version=1)` (stale) → `OptimisticLockError`, title in DB unverändert „neu" (version=2). Parallel-Test: Zwei gleichzeitige Updates → eines erfolgreich, anderes `OptimisticLockError`.
- **Priorität:** mandatory

---

#### UNIT-REQ-010: ArchitectureElement-Löschung mit TraceLink-Cascade

- **Beschreibung:** Die Methode `ArchitectureService.delete_architecture_element(architecture_element_id)` löscht ein ArchitectureElement und alle zugehörigen TraceLinks in einer atomaren Transaktion. Vor der Löschung wird geprüft, ob das Element verknüpfte Requirements oder TestCases hat — diese TraceLinks werden mitgelöscht, die verknüpften Requirements/TestCases selbst bleiben erhalten. Der Löschvorgang wird im AuditLog protokolliert.
- **Abgeleitet von:** COMP-REQ-007 (ArchitectureElement CRUD mit Versionierung)
- **Traceability:** SN-03 → SYS-REQ-04 → COMP-REQ-007 → UNIT-REQ-010
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ArchitectureService.delete_architecture_element(id)`
- **Abnahmekriterium:** Integration-Test: Erstelle ArchitectureElement AE-1 mit 2 TraceLinks zu Requirements. `delete_architecture_element(AE-1.id)` → AE-1 gelöscht, 2 TraceLinks gelöscht, Requirements unverändert. AuditLog enthält Delete-Eintrag.
- **Priorität:** mandatory

---

### 2.4 TestService

> **Zuständigkeit:** TestCase-CRUD, Test-Typ-Verwaltung, Ausführungsstatus
> **COMP-REQs:** COMP-REQ-029

---

#### UNIT-REQ-011: TestCase-Erstellung mit Typ-Validierung

- **Beschreibung:** Die Methode `TestService.create_test_case(title, test_type, workspace_id, description=None)` erzeugt einen neuen TestCase. Der `test_type` wird gegen das Enum `(Unit, Integration, System, Acceptance)` validiert. Der TestCase wird mit initialem WorkflowState und Audit-Feldern persistiert. Die optionale direkte Verknüpfung mit einem Requirement (via `linked_req_id`) wird unterstützt — dabei wird automatisch ein TraceLink vom Typ `verifies` erzeugt.
- **Abgeleitet von:** COMP-REQ-029 (TestCase CRUD mit Test-Status-Verwaltung)
- **Traceability:** SN-03 → SYS-REQ-12 → COMP-REQ-029 → UNIT-REQ-011
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `TestService.create_test_case(title, test_type, workspace_id, ...)`
- **Abnahmekriterium:** Unit-Test: `create_test_case("Login-Test", "Integration", ws_id)` → TestCase mit `test_type="Integration"`, `workflow_state.key="draft"`. Ungültiger Typ „Performance" → `ValidationError`. Mit `linked_req_id=req_1` → TestCase + TraceLink `{source: tc_id, target: req_1, type: "verifies"}` erzeugt.
- **Priorität:** mandatory

---

#### UNIT-REQ-012: Test-Ausführungsstatus-Update

- **Beschreibung:** Die Methode `TestService.update_test_status(test_case_id, execution_status)` aktualisiert den Ausführungsstatus eines TestCases. Der Status wird gegen das Enum `(Passed, Failed, Not Run)` validiert. Die Änderung wird im AuditLog protokolliert und inkrementiert das Versions-Feld. Der Ausführungsstatus ist ein separates Feld (`execution_status`) und unabhängig vom WorkflowState.
- **Abgeleitet von:** COMP-REQ-029 (TestCase CRUD mit Test-Status-Verwaltung)
- **Traceability:** SN-03 → SYS-REQ-12 → COMP-REQ-029 → UNIT-REQ-012
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `TestService.update_test_status(test_case_id, execution_status)`
- **Abnahmekriterium:** Unit-Test: `create_test_case(...)` → `execution_status="Not Run"` (Default). `update_test_status(tc_id, "Passed")` → `execution_status="Passed"`. `update_test_status(tc_id, "InvalidStatus")` → `ValidationError`. AuditLog enthält Update-Eintrag.
- **Priorität:** mandatory

---

#### UNIT-REQ-013: TestCase-Query mit Filterung

- **Beschreibung:** Die Methode `TestService.query_test_cases(filters)` unterstützt die Filterung von TestCases nach `test_type`, `workspace_id`, `execution_status` und `workflow_state`. Die Filter sind kombinierbar (AND-Logik). Das Ergebnis wird als paginierte Liste zurückgegeben. Die Query nutzt die Tenant-Isolation des Custom Django Managers.
- **Abgeleitet von:** COMP-REQ-029 (TestCase CRUD mit Test-Status-Verwaltung)
- **Traceability:** SN-03 → SYS-REQ-12 → COMP-REQ-029 → UNIT-REQ-013
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `TestService.query_test_cases(filters)`
- **Abnahmekriterium:** Unit-Test: Erstelle 5 TestCases (2 Unit, 2 Integration, 1 System). `query_test_cases({test_type: "Unit"})` → 2 Ergebnisse. `query_test_cases({execution_status: "Passed"})` → nur TestCases mit Status Passed. Kombiniert: `query_test_cases({test_type: "Integration", workspace_id: ws_1})` → nur Integration-Tests aus ws_1.
- **Priorität:** mandatory

---

### 2.5 ExportService

> **Zuständigkeit:** JSON-/CSV-Export für alle Entitäten inkl. Terminologie-Metadatum
> **COMP-REQs:** COMP-REQ-044, COMP-REQ-045

---

#### UNIT-REQ-014: JSON-Export-Generator

- **Beschreibung:** Die Methode `ExportService.export_json(scope, scope_id)` erzeugt eine vollständige JSON-Datei mit allen Entitäten des angegebenen Scopes (Workspace oder einzelnes Artefakt). Der Export enthält Requirements, ArchitectureElements, TestCases und TraceLinks. Das aktive Terminologie-Profil wird als Top-Level-Metadatum `metadata.terminology_profile` eingebettet. Die Serialisierung nutzt Django REST Framework Serializer für konsistente Feldstruktur.
- **Abgeleitet von:** COMP-REQ-044 (Export in JSON und CSV)
- **Traceability:** SN-12 → SYS-REQ-19 → COMP-REQ-044 → UNIT-REQ-014
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ExportService.export_json(scope, scope_id)`
- **Abnahmekriterium:** Integration-Test: Workspace mit 10 Requirements, 3 ArchitectureElements, 5 TestCases, 8 TraceLinks. `export_json("workspace", ws_id)` → gültige JSON-Datei mit allen Entitäten und `{"metadata": {"terminology_profile": "dev_mode"}}`. Export von 1.000 Requirements in unter 5 Sekunden.
- **Priorität:** mandatory

---

#### UNIT-REQ-015: CSV-Export-Generator

- **Beschreibung:** Die Methode `ExportService.export_csv(scope, scope_id)` erzeugt eine CSV-Datei mit allen Entitäten des angegebenen Scopes. Jede Entitäts-Kategorie (Requirements, ArchitectureElements, TestCases, TraceLinks) wird in einem separaten Abschnitt der CSV-Datei exportiert, getrennt durch eine Abschnitts-Markierung. Das Terminologie-Profil wird als Kommentar-Zeile am Dateianfang eingebettet (`# terminology_profile: <profil_name>`). Die CSV-Datei ist UTF-8-kodiert und in Excel importierbar.
- **Abgeleitet von:** COMP-REQ-044 (Export in JSON und CSV)
- **Traceability:** SN-12 → SYS-REQ-19 → COMP-REQ-044 → UNIT-REQ-015
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ExportService.export_csv(scope, scope_id)`
- **Abnahmekriterium:** Integration-Test: `export_csv("workspace", ws_id)` → CSV-Datei mit Kommentar-Zeile `# terminology_profile: se_mode`, Header-Zeile und Datenzeilen für alle Entitäten. Datei in Excel importierbar (keine Encoding-Fehler). Trennzeichen: Komma. Felder mit Kommas: in Anführungszeichen.
- **Priorität:** mandatory

---

#### UNIT-REQ-016: Terminologie-Profil-Metadatum im Export

- **Beschreibung:** Die Methode `ExportService._get_terminology_metadata(workspace_id)` ruft das aktive Terminologie-Profil des Workspaces von der PresetConfigEngine ab und formatiert es als Metadatum-Diktat. Dieses Metadatum wird von `export_json()` als Top-Level-Feld und von `export_csv()` als Kommentar-Zeile in den Export eingebettet. Bei Profilwechsel (z.B. Dev-Modus → SE-Modus) liefert die Methode das aktualisierte Profil.
- **Abgeleitet von:** COMP-REQ-045 (Export mit Terminologie-Profil-Metadatum)
- **Traceability:** SN-10 → SYS-REQ-19 → COMP-REQ-045 → UNIT-REQ-016
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `ExportService._get_terminology_metadata(workspace_id)`
- **Abnahmekriterium:** Unit-Test: Workspace im SE-Modus → `_get_terminology_metadata(ws_id)` → `{"terminology_profile": "se_mode"}`. Nach Wechsel zu Dev-Modus → `{"terminology_profile": "dev_mode"}`. JSON-Export enthält Feld `metadata.terminology_profile`. CSV-Export enthält Kommentar-Zeile `# terminology_profile: se_mode`.
- **Priorität:** mandatory

---

### 2.6 SearchService

> **Zuständigkeit:** Volltextsuche über alle Artefakttypen, Filterung, Relevanz-Sortierung
> **COMP-REQs:** COMP-REQ-046, COMP-REQ-047

---

#### UNIT-REQ-017: PostgreSQL-Full-Text-Search-Executor

- **Beschreibung:** Die Methode `SearchService.search(query, types=None, workspace_id=None)` führt eine artefakttyp-übergreifende Volltextsuche über Requirements, ArchitectureElements und TestCases mittels PostgreSQL `tsvector`/`tsquery` durch. Die Suche durchsucht die Felder `title`, `description` und `tags`. Ergebnisse werden nach Relevanz (PostgreSQL `ts_rank`) sortiert und enthalten eine `artifact_type`-Annotation („requirement", „architecture_element", „test_case"). Die Methode nutzt den tsvector-Index für Performance.
- **Abgeleitet von:** COMP-REQ-046 (Volltextsuche über alle Artefakttypen)
- **Traceability:** SN-01 → SYS-REQ-20 → COMP-REQ-046 → UNIT-REQ-017
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `SearchService.search(query, types=None, workspace_id=None)`
- **Abnahmekriterium:** Integration-Test: Erstelle 5 Requirements, 3 ArchitectureElements, 2 TestCases mit verschiedenen Titeln. `search("Authentifizierung")` → Ergebnisliste mit allen Matches, jeweils mit `artifact_type`-Feld, sortiert nach Relevanz. Performance-Test: 10.000 Items → Antwortzeit ≤ 500ms (p95).
- **Priorität:** mandatory

---

#### UNIT-REQ-018: Suchergebnis-Serialisierung mit Typ-Annotation

- **Beschreibung:** Die Datenklasse `SearchResult` repräsentiert ein einzelnes Suchergebnis mit den Feldern `entity_id` (UUID), `artifact_type` (Enum: requirement/architecture_element/test_case), `title` (String), `description_snippet` (String, gekürzt auf 200 Zeichen mit Hervorhebung des Suchbegriffs), `relevance_score` (Float, ts_rank-Wert) und `workspace_id` (UUID). Die Methode `SearchResult.to_dict()` serialisiert das Ergebnis für REST- und MCP-Responses.
- **Abgeleitet von:** COMP-REQ-046 (Volltextsuche über alle Artefakttypen)
- **Traceability:** SN-01 → SYS-REQ-20 → COMP-REQ-046 → UNIT-REQ-018
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `SearchService.SearchResult`
- **Abnahmekriterium:** Unit-Test: Erstelle `SearchResult` für ein Requirement. `to_dict()` → JSON mit `artifact_type: "requirement"`, `title`, `description_snippet` (max 200 Zeichen), `relevance_score` (Float > 0). Leere Suche → leere Ergebnisliste.
- **Priorität:** mandatory

---

#### UNIT-REQ-019: Artefakttyp-Filter

- **Beschreibung:** Die Methode `SearchService._apply_type_filter(queryset, types)` schränkt die Full-Text-Search-Ergebnisse auf die angegebenen Artefakttypen ein. Der `types`-Parameter ist eine Liste von Enum-Werten (z.B. `["requirement", "test_case"]`). Die Filterung erfolgt als SQL `WHERE artifact_type IN (...)` auf der kombinierten Ergebnismenge. Ungültige Typ-Werte werden mit `ValidationError` abgelehnt.
- **Abgeleitet von:** COMP-REQ-047 (Search Type-Filter und Workspace-Filter)
- **Traceability:** SN-01 → SYS-REQ-20 → COMP-REQ-047 → UNIT-REQ-019
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `SearchService._apply_type_filter(queryset, types)`
- **Abnahmekriterium:** Unit-Test: `search("test", types=["requirement"])` → nur Requirement-Treffer. `search("test", types=["requirement", "test_case"])` → nur Requirements und TestCases. `search("test", types=["invalid_type"])` → `ValidationError`.
- **Priorität:** mandatory

---

#### UNIT-REQ-020: Workspace-Filter für Suche

- **Beschreibung:** Die Methode `SearchService._apply_workspace_filter(queryset, workspace_id)` schränkt die Suchergebnisse auf den angegebenen Workspace ein. Der Filter wird auf der `workspace_id`-Spalte aller durchsuchten Entitäten angewendet. Die Tenant-Isolation wird zusätzlich durch den Custom Django Manager sichergestellt.
- **Abgeleitet von:** COMP-REQ-047 (Search Type-Filter und Workspace-Filter)
- **Traceability:** SN-01 → SYS-REQ-20 → COMP-REQ-047 → UNIT-REQ-020
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `SearchService._apply_workspace_filter(queryset, workspace_id)`
- **Abnahmekriterium:** Unit-Test: 2 Workspaces (ws_1, ws_2) mit jeweils 5 Requirements. `search("test", workspace_id=ws_1.id)` → nur Treffer aus ws_1. Kombiniert: `search("test", types=["requirement"], workspace_id=ws_1.id)` → nur Requirements aus ws_1.
- **Priorität:** mandatory

---

### 2.7 TraceLinkService

> **Zuständigkeit:** TraceLink-CRUD, Quell/Ziel-Validierung
> **COMP-REQs:** (implizit aus COMP-REQ-003, COMP-REQ-007, COMP-REQ-029 — TraceLink-Cascade bei Löschung)

---

#### UNIT-REQ-021: TraceLink-Erstellung mit Source/Target-Validierung

- **Beschreibung:** Die Methode `TraceLinkService.create_trace_link(source_type, source_id, target_type, target_id, link_type)` erzeugt einen neuen TraceLink. Die Validierung prüft: (1) Der `link_type` ist einer der sechs erlaubten Typen (parent-child, derives-from, satisfies, verifies, implements, refines), (2) Source- und Target-Entität existieren, (3) Source und Target gehören zum selben Tenant, (4) genau ein Source-Feld und genau ein Target-Feld sind befüllt. Bei Validierungsfehler wird `ValidationError` ausgelöst.
- **Abgeleitet von:** COMP-REQ-003 (TraceLink-Cascade-Aspekt)
- **Traceability:** SN-03 → SYS-REQ-03 → COMP-REQ-003 → UNIT-REQ-021
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `TraceLinkService.create_trace_link(source_type, source_id, target_type, target_id, link_type)`
- **Abnahmekriterium:** Unit-Test: `create_trace_link("requirement", req_1, "requirement", req_2, "derives-from")` → TraceLink erzeugt. `create_trace_link("requirement", req_1, "requirement", req_2, "invalid_type")` → `ValidationError`. Source aus Tenant-1, Target aus Tenant-2 → `ValidationError("Cross-tenant link not allowed")`.
- **Priorität:** mandatory

---

#### UNIT-REQ-022: TraceLink-Löschung (Bulk bei Entity-Delete)

- **Beschreibung:** Die Methode `TraceLinkService.delete_links_for_entity(entity_type, entity_id)` löscht alle TraceLinks, bei denen die angegebene Entität als Source oder Target beteiligt ist. Die Methode wird von `RequirementService.delete_requirement()`, `ArchitectureService.delete_architecture_element()` und `TestService.delete_test_case()` aufgerufen. Die Löschung erfolgt in derselben Transaktion wie die Entity-Löschung.
- **Abgeleitet von:** COMP-REQ-003 (TraceLink-Cascade-Aspekt)
- **Traceability:** SN-03 → SYS-REQ-03 → COMP-REQ-003 → UNIT-REQ-022
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `TraceLinkService.delete_links_for_entity(entity_type, entity_id)`
- **Abnahmekriterium:** Unit-Test: Erstelle Requirement A mit 3 TraceLinks (2 als Source, 1 als Target). `delete_links_for_entity("requirement", A.id)` → alle 3 TraceLinks gelöscht. Andere TraceLinks (ohne Beteiligung von A) unverändert. Rückgabe: Anzahl gelöschter Links = 3.
- **Priorität:** mandatory

---

### 2.8 BaselineFacade

> **Zuständigkeit:** Baseline-Lifecycle-Orchestrierung (delegiert an AE-006 BaselineService)
> **COMP-REQs:** (implizit aus COMP-REQ-019, COMP-REQ-020, COMP-REQ-021 — Orchestrierung)

---

#### UNIT-REQ-023: Baseline-Erstellungs-Orchestrierung

- **Beschreibung:** Die Methode `BaselineFacade.create_baseline(scope, name, workspace_id=None, artifact_id=None, description=None)` orchestriert die Baseline-Erstellung: (1) Konsultiert `PresetGate.is_scope_allowed()` zur Scope-Validierung, (2) delegiert an `ScopeResolver.resolve()` zur Ermittlung der betroffenen Item-IDs, (3) delegiert an `SnapshotBuilder.build()` zur atomaren Snapshot-Erstellung, (4) protokolliert im AuditLog. Alle Schritte erfolgen in einer Transaktion.
- **Abgeleitet von:** COMP-REQ-019 (Orchestrierungs-Aspekt)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-019 → UNIT-REQ-023
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `BaselineFacade.create_baseline(scope, name, ...)`
- **Abnahmekriterium:** Integration-Test: `create_baseline("project", "Sprint-3", workspace_id=ws_1)` → PresetGate geprüft → ScopeResolver aufgerufen → SnapshotBuilder aufgerufen → Baseline mit JSON-Snapshot persistiert. AuditLog-Eintrag vorhanden. Minimal-Preset → `ValidationError("Baselines not available in Minimal preset")`.
- **Priorität:** mandatory

---

### 2.9 WorkflowFacade

> **Zuständigkeit:** Workflow-State-Transitionen (delegiert an AE-005 WorkflowEngine)
> **COMP-REQs:** (implizit aus COMP-REQ-004, COMP-REQ-023 — Orchestrierung)

---

#### UNIT-REQ-024: Workflow-Transition-Orchestrierung

- **Beschreibung:** Die Methode `WorkflowFacade.transition(item_type, item_id, target_state, change_reason=None)` orchestriert einen Workflow-State-Übergang: (1) Konsultiert `TransitionValidator.validate()` zur Prüfung der Transition (erlaubt, Rolle, change_reason), (2) delegiert an `StateMutator.mutate()` zur atomaren State-Aktualisierung und History-Schreibung, (3) protokolliert im AuditLog. Bei Validierungsfehler wird die spezifische Fehlermeldung des TransitionValidators an den Aufrufer propagiert.
- **Abgeleitet von:** COMP-REQ-004 (Orchestrierungs-Aspekt)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-004 → UNIT-REQ-024
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `WorkflowFacade.transition(item_type, item_id, target_state, change_reason=None)`
- **Abnahmekriterium:** Integration-Test: `transition("requirement", req_1, "approved", change_reason="Review OK")` → TransitionValidator aufgerufen → StateMutator aufgerufen → State aktualisiert, History-Eintrag geschrieben. Ungültige Transition → Fehlermeldung vom TransitionValidator propagiert (z.B. „Role not allowed").
- **Priorität:** mandatory

---

### 2.10 PresetPolicyService

> **Zuständigkeit:** Validierung von Preset-Downgrades
> **COMP-REQs:** (implizit aus COMP-REQ-018 — Downgrade-Validierung als Subservice)

---

#### UNIT-REQ-025: Downgrade-Inkompabilitäts-Prüfung

- **Beschreibung:** Die Methode `PresetPolicyService.validate_downgrade(workspace_id, target_preset)` prüft beim Preset-Downgrade, ob inkompatible Daten im Workspace existieren. Die Prüfung umfasst: (1) Global-Baselines beim Wechsel von Extended → Standard, (2) Items im Approval-Gate-State (z.B. „approved" via Approver-Rolle) beim Wechsel von Extended → Minimal, (3) Erweiterte WorkflowStates die im Zielpreset nicht existieren. Bei Inkompabilität wird eine `DowngradeBlockedError` mit einer Liste der betroffenen Items und dem Grund zurückgegeben.
- **Abgeleitet von:** COMP-REQ-018 (Downgrade-Validierung als Subservice)
- **Traceability:** SN-02 → SYS-REQ-07 → COMP-REQ-018 → UNIT-REQ-025
- **Zugeordnetes AE:** AE-004 (ApplicationService)
- **Zugeordnete Unit:** `PresetPolicyService.validate_downgrade(workspace_id, target_preset)`
- **Abnahmekriterium:** Unit-Test: Workspace im Extended mit 1 Global-Baseline. `validate_downgrade(ws_id, "standard")` → `DowngradeBlockedError("1 global baseline exists")`. Nach Löschen der Baseline → Validierung erfolgreich. Workspace im Extended mit 3 Items im State „approved". `validate_downgrade(ws_id, "minimal")` → `DowngradeBlockedError("3 items in approval-gated state")`.
- **Priorität:** should-have

---

## 3. AE-003: McpServer

> **Typ:** Component | **Priorität:** P0 | **SYS-REQs:** SYS-REQ-05, SYS-REQ-20
>
> Der MCP Server implementiert 20 Tools in vier Gruppen plus eine Transport-/Dispatch-Schicht. Jede Tool-Gruppe ist ein dünner Translator: JSON-Schema-Validierung → ApplicationService-Aufruf → Ergebnis-Serialisierung.

---

### 3.1 McpTransport

> **Zuständigkeit:** Protokoll-Handler (stdio/SSE/HTTP), JSON-RPC-Dispatch
> **COMP-REQs:** (implizit aus COMP-REQ-009 bis COMP-REQ-012 — Transport-Schicht)

---

#### UNIT-REQ-026: JSON-RPC-Request-Dispatcher

- **Beschreibung:** Die Klasse `McpDispatcher` empfängt JSON-RPC-Requests, extrahiert den Tool-Namen aus dem `method`-Feld, validiert die Presence aller Pflicht-JSON-RPC-Felder (`jsonrpc`, `method`, `id`, `params`) und leitet den Request an die registrierte Tool-Handler-Klasse weiter. Unbekannte Tool-Namen werden mit einem JSON-RPC Error (-32601 „Method not found") beantwortet. Der Dispatcher unterstützt die gleichzeitige Registrierung mehrerer Tool-Gruppen.
- **Abgeleitet von:** COMP-REQ-009 (Transport-Aspekt)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-026
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `McpTransport.McpDispatcher.dispatch(jsonrpc_request)`
- **Abnahmekriterium:** Unit-Test: `dispatch({jsonrpc: "2.0", method: "requirement.get", id: 1, params: {id: "uuid"}})` → delegiert an RequirementTools.get(). `dispatch({method: "unknown.tool"})` → JSON-RPC Error -32601. `dispatch({method: "requirement.get"})` ohne `id` → JSON-RPC Error -32600 (Invalid Request).
- **Priorität:** mandatory

---

#### UNIT-REQ-027: Tool-Registry mit Gruppen-Registrierung

- **Beschreibung:** Die Klasse `ToolRegistry` verwaltet die Registrierung aller 20 MCP-Tools gruppiert nach Tool-Gruppe (RequirementTools, ArchitectureTools, TestTools, CrossCuttingTools). Jede Tool-Gruppe registriert ihre Tools mit Name, JSON-Schema (für Parameter-Validierung) und Handler-Referenz. Die Methode `get_handler(tool_name)` liefert den Handler für einen Tool-Namen. Die Methode `list_tools()` gibt alle registrierten Tools mit Name und Schema zurück (für MCP `tools/list`).
- **Abgeleitet von:** COMP-REQ-009 (Transport-Aspekt)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-027
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `McpTransport.ToolRegistry`
- **Abnahmekriterium:** Unit-Test: Registriere 4 Tool-Gruppen mit insgesamt 20 Tools. `list_tools()` → Liste mit 20 Einträgen, jeder mit `name` und `inputSchema`. `get_handler("requirement.get")` → Handler-Referenz. `get_handler("nonexistent")` → None. Doppelte Registrierung → Fehler.
- **Priorität:** mandatory

---

### 3.2 RequirementTools

> **Zuständigkeit:** 6 Requirement-MCP-Tools
> **COMP-REQs:** COMP-REQ-009

---

#### UNIT-REQ-028: requirement.get — Einzelabruf mit Kontext

- **Beschreibung:** Das Tool `requirement.get` validiert den Eingabeparameter `id` (UUID-Format), ruft `ApplicationService.RequirementService.get_requirement(id)` auf und serialisiert das Ergebnis als JSON mit allen Kontext-Feldern: Requirement-Daten, Traces (via TraceabilityEngine), Workflow-History (via WorkflowState.history) und Audit-Felder. Fehler (Requirement nicht gefunden) werden als JSON-RPC Error (-32602 „Requirement not found") zurückgegeben.
- **Abgeleitet von:** COMP-REQ-009 (Requirements-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-028
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `RequirementTools.RequirementGetTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({id: "valid_uuid"})` → JSON mit Requirement-Daten, Traces, Workflow-History. `execute({id: "nonexistent_uuid"})` → JSON-RPC Error -32602. `execute({id: "invalid_format"})` → JSON-RPC Error -32602 (Invalid params).
- **Priorität:** mandatory

---

#### UNIT-REQ-029: requirement.query — Filter-Query

- **Beschreibung:** Das Tool `requirement.query` validiert die Filter-Parameter (artifact_id, workflow_state, category, tags, priority) gegen ein JSON-Schema und delegiert an `RequirementService.query_requirements(filters)`. Das Ergebnis wird als JSON-Array serialisiert. Die Filter sind kombinierbar; leere Filter liefern alle Requirements des Workspace.
- **Abgeleitet von:** COMP-REQ-009 (Requirements-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-029
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `RequirementTools.RequirementQueryTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({filters: {category: "Functional", workflow_state: "draft"}})` → JSON-Array mit gefilterten Requirements. `execute({filters: {}})` → alle Requirements. `execute({filters: {invalid_field: "x"}})` → JSON-RPC Error -32602.
- **Priorität:** mandatory

---

#### UNIT-REQ-030: requirement.create — Erstellung mit Audit

- **Beschreibung:** Das Tool `requirement.create` validiert die Pflicht-Parameter (`title`, `description`, `type`, `artifact_id`) gegen ein JSON-Schema und delegiert an `RequirementService.create_requirement()`. Nach erfolgreicher Erstellung wird ein AuditLog-Eintrag mit der Agent-Identität (aus MCP-Request-Kontext) geschrieben. Die Response enthält die UUID des neuen Requirements.
- **Abgeleitet von:** COMP-REQ-009 (Requirements-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-030
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `RequirementTools.RequirementCreateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({title: "Login", description: "...", type: "Functional", artifact_id: "uuid"})` → JSON mit `{id: "new_uuid"}`. AuditLog-Eintrag mit `source: "mcp"`. `execute({title: ""})` → JSON-RPC Error -32602 („title is required").
- **Priorität:** mandatory

---

#### UNIT-REQ-031: requirement.update — Update mit change_reason

- **Beschreibung:** Das Tool `requirement.update` validiert die Parameter (`id`, `fields`, `change_reason`) und delegiert an `RequirementService.update_requirement()`. Im Extended-Preset wird das Vorhandensein von `change_reason` bereits auf Tool-Ebene geprüft (Fail-Fast), bevor die Delegation an den ApplicationService erfolgt.
- **Abgeleitet von:** COMP-REQ-009 (Requirements-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-031
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `RequirementTools.RequirementUpdateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({id: "uuid", fields: {title: "neu"}, change_reason: "Review"})` → Update erfolgreich. Extended-Preset ohne `change_reason` → JSON-RPC Error mit Hinweis „change_reason required". AuditLog-Eintrag mit MCP-Source.
- **Priorität:** mandatory

---

#### UNIT-REQ-032: requirement.decompose — Batch-Zerlegung

- **Beschreibung:** Das Tool `requirement.decompose` validiert die Parameter (`id`, optionale `children`) und delegiert an `RequirementService.decompose_requirement()`. Ohne `children`-Vorschlag wird der LlmAdapter zur automatischen Zerlegung konsultiert. Die erzeugten Kind-Requirements werden batch-weise persistiert, jeweils mit TraceLink `parent-child` und initialem WorkflowState. Die Response enthält alle erzeugten Kind-Requirements mit UUIDs.
- **Abgeleitet von:** COMP-REQ-009 (Requirements-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-009 → UNIT-REQ-032
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `RequirementTools.RequirementDecomposeTool.execute(params)`
- **Abnahmekriterium:** Integration-Test: `execute({id: parent_req_id, children: [{title: "Kind 1"}, {title: "Kind 2"}]})` → 2 Kind-Requirements erzeugt, je mit TraceLink `parent-child`. Ohne `children` + LLM konfiguriert → LLM-Aufruf, Kind-Vorschläge erzeugt. Ohne `children` + kein LLM → JSON-RPC Error `LLM_NOT_CONFIGURED`.
- **Priorität:** mandatory

---

#### UNIT-REQ-033: requirement.validate — LLM-gestützte Prüfung

- **Beschreibung:** Das Tool `requirement.validate` validiert den Eingabeparameter `id` und delegiert an `LlmAdapter.validate_artifact(id)`. Bei fehlender LLM-Konfiguration wird ein strukturierter JSON-RPC Error mit Code `LLM_NOT_CONFIGURED` zurückgegeben (keine Exception). Die Response enthält das strukturierte LLM-Ergebnis (Score + Verbesserungsvorschläge).
- **Abgeleitet von:** COMP-REQ-009 (Requirements-Tool-Gruppe)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-009 → UNIT-REQ-033
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `RequirementTools.RequirementValidateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: LLM konfiguriert → `execute({id: req_id})` → JSON mit `{score: 0.85, suggestions: [...]}`. Kein LLM → JSON-RPC Error `{code: "LLM_NOT_CONFIGURED", message: "LLM provider not configured"}`. Requirement nicht gefunden → JSON-RPC Error -32602.
- **Priorität:** mandatory

---

### 3.3 ArchitectureTools

> **Zuständigkeit:** 5 Architecture-MCP-Tools
> **COMP-REQs:** COMP-REQ-010

---

#### UNIT-REQ-034: architecture.get — Einzelabruf mit Kontext

- **Beschreibung:** Das Tool `architecture.get` validiert den Eingabeparameter `id` (UUID), ruft `ArchitectureService.get_architecture_element(id)` auf und serialisiert das Ergebnis mit Kontext-Feldern: Element-Daten, verknüpfte TraceLinks, Workflow-State. Fehler (nicht gefunden) als JSON-RPC Error.
- **Abgeleitet von:** COMP-REQ-010 (Architecture-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-010 → UNIT-REQ-034
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `ArchitectureTools.ArchitectureGetTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({id: "valid_uuid"})` → JSON mit ArchitectureElement-Daten, Traces, Workflow-State. Nicht gefunden → Error -32602.
- **Priorität:** mandatory

---

#### UNIT-REQ-035: architecture.query — Filter-Query

- **Beschreibung:** Das Tool `architecture.query` validiert die Filter-Parameter (element_type, workspace_id, artifact_id, tags) und delegiert an `ArchitectureService.query_architecture_elements(filters)`. Ergebnis als JSON-Array.
- **Abgeleitet von:** COMP-REQ-010 (Architecture-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-010 → UNIT-REQ-035
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `ArchitectureTools.ArchitectureQueryTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({filters: {element_type: "Component"}})` → JSON-Array mit Components. Leere Filter → alle ArchitectureElements.
- **Priorität:** mandatory

---

#### UNIT-REQ-036: architecture.create — Erstellung mit Audit

- **Beschreibung:** Das Tool `architecture.create` validiert die Pflicht-Parameter (`title`, `description`, `element_type`, `workspace_id`) und delegiert an `ArchitectureService.create_architecture_element()`. Schreibende Operation erzeugt AuditLog-Eintrag mit Agent-Identität.
- **Abgeleitet von:** COMP-REQ-010 (Architecture-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-010 → UNIT-REQ-036
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `ArchitectureTools.ArchitectureCreateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({title: "Auth Service", element_type: "Component", ...})` → JSON mit `{id: "new_uuid"}`. AuditLog mit `source: "mcp"`, `actor_type: "agent"`. Ungültiger `element_type` → Error -32602.
- **Priorität:** mandatory

---

#### UNIT-REQ-037: architecture.update — Update mit Versionierung

- **Beschreibung:** Das Tool `architecture.update` validiert die Parameter (`id`, `fields`, `change_reason`) und delegiert an `ArchitectureService.update_architecture_element()`. Die Optimistic-Locking-Prüfung erfolgt im ApplicationService; der Tool-Handler propagiert `OptimisticLockError` als JSON-RPC Error.
- **Abgeleitet von:** COMP-REQ-010 (Architecture-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-010 → UNIT-REQ-037
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `ArchitectureTools.ArchitectureUpdateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({id: "uuid", fields: {title: "neu"}})` → Update erfolgreich. Stale version → JSON-RPC Error „OptimisticLockError". AuditLog-Eintrag vorhanden.
- **Priorität:** mandatory

---

#### UNIT-REQ-038: architecture.link — TraceLink-Erstellung

- **Beschreibung:** Das Tool `architecture.link` validiert die Parameter (`architecture_id`, `target_id`, `target_type`, `link_type`) und delegiert an `TraceLinkService.create_trace_link()`. Der `target_type` bestimmt ob das Ziel ein Requirement, TestCase oder ArchitectureElement ist. Der `link_type` wird gegen die 6 erlaubten Typen validiert.
- **Abgeleitet von:** COMP-REQ-010 (Architecture-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-010 → UNIT-REQ-038
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `ArchitectureTools.ArchitectureLinkTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({architecture_id: "ae_1", target_id: "req_1", target_type: "requirement", link_type: "satisfies"})` → TraceLink erzeugt. Ungültiger `link_type` → Error -32602. Cross-Tenant → Error.
- **Priorität:** mandatory

---

### 3.4 TestTools

> **Zuständigkeit:** 5 Test-MCP-Tools
> **COMP-REQs:** COMP-REQ-011

---

#### UNIT-REQ-039: test.get — Einzelabruf mit Kontext

- **Beschreibung:** Das Tool `test.get` validiert den Eingabeparameter `id` und ruft `TestService.get_test_case(id)` auf. Serialisiert das Ergebnis mit Kontext: TestCase-Daten, verknüpfte Requirements (via TraceLinks), Workflow-State, Ausführungsstatus.
- **Abgeleitet von:** COMP-REQ-011 (Test-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-011 → UNIT-REQ-039
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `TestTools.TestGetTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({id: "valid_uuid"})` → JSON mit TestCase-Daten, verknüpften Requirements, `execution_status`. Nicht gefunden → Error -32602.
- **Priorität:** mandatory

---

#### UNIT-REQ-040: test.query — Filter-Query

- **Beschreibung:** Das Tool `test.query` validiert die Filter-Parameter (test_type, execution_status, workspace_id, linked_req_id) und delegiert an `TestService.query_test_cases(filters)`. Ergebnis als JSON-Array.
- **Abgeleitet von:** COMP-REQ-011 (Test-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-011 → UNIT-REQ-040
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `TestTools.TestQueryTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({filters: {test_type: "Unit", execution_status: "Failed"}})` → JSON-Array mit gefilterten TestCases. Leere Filter → alle TestCases.
- **Priorität:** mandatory

---

#### UNIT-REQ-041: test.create — Erstellung mit optionaler Verknüpfung

- **Beschreibung:** Das Tool `test.create` validiert die Parameter (`title`, `type`, optionale `linked_req_id`) und delegiert an `TestService.create_test_case()`. Bei Angabe von `linked_req_id` wird automatisch ein TraceLink vom Typ `verifies` erzeugt. AuditLog-Eintrag mit Agent-Identität.
- **Abgeleitet von:** COMP-REQ-011 (Test-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-011 → UNIT-REQ-041
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `TestTools.TestCreateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({title: "Login-Test", type: "Integration"})` → TestCase erzeugt. `execute({title: "Test", type: "Unit", linked_req_id: "req_1"})` → TestCase + TraceLink `verifies`. AuditLog mit `source: "mcp"`.
- **Priorität:** mandatory

---

#### UNIT-REQ-042: test.update — Status-Update nach Ausführung

- **Beschreibung:** Das Tool `test.update` validiert die Parameter (`id`, `fields` inkl. `execution_status`) und delegiert an `TestService.update_test_status()`. Der `execution_status` wird gegen das Enum (Passed/Failed/Not Run) validiert.
- **Abgeleitet von:** COMP-REQ-011 (Test-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-011 → UNIT-REQ-042
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `TestTools.TestUpdateTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({id: "tc_id", fields: {execution_status: "Passed"}})` → Status aktualisiert. `execute({id: "tc_id", fields: {execution_status: "Invalid"}})` → Error -32602.
- **Priorität:** mandatory

---

#### UNIT-REQ-043: test.link — Nachträgliche TraceLink-Erstellung

- **Beschreibung:** Das Tool `test.link` validiert die Parameter (`test_id`, `req_id`) und delegiert an `TraceLinkService.create_trace_link(source_type="test_case", source_id=test_id, target_type="requirement", target_id=req_id, link_type="verifies")`.
- **Abgeleitet von:** COMP-REQ-011 (Test-Tool-Gruppe)
- **Traceability:** SN-12 → SYS-REQ-05 → COMP-REQ-011 → UNIT-REQ-043
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `TestTools.TestLinkTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({test_id: "tc_1", req_id: "req_1"})` → TraceLink `{source: tc_1, target: req_1, type: "verifies"}` erzeugt. Bereits vorhanden → Error (Duplicate).
- **Priorität:** mandatory

---

### 3.5 CrossCuttingTools

> **Zuständigkeit:** 4 übergreifende Tools (Traceability, Search, Tree, Context)
> **COMP-REQs:** COMP-REQ-012

---

#### UNIT-REQ-044: traceability.query — Upstream/Downstream-Graph

- **Beschreibung:** Das Tool `traceability.query` validiert die Parameter (`artifact_id`, optionale `direction`) und delegiert an `TraceabilityEngine.query(artifact_id, direction)`. Die `direction` ist optional: „upstream", „downstream" oder „both" (Default). Das Ergebnis ist ein Graph mit Knoten (Entitäten) und Kanten (TraceLinks mit Typ-Annotation).
- **Abgeleitet von:** COMP-REQ-012 (Übergreifende Tools)
- **Traceability:** SN-03 → SYS-REQ-03 → COMP-REQ-012 → UNIT-REQ-044
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `CrossCuttingTools.TraceabilityQueryTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({artifact_id: "req_1", direction: "downstream"})` → JSON-Graph mit allen Downstream-Knoten und Kanten. `execute({artifact_id: "req_1"})` (Default: both) → vollständiger Graph. Artefakt nicht gefunden → Error -32602.
- **Priorität:** mandatory

---

#### UNIT-REQ-045: artifact.search — Typ-übergreifende Volltextsuche

- **Beschreibung:** Das Tool `artifact.search` validiert die Parameter (`query`, optionale `types`, optionale `workspace_id`) und delegiert an `SearchService.search()`. Das Ergebnis ist eine gemischte Liste mit Artefakttyp-Annotation, sortiert nach Relevanz.
- **Abgeleitet von:** COMP-REQ-012 (Übergreifende Tools)
- **Traceability:** SN-01 → SYS-REQ-20 → COMP-REQ-012 → UNIT-REQ-045
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `CrossCuttingTools.ArtifactSearchTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({query: "Auth"})` → gemischte Ergebnisliste über alle Typen. `execute({query: "Auth", types: ["requirement"]})` → nur Requirements. Performance: 10.000 Items ≤ 500ms.
- **Priorität:** mandatory

---

#### UNIT-REQ-046: artifact.get_tree — Hierarchie-Abruf

- **Beschreibung:** Das Tool `artifact.get_tree` validiert den optionalen Parameter `root_id` und delegiert an `ArtifactService.get_tree(workspace_id, root_id)`. Das Ergebnis ist eine verschachtelte JSON-Struktur der Artefakt-Hierarchie.
- **Abgeleitet von:** COMP-REQ-012 (Übergreifende Tools)
- **Traceability:** SN-03 → SYS-REQ-01 → COMP-REQ-012 → UNIT-REQ-046
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `CrossCuttingTools.ArtifactGetTreeTool.execute(params)`
- **Abnahmekriterium:** Unit-Test: `execute({root_id: "artifact_A"})` → JSON-Baum ab A. `execute({})` → vollständiger Workspace-Baum. Leerer Workspace → leeres Array.
- **Priorität:** mandatory

---

#### UNIT-REQ-047: workspace.get_context — Workspace-Metadaten

- **Beschreibung:** Das Tool `workspace.get_context` ruft den kompletten Workspace-Status ab: offene Requirements (im Initial-State ohne TraceLink), unverknüpfte TestCases, Coverage-Summary (Prozentsatz), aktives Preset, aktives Terminologie-Profil und aktive WorkflowDefinitions. Das Tool aggregiert Daten von PresetConfigEngine, TraceabilityEngine und WorkflowEngine. Es benötigt keinen Schreibzugriff und keine LLM-Konfiguration.
- **Abgeleitet von:** COMP-REQ-012 (Übergreifende Tools)
- **Traceability:** SN-01 → SYS-REQ-05 → COMP-REQ-012 → UNIT-REQ-047
- **Zugeordnetes AE:** AE-003 (McpServer)
- **Zugeordnete Unit:** `CrossCuttingTools.WorkspaceGetContextTool.execute(params)`
- **Abnahmekriterium:** Integration-Test: `execute({})` → JSON mit `{open_requirements: 5, unlinked_tests: 3, coverage: {total: 20, covered: 15, percentage: 75.0}, preset: "standard", terminology_profile: "dev_mode", workflow_definitions: [...]}`. Funktioniert ohne LLM-Konfiguration.
- **Priorität:** mandatory

---

## 4. AE-005: WorkflowEngine

> **Typ:** Service | **Priorität:** P1 | **SYS-REQs:** SYS-REQ-02, SYS-REQ-09
>
> Die WorkflowEngine verwaltet konfigurierbare Item-Lifecycles mit WorkflowDefinitions pro Item-Typ und Workspace, Transition-Validierung und append-only State-History.

---

### 4.1 WorkflowDefinitionStore

> **Zuständigkeit:** CRUD + Default-Templates pro Preset
> **COMP-REQs:** COMP-REQ-022

---

#### UNIT-REQ-048: Default-Workflow-Template-Generator (Minimal)

- **Beschreibung:** Die Methode `WorkflowDefinitionStore.create_default_definition(workspace_id, item_type, preset="minimal")` erzeugt die Default-WorkflowDefinition für das Minimal-Preset. States: `[draft, done]`. Transitions: `draft→done` und `done→draft`, beide mit `allowed_roles=["editor"]`, `requires_change_reason=false`. Die Definition wird als `is_default=true` markiert und persistiert.
- **Abgeleitet von:** COMP-REQ-022 (WorkflowDefinition-Verwaltung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-022 → UNIT-REQ-048
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowDefinitionStore.create_default_definition(workspace_id, item_type, preset="minimal")`
- **Abnahmekriterium:** Unit-Test: `create_default_definition(ws_id, "requirement", "minimal")` → WorkflowDefinition mit States `[draft, done]`, 2 Transitions, alle `allowed_roles=["editor"]`, `requires_change_reason=false`. `is_default=true`. Persistiert in DB.
- **Priorität:** mandatory

---

#### UNIT-REQ-049: Default-Workflow-Template-Generator (Standard)

- **Beschreibung:** Die Methode erzeugt die Default-WorkflowDefinition für das Standard-Preset. States: `[draft, approved, deprecated]`. Transitions: `draft→approved` (allowed_roles=["editor"], requires_change_reason=false), `approved→deprecated` (allowed_roles=["editor"]), `draft→deprecated` (allowed_roles=["editor"]).
- **Abgeleitet von:** COMP-REQ-022 (WorkflowDefinition-Verwaltung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-022 → UNIT-REQ-049
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowDefinitionStore.create_default_definition(workspace_id, item_type, preset="standard")`
- **Abnahmekriterium:** Unit-Test: `create_default_definition(ws_id, "requirement", "standard")` → States `[draft, approved, deprecated]`, 3 Transitions, alle für Editor erlaubt, kein change_reason-Pflicht.
- **Priorität:** mandatory

---

#### UNIT-REQ-050: Default-Workflow-Template-Generator (Extended)

- **Beschreibung:** Die Methode erzeugt die Default-WorkflowDefinition für das Extended-Preset. States: `[draft, in_review, approved, deprecated]`. Transitions: `draft→in_review` (allowed_roles=["editor"]), `in_review→approved` (allowed_roles=["approver"], requires_change_reason=true), `approved→deprecated` (allowed_roles=["editor", "approver"]), `draft→deprecated` (allowed_roles=["editor"]).
- **Abgeleitet von:** COMP-REQ-022 (WorkflowDefinition-Verwaltung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-022 → UNIT-REQ-050
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowDefinitionStore.create_default_definition(workspace_id, item_type, preset="extended")`
- **Abnahmekriterium:** Unit-Test: `create_default_definition(ws_id, "requirement", "extended")` → States `[draft, in_review, approved, deprecated]`, Transition `in_review→approved` mit `allowed_roles=["approver"]` und `requires_change_reason=true`.
- **Priorität:** mandatory

---

#### UNIT-REQ-051: Custom-WorkflowDefinition-CRUD

- **Beschreibung:** Die Methode `WorkflowDefinitionStore.create_custom_definition(workspace_id, item_type, name, states, transitions)` erzeugt eine benutzerdefinierte WorkflowDefinition (Extended-Preset). Die Validierung prüft: (1) Mindestens ein State ist als `is_initial=true` markiert, (2) alle in Transitions referenzierten States existieren in der States-Liste, (3) keine duplikaten Transitionen (gleiche from/to-Kombination). Die Methode `update_definition()` und `delete_definition()` sind ebenfalls implementiert.
- **Abgeleitet von:** COMP-REQ-022 (WorkflowDefinition-Verwaltung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-022 → UNIT-REQ-051
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowDefinitionStore.create_custom_definition(workspace_id, item_type, name, states, transitions)`
- **Abnahmekriterium:** Unit-Test: Custom Definition mit 4 States und 5 Transitions → erfolgreich. Kein initial-State → `ValidationError`. Transition referenziert nicht-existierenden State → `ValidationError`. Duplikate from/to → `ValidationError`.
- **Priorität:** mandatory

---

### 4.2 TransitionValidator

> **Zuständigkeit:** Prüft from→to, allowed_roles, requires_change_reason
> **COMP-REQs:** COMP-REQ-004

---

#### UNIT-REQ-052: Transition-Erlaubnis-Prüfung

- **Beschreibung:** Die Methode `TransitionValidator.validate_transition(workflow_definition, from_state, to_state)` prüft, ob die Transition `from_state → to_state` in der angegebenen WorkflowDefinition existiert. Ist die Transition nicht definiert, wird eine `TransitionNotAllowedError` mit der Nachricht „Transition from '{from_state}' to '{to_state}' is not allowed" ausgelöst.
- **Abgeleitet von:** COMP-REQ-004 (Workflow-Transition-Validierung)
- **Traceability:** SN-05 → SYS-REQ-02 → COMP-REQ-004 → UNIT-REQ-052
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `TransitionValidator.validate_transition(workflow_definition, from_state, to_state)`
- **Abnahmekriterium:** Unit-Test: Definition mit Transition draft→approved. `validate_transition(def, "draft", "approved")` → OK (keine Exception). `validate_transition(def, "draft", "deprecated")` (nicht definiert) → `TransitionNotAllowedError`.
- **Priorität:** mandatory

---

#### UNIT-REQ-053: Rollenberechtigungs-Prüfung

- **Beschreibung:** Die Methode `TransitionValidator.validate_role(transition, user_roles)` prüft, ob mindestens eine der Rollen des anfragenden Nutzers in den `allowed_roles` der Transition enthalten ist. Bei fehlender Berechtigung wird eine `RoleNotAllowedError` mit der Nachricht „Role not allowed for this transition. Required: {allowed_roles}" ausgelöst.
- **Abgeleitet von:** COMP-REQ-004 (Workflow-Transition-Validierung)
- **Traceability:** SN-05 → SYS-REQ-02 → COMP-REQ-004 → UNIT-REQ-053
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `TransitionValidator.validate_role(transition, user_roles)`
- **Abnahmekriterium:** Unit-Test: Transition mit `allowed_roles=["approver"]`. `validate_role(transition, ["editor"])` → `RoleNotAllowedError`. `validate_role(transition, ["approver"])` → OK. `validate_role(transition, ["editor", "approver"])` → OK (mindestens eine Rolle matcht).
- **Priorität:** mandatory

---

#### UNIT-REQ-054: Change-Reason-Pflichtprüfung

- **Beschreibung:** Die Methode `TransitionValidator.validate_change_reason(transition, change_reason)` prüft, ob bei Transitionen mit `requires_change_reason=true` ein nicht-leerer `change_reason` vorliegt. Bei fehlendem change_reason wird eine `ChangeReasonRequiredError` ausgelöst. Bei Transitionen ohne Pflicht ist die Prüfung optional (leerer change_reason erlaubt).
- **Abgeleitet von:** COMP-REQ-004 (Workflow-Transition-Validierung)
- **Traceability:** SN-05 → SYS-REQ-02 → COMP-REQ-004 → UNIT-REQ-054
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `TransitionValidator.validate_change_reason(transition, change_reason)`
- **Abnahmekriterium:** Unit-Test: Transition mit `requires_change_reason=true`. `validate_change_reason(transition, None)` → `ChangeReasonRequiredError`. `validate_change_reason(transition, "")` → `ChangeReasonRequiredError`. `validate_change_reason(transition, "Review OK")` → OK. Transition mit `requires_change_reason=false` → immer OK.
- **Priorität:** mandatory

---

#### UNIT-REQ-055: Kombinierte Validierungs-Pipeline

- **Beschreibung:** Die Methode `TransitionValidator.validate(workflow_definition, from_state, to_state, user_roles, change_reason)` führt alle drei Einzelprüfungen (Transition-Erlaubnis, Rollenberechtigung, Change-Reason-Pflicht) sequenziell in einer Pipeline aus. Die erste fehlschlagende Prüfung löst die entsprechende Exception aus (Fail-Fast). Bei erfolgreicher Validierung wird `True` zurückgegeben.
- **Abgeleitet von:** COMP-REQ-004 (Workflow-Transition-Validierung)
- **Traceability:** SN-05 → SYS-REQ-02 → COMP-REQ-004 → UNIT-REQ-055
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `TransitionValidator.validate(workflow_definition, from_state, to_state, user_roles, change_reason)`
- **Abnahmekriterium:** Integration-Test: Valider Übergang (draft→approved, Rolle=approver, change_reason vorhanden) → `True`. Transition nicht erlaubt → `TransitionNotAllowedError` (Rollen- und Change-Reason-Prüfung nicht erreicht). Rolle nicht erlaubt → `RoleNotAllowedError`. Change-Reason fehlt → `ChangeReasonRequiredError`.
- **Priorität:** mandatory

---

### 4.3 StateMutator

> **Zuständigkeit:** Persistiert State-Übergang atomar + schreibt History-Eintrag
> **COMP-REQs:** COMP-REQ-023

---

#### UNIT-REQ-056: Atomare State-Aktualisierung

- **Beschreibung:** Die Methode `StateMutator.mutate(workflow_state, to_state)` aktualisiert den `current_state` eines WorkflowState-Objekts atomar in einer Datenbank-Transaktion. Die Aktualisierung nutzt Optimistic Locking (version-Feld auf WorkflowState), um konkurrierende Mutationen zu erkennen. Bei erfolgreicher Mutation wird das version-Feld inkrementiert.
- **Abgeleitet von:** COMP-REQ-023 (WorkflowState History mit Audit-Trail)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-023 → UNIT-REQ-056
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `StateMutator.mutate(workflow_state, to_state)`
- **Abnahmekriterium:** Unit-Test: WorkflowState mit `current_state="draft"`. `mutate(ws, "approved")` → `current_state="approved"`, version inkrementiert. Konkurrierende Mutation (stale version) → `OptimisticLockError`, State unverändert.
- **Priorität:** mandatory

---

#### UNIT-REQ-057: Append-Only-History-Eintrag

- **Beschreibung:** Die Methode `StateMutator.write_history(workflow_state, from_state, to_state, user_id, change_reason=None)` schreibt einen History-Eintrag in das `history` JSON-Array des WorkflowState. Der Eintrag enthält: `from_state`, `to_state`, `transitioned_by` (User-ID), `transitioned_at` (UTC-Zeitstempel), `change_reason` (optional). Die History ist append-only: Versuche, bestehende Einträge zu修改n oder zu löschen, werden mit `HistoryImmutableError` abgelehnt.
- **Abgeleitet von:** COMP-REQ-023 (WorkflowState History mit Audit-Trail)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-023 → UNIT-REQ-057
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `StateMutator.write_history(workflow_state, from_state, to_state, user_id, change_reason)`
- **Abnahmekriterium:** Unit-Test: 3 aufeinanderfolgende Transitionen (draft→in_review→approved). `workflow_state.history` enthält 3 Einträge in korrekter Reihenfolge mit from/to, user, timestamp. Versuch, `history[0]` zu ändern → `HistoryImmutableError`. Versuch, `history` zu kürzen → `HistoryImmutableError`.
- **Priorität:** mandatory

---

#### UNIT-REQ-058: WorkflowState-Initialisierung

- **Beschreibung:** Die Methode `StateMutator.initialize_state(item_type, item_id, workflow_definition)` erzeugt einen neuen WorkflowState für ein Item mit dem initialen State der WorkflowDefinition (der State mit `is_initial=true`). Die `history` wird als leeres Array initialisiert. Die Methode wird von `RequirementService.create_requirement()` und `ArchitectureService.create_architecture_element()` aufgerufen.
- **Abgeleitet von:** COMP-REQ-023 (WorkflowState History mit Audit-Trail)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-023 → UNIT-REQ-058
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `StateMutator.initialize_state(item_type, item_id, workflow_definition)`
- **Abnahmekriterium:** Unit-Test: `initialize_state("requirement", req_id, wf_def)` → WorkflowState mit `current_state="draft"` (initial state der Definition), `history=[]`. WorkflowDefinition ohne initial-State → `ConfigurationError`.
- **Priorität:** mandatory

---

### 4.4 WorkflowMigrationHandler

> **Zuständigkeit:** Behandelt Items in verwaisten States bei Definition-Wechsel
> **COMP-REQs:** COMP-REQ-024

---

#### UNIT-REQ-059: Verwaiste-State-Erkennung

- **Beschreibung:** Die Methode `WorkflowMigrationHandler.find_orphaned_items(old_definition, new_definition)` identifiziert alle Items, deren `current_state` in der neuen WorkflowDefinition nicht mehr existiert. Die Methode vergleicht die State-Keys der alten und neuen Definition und queryt alle WorkflowState-Instanzen, deren `current_state` in der Differenzmenge liegt. Das Ergebnis ist eine Liste von `{item_type, item_id, orphaned_state}`.
- **Abgeleitet von:** COMP-REQ-024 (Workflow-Migration bei Definition-Änderung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-024 → UNIT-REQ-059
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowMigrationHandler.find_orphaned_items(old_definition, new_definition)`
- **Abnahmekriterium:** Unit-Test: Alte Definition mit States [draft, in_progress, approved]. Neue Definition mit States [draft, ready_for_review, approved]. 5 Items im State „in_progress". `find_orphaned_items(old, new)` → Liste mit 5 Einträgen, alle mit `orphaned_state="in_progress"`. Keine verwaisten Items → leere Liste.
- **Priorität:** should-have

---

#### UNIT-REQ-060: Migrations-Blockade bei verwaisten Items

- **Beschreibung:** Die Methode `WorkflowMigrationHandler.validate_migration(old_definition, new_definition)` ruft `find_orphaned_items()` auf und blockiert die Definition-Änderung, wenn verwaiste Items existieren. Die Blockade löst eine `MigrationBlockedError` mit der Nachricht „Workflow change blocked: {count} items in orphaned state '{state}'" aus, inklusive der vollständigen Liste betroffener Items.
- **Abgeleitet von:** COMP-REQ-024 (Workflow-Migration bei Definition-Änderung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-024 → UNIT-REQ-060
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowMigrationHandler.validate_migration(old_definition, new_definition)`
- **Abnahmekriterium:** Unit-Test: 5 Items im verwaisten State → `MigrationBlockedError("Workflow change blocked: 5 items in orphaned state 'in_progress'")`. Fehlermeldung enthält Liste der betroffenen Item-IDs. Nach Migration der Items (manuell auf „draft" gesetzt) → `validate_migration()` → OK (keine Exception).
- **Priorität:** should-have

---

#### UNIT-REQ-061: Definition-Änderung mit Migrations-Check

- **Beschreibung:** Die Methode `WorkflowMigrationHandler.apply_definition_change(definition, new_states, new_transitions)` orchestriert die Änderung einer WorkflowDefinition: (1) Lädt die alte Definition, (2) ruft `validate_migration()` auf, (3) bei Erfolg: aktualisiert States und Transitions der Definition. Die gesamte Operation erfolgt in einer Transaktion.
- **Abgeleitet von:** COMP-REQ-024 (Workflow-Migration bei Definition-Änderung)
- **Traceability:** SN-05 → SYS-REQ-09 → COMP-REQ-024 → UNIT-REQ-061
- **Zugeordnetes AE:** AE-005 (WorkflowEngine)
- **Zugeordnete Unit:** `WorkflowMigrationHandler.apply_definition_change(definition, new_states, new_transitions)`
- **Abnahmekriterium:** Integration-Test: Definition ohne verwaiste Items ändern → States und Transitions aktualisiert. Definition mit verwaisten Items ändern → `MigrationBlockedError`, Definition in DB unverändert (Transaktion zurückgerollt).
- **Priorität:** should-have

---

## 5. AE-006: BaselineService

> **Typ:** Service | **Priorität:** P1 | **SYS-REQs:** SYS-REQ-08
>
> Der BaselineService erstellt unveränderliche, benannte Baselines auf drei Scopes und stellt Diff-Vergleiche bereit.

---

### 5.1 ScopeResolver

> **Zuständigkeit:** Ermittelt betroffene Item-IDs/Versionen je Scope
> **COMP-REQs:** COMP-REQ-019

---

#### UNIT-REQ-062: Document-Scope-Resolver

- **Beschreibung:** Die Methode `ScopeResolver.resolve_document_scope(artifact_id)` ermittelt alle Item-IDs und Versionen für den Document-Scope: Das angegebene Artefakt, alle Nachkommen (via Recursive CTE), sowie alle Requirements, ArchitectureElements und TestCases, die mit diesen Artefakten verbunden sind. Das Ergebnis ist eine Liste von `{entity_type, entity_id, version}`.
- **Abgeleitet von:** COMP-REQ-019 (Baseline Scope-Auflösung und Snapshot-Erstellung)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-019 → UNIT-REQ-062
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `ScopeResolver.resolve_document_scope(artifact_id)`
- **Abnahmekriterium:** Integration-Test: Artifact A mit 2 Kindern (B, C). A hat 3 Requirements, B hat 2, C hat 1. `resolve_document_scope(A.id)` → Liste mit A, B, C + 6 Requirements + zugehörige TestCases/ArchitectureElements. Artifact ohne Kinder → nur das Artifact + zugehörige Items.
- **Priorität:** mandatory

---

#### UNIT-REQ-063: Project-Scope-Resolver

- **Beschreibung:** Die Methode `ScopeResolver.resolve_project_scope(workspace_id)` ermittelt alle Item-IDs und Versionen für den Project-Scope: Alle Artefakte, Requirements, ArchitectureElements und TestCases des angegebenen Workspaces.
- **Abgeleitet von:** COMP-REQ-019 (Baseline Scope-Auflösung und Snapshot-Erstellung)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-019 → UNIT-REQ-063
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `ScopeResolver.resolve_project_scope(workspace_id)`
- **Abnahmekriterium:** Integration-Test: Workspace mit 10 Requirements, 3 ArchitectureElements, 5 TestCases. `resolve_project_scope(ws_id)` → Liste mit 18 Einträgen (alle Items mit Versionen). Workspace ohne Items → leere Liste.
- **Priorität:** mandatory

---

#### UNIT-REQ-064: Global-Scope-Resolver

- **Beschreibung:** Die Methode `ScopeResolver.resolve_global_scope(tenant_id)` ermittelt alle Item-IDs und Versionen für den Global-Scope: Alle Artefakte, Requirements, ArchitectureElements und TestCases aller Workspaces des angegebenen Tenants.
- **Abgeleitet von:** COMP-REQ-019 (Baseline Scope-Auflösung und Snapshot-Erstellung)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-019 → UNIT-REQ-064
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `ScopeResolver.resolve_global_scope(tenant_id)`
- **Abnahmekriterium:** Integration-Test: Tenant mit 2 Workspaces (ws_1: 5 Requirements, ws_2: 3 Requirements). `resolve_global_scope(tenant_id)` → Liste mit 8 Requirements + zugehörige Items.
- **Priorität:** mandatory

---

### 5.2 SnapshotBuilder

> **Zuständigkeit:** Erstellt atomaren JSON-Snapshot, persistiert unveränderlich
> **COMP-REQs:** COMP-REQ-019

---

#### UNIT-REQ-065: Atomare Snapshot-Persistierung

- **Beschreibung:** Die Methode `SnapshotBuilder.build(baseline_name, scope, resolved_items, workspace_id=None, artifact_id=None, created_by, description=None)` erzeugt ein Baseline-Objekt mit dem JSON-Snapshot der aufgelösten Items. Der Snapshot enthält für jedes Item: `{entity_type, entity_id, version}`. Die Persistierung erfolgt atomar in einer Transaktion. Nach der Persistierung ist das `snapshot`-Feld unveränderlich (DB-Constraint oder Application-Layer-Schutz).
- **Abgeleitet von:** COMP-REQ-019 (Baseline Scope-Auflösung und Snapshot-Erstellung)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-019 → UNIT-REQ-065
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `SnapshotBuilder.build(baseline_name, scope, resolved_items, ...)`
- **Abnahmekriterium:** Integration-Test: `build("Sprint-3", "project", resolved_items, ws_id)` → Baseline mit JSON-Snapshot persistiert. `baseline.snapshot` enthält alle resolved_items mit Versionen. Versuch, `snapshot` nach Erstellung zu ändern → Exception/Constraint-Fehler. Baseline-Objekt hat `created_by`, `created_at`, `scope="project"`.
- **Priorität:** mandatory

---

#### UNIT-REQ-066: Snapshot-Unveränderlichkeits-Validierung

- **Beschreibung:** Die Methode `SnapshotBuilder.validate_immutable(baseline_id)` stellt sicher, dass ein einmal persistierter Snapshot nicht verändert werden kann. Dies wird auf zwei Ebenen umgesetzt: (1) Django `save()`-Methode des Baseline-Modells prüft, ob das `snapshot`-Feld geändert wurde und lehnt die Speicherung ab, (2) der SnapshotBuilder bietet keine Update-Methode für Snapshots an.
- **Abgeleitet von:** COMP-REQ-019 (Baseline Scope-Auflösung und Snapshot-Erstellung)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-019 → UNIT-REQ-066
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `SnapshotBuilder.validate_immutable(baseline_id)`
- **Abnahmekriterium:** Unit-Test: Erstelle Baseline mit Snapshot. Versuche, `baseline.snapshot` zu ändern und zu speichern → Exception „Baseline snapshot is immutable". Direkter DB-Update-Versuch → abgelehnt durch Application-Layer.
- **Priorität:** mandatory

---

### 5.3 BaselineDiff

> **Zuständigkeit:** Vergleich zweier Baselines (added/changed/removed mit Versions-Delta)
> **COMP-REQs:** COMP-REQ-020

---

#### UNIT-REQ-067: Baseline-Diff-Berechnung

- **Beschreibung:** Die Methode `BaselineDiff.compute(baseline_a, baseline_b)` berechnet den Unterschied zwischen zwei Baselines. Der Diff enthält drei Kategorien: `added` (Items in B aber nicht in A, identifiziert über entity_id), `removed` (Items in A aber nicht in B) und `changed` (Items in beiden, aber mit unterschiedlicher Version). Das Ergebnis ist ein `BaselineDiffResult`-Objekt.
- **Abgeleitet von:** COMP-REQ-020 (Baseline-Vergleich)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-020 → UNIT-REQ-067
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `BaselineDiff.compute(baseline_a, baseline_b)`
- **Abnahmekriterium:** Integration-Test: Baseline A (5 Items, V1-V5). Baseline B (nach 2 Updates, 1 Delete, 1 Add). `compute(A, B)` → `{added: [new_item], removed: [deleted_item], changed: [{id: item2, old_version: 2, new_version: 3}, {id: item4, old_version: 4, new_version: 5}]}`. Identische Baselines → alle Kategorien leer.
- **Priorität:** mandatory

---

#### UNIT-REQ-068: Diff-Ergebnis-Serialisierung

- **Beschreibung:** Die Datenklasse `BaselineDiffResult` repräsentiert das Diff-Ergebnis mit den Feldern `added` (Liste von `{entity_type, entity_id, version}`), `removed` (Liste von `{entity_type, entity_id, version}`) und `changed` (Liste von `{entity_type, entity_id, old_version, new_version}`). Die Methode `to_dict()` serialisiert das Ergebnis für REST- und MCP-Responses. Zusätzlich werden Summary-Felder (`added_count`, `removed_count`, `changed_count`) bereitgestellt.
- **Abgeleitet von:** COMP-REQ-020 (Baseline-Vergleich)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-020 → UNIT-REQ-068
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `BaselineDiff.BaselineDiffResult`
- **Abnahmekriterium:** Unit-Test: `BaselineDiffResult(added=[...], removed=[...], changed=[...])`. `to_dict()` → JSON mit `added`, `removed`, `changed` Listen und Summary-Feldern. Leeres Diff → alle Listen leer, alle Counts = 0.
- **Priorität:** mandatory

---

#### UNIT-REQ-069: Baseline-Kompatibilitätsprüfung

- **Beschreibung:** Die Methode `BaselineDiff.validate_compatibility(baseline_a, baseline_b)` prüft, ob zwei Baselines vergleichbar sind (gleicher Scope oder kompatibler Scope). Baselines unterschiedlicher Scopes (z.B. document vs. global) können nur verglichen werden, wenn der kleinere Scope eine Teilmenge des größeren ist. Bei Inkompatibilität wird `BaselineIncompatibleError` ausgelöst.
- **Abgeleitet von:** COMP-REQ-020 (Baseline-Vergleich)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-020 → UNIT-REQ-069
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `BaselineDiff.validate_compatibility(baseline_a, baseline_b)`
- **Abnahmekriterium:** Unit-Test: Zwei project-Baselines desselben Workspaces → kompatibel. Zwei document-Baselines desselben Artefakts → kompatibel. document-Baseline vs. global-Baseline (document ist Teilmenge) → kompatibel. document-Baseline vs. project-Baseline (anderer Workspace) → `BaselineIncompatibleError`.
- **Priorität:** mandatory

---

### 5.4 PresetGate

> **Zuständigkeit:** Scope-Verfügbarkeitsprüfung vor Erstellung
> **COMP-REQs:** COMP-REQ-021

---

#### UNIT-REQ-070: Scope-Erlaubnis-Prüfung

- **Beschreibung:** Die Methode `PresetGate.is_scope_allowed(workspace_id, scope)` konsultiert die PresetConfigEngine und prüft, ob der angeforderte Baseline-Scope im aktiven Workspace-Preset erlaubt ist. Regeln: Minimal → kein Scope erlaubt. Standard → `document` und `project` erlaubt. Extended → alle drei Scopes (`document`, `project`, `global`) erlaubt.
- **Abgeleitet von:** COMP-REQ-021 (Baseline Preset-Gate)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-021 → UNIT-REQ-070
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `PresetGate.is_scope_allowed(workspace_id, scope)`
- **Abnahmekriterium:** Unit-Test: Minimal-Preset → `is_scope_allowed(ws, "document")` = False. Standard-Preset → `is_scope_allowed(ws, "document")` = True, `is_scope_allowed(ws, "project")` = True, `is_scope_allowed(ws, "global")` = False. Extended-Preset → alle drei = True.
- **Priorität:** mandatory

---

#### UNIT-REQ-071: Scope-Ablehnung mit Fehlermeldung

- **Beschreibung:** Die Methode `PresetGate.require_scope_allowed(workspace_id, scope)` ist eine Wrapper-Methode, die `is_scope_allowed()` aufruft und bei `False` eine `ScopeNotAllowedError` mit einer kontextspezifischen Fehlermeldung auslöst: Minimal → „Baselines not available in Minimal preset". Standard + global → „Global baselines require Extended preset". Die Fehlermeldung enthält den angeforderten Scope und das aktive Preset.
- **Abgeleitet von:** COMP-REQ-021 (Baseline Preset-Gate)
- **Traceability:** SN-04 → SYS-REQ-08 → COMP-REQ-021 → UNIT-REQ-071
- **Zugeordnetes AE:** AE-006 (BaselineService)
- **Zugeordnete Unit:** `PresetGate.require_scope_allowed(workspace_id, scope)`
- **Abnahmekriterium:** Unit-Test: Minimal-Preset, scope=document → `ScopeNotAllowedError("Baselines not available in Minimal preset")`. Standard-Preset, scope=global → `ScopeNotAllowedError("Global baselines require Extended preset")`. Standard-Preset, scope=document → keine Exception.
- **Priorität:** mandatory

---

## 6. AE-009: LlmAdapter

> **Typ:** Component | **Priorität:** P2 | **SYS-REQs:** SYS-REQ-13
>
> Der LlmAdapter ist die provider-agnostische LLM-Abstraktionsschicht. Er stellt eine stabile interne Schnittstelle bereit und implementiert graceful Degradation bei fehlender Konfiguration.

---

### 6.1 LlmCapabilityInterface

> **Zuständigkeit:** Stabile interne Signaturen für LLM-Operationen
> **COMP-REQs:** COMP-REQ-031

---

#### UNIT-REQ-072: LlmCapabilityInterface (Abstrakte Basisklasse)

- **Beschreibung:** Die abstrakte Klasse `LlmCapabilityInterface` definiert drei Operationen: `validate_artifact(artifact_id) → LlmResult`, `decompose_requirement(requirement_id) → LlmDecompositionResult` und `check_consistency(workspace_id) → LlmConsistencyResult`. Jede Operation ist als abstrakte Methode definiert, die von konkreten Provider-Implementierungen überschrieben werden muss. Die Rückgabetypen sind standardisierte Datenklassen.
- **Abgeleitet von:** COMP-REQ-031 (LLM-Capability-Interface mit Provider-Abstraktion)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-031 → UNIT-REQ-072
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `LlmCapabilityInterface` (abstrakte Klasse)
- **Abnahmekriterium:** Unit-Test: `LlmCapabilityInterface` kann nicht direkt instanziiert werden (abstrakt). Subklasse ohne Implementierung aller 3 Methoden → TypeError. Subklasse mit vollständiger Implementierung → Instanziierung erfolgreich.
- **Priorität:** mandatory

---

#### UNIT-REQ-073: AnthropicProvider-Implementierung

- **Beschreibung:** Die Klasse `AnthropicProvider(LlmCapabilityInterface)` implementiert die drei LLM-Operationen mittels der Anthropic API (Claude). Die Methode `validate_artifact()` sendet das Artifact (Title + Description) an die Anthropic API mit einem strukturierten Prompt und parst die Response in ein `LlmResult` (Score + Suggestions). `decompose_requirement()` sendet das Requirement und empfängt strukturierte Kind-Vorschläge. Die API-Konfiguration (API-Key, Modell) wird aus der Deployment-Konfiguration (.env) gelesen.
- **Abgeleitet von:** COMP-REQ-031 (LLM-Capability-Interface mit Provider-Abstraktion)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-031 → UNIT-REQ-073
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `AnthropicProvider`
- **Abnahmekriterium:** Integration-Test (mit Mock-API): `AnthropicProvider.validate_artifact(req_id)` → `LlmResult(score=0.85, suggestions=[...])`. `AnthropicProvider.decompose_requirement(req_id)` → `LlmDecompositionResult(children=[...])`. API-Timeout → `LlmProviderError`.
- **Priorität:** mandatory

---

#### UNIT-REQ-074: OpenAiProvider-Implementierung

- **Beschreibung:** Die Klasse `OpenAiProvider(LlmCapabilityInterface)` implementiert die drei LLM-Operationen mittels der OpenAI API. Die interne Prompt-Struktur und Response-Parsing-Logik ist providerspezifisch, aber die Rückgabetypen sind identisch zu AnthropicProvider (selbe Datenklassen). Die API-Konfiguration wird aus .env gelesen.
- **Abgeleitet von:** COMP-REQ-031 (LLM-Capability-Interface mit Provider-Abstraktion)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-031 → UNIT-REQ-074
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `OpenAiProvider`
- **Abnahmekriterium:** Integration-Test (mit Mock-API): `OpenAiProvider.validate_artifact(req_id)` → `LlmResult` mit identischer Struktur wie AnthropicProvider. Kein Domain-Modul kennt den konkreten Provider (Interface-basierte Kopplung).
- **Priorität:** mandatory

---

#### UNIT-REQ-075: OllamaProvider-Implementierung

- **Beschreibung:** Die Klasse `OllamaProvider(LlmCapabilityInterface)` implementiert die drei LLM-Operationen mittels der Ollama Local-API (HTTP-Endpunkt). Diese Implementierung ermöglicht Self-Hosted-Betrieb ohne externe Cloud-Abhängigkeiten. Die Konfiguration (Ollama-URL, Modell-Name) wird aus .env gelesen.
- **Abgeleitet von:** COMP-REQ-031 (LLM-Capability-Interface mit Provider-Abstraktion)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-031 → UNIT-REQ-075
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `OllamaProvider`
- **Abnahmekriterium:** Integration-Test (mit Mock-Ollama): `OllamaProvider.validate_artifact(req_id)` → `LlmResult`. Ollama nicht erreichbar → `LlmProviderError("Ollama endpoint not reachable")`.
- **Priorität:** mandatory

---

#### UNIT-REQ-076: LlmResult-Datenklasse

- **Beschreibung:** Die Datenklasse `LlmResult` standardisiert das Rückgabeformat aller LLM-Operationen. Felder: `score` (Float, 0.0-1.0), `suggestions` (Liste von Strings), `provider` (String, Provider-Name), `model` (String, verwendete Modell-Version), `token_usage` (optional, Dict mit prompt_tokens/completion_tokens). `LlmDecompositionResult` erweitert um `children` (Liste von `{title, description}`). `LlmConsistencyResult` erweitert um `issues` (Liste von `{type, description, affected_items}`).
- **Abgeleitet von:** COMP-REQ-031 (LLM-Capability-Interface mit Provider-Abstraktion)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-031 → UNIT-REQ-076
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `LlmResult`, `LlmDecompositionResult`, `LlmConsistencyResult`
- **Abnahmekriterium:** Unit-Test: `LlmResult(score=0.85, suggestions=["..."], provider="anthropic", model="claude-3")`. `to_dict()` → JSON mit allen Feldern. `LlmDecompositionResult` mit `children=[{title: "Kind 1", description: "..."}]`. Validierung: `score` außerhalb [0.0, 1.0] → `ValueError`.
- **Priorität:** mandatory

---

### 6.2 CapabilityRegistry

> **Zuständigkeit:** Deployment-Config, Aktivierung/Deaktivierung, Graceful Degradation
> **COMP-REQs:** COMP-REQ-032

---

#### UNIT-REQ-077: Provider-Registrierung und -Auswahl

- **Beschreibung:** Die Klasse `CapabilityRegistry` liest die Deployment-Konfiguration (.env: `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`) und registriert den konfigurierten Provider. Die Methode `get_provider()` liefert die aktive `LlmCapabilityInterface`-Instanz. Unterstützte Provider-Werte: „anthropic", „openai", „ollama". Bei `LLM_PROVIDER=none` oder fehlender Konfiguration wird kein Provider registriert.
- **Abgeleitet von:** COMP-REQ-032 (Graceful Degradation bei fehlender LLM-Konfiguration)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-032 → UNIT-REQ-077
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `CapabilityRegistry`
- **Abnahmekriterium:** Unit-Test: `.env` mit `LLM_PROVIDER=anthropic` → `get_provider()` liefert `AnthropicProvider`-Instanz. `LLM_PROVIDER=openai` → `OpenAiProvider`. `LLM_PROVIDER=none` → `get_provider()` liefert None. `LLM_PROVIDER=invalid` → `ConfigurationError("Unknown LLM provider: invalid")`.
- **Priorität:** mandatory

---

#### UNIT-REQ-078: Graceful-Degradation-Wrapper

- **Beschreibung:** Die Methode `CapabilityRegistry.execute_capability(capability_name, **kwargs)` ist der zentrale Einstiegspunkt für LLM-Aufrufe. Wenn kein Provider konfiguriert ist, wird ein strukturierter Fehler `{error: {code: "LLM_NOT_CONFIGURED", message: "LLM provider not configured"}}` zurückgegeben — keine Exception. Wenn der Provider einen Fehler wirft (Timeout, API-Error), wird `{error: {code: "LLM_PROVIDER_ERROR", message: ...}}` zurückgegeben. Nur bei erfolgreicher Ausführung wird das `LlmResult` zurückgegeben.
- **Abgeleitet von:** COMP-REQ-032 (Graceful Degradation bei fehlender LLM-Konfiguration)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-032 → UNIT-REQ-078
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `CapabilityRegistry.execute_capability(capability_name, **kwargs)`
- **Abnahmekriterium:** Integration-Test: Kein LLM konfiguriert → `execute_capability("validate_artifact", artifact_id=req_id)` → `{error: {code: "LLM_NOT_CONFIGURED"}}`. Provider-Timeout → `{error: {code: "LLM_PROVIDER_ERROR"}}`. Provider OK → `LlmResult(score=0.85, ...)`. Nicht-LLM-Operationen (CRUD) funktionieren ohne Einschränkung.
- **Priorität:** mandatory

---

#### UNIT-REQ-079: Capability-Aktivierung pro Deployment

- **Beschreibung:** Die Methode `CapabilityRegistry.is_capability_enabled(capability_name)` prüft, ob eine bestimmte LLM-Capability im aktuellen Deployment aktiviert ist. Die Konfiguration erfolgt über .env (z.B. `LLM_CAPABILITIES=validate,decompose`). Capabilities die nicht in der Liste sind, werden mit `LLM_NOT_CONFIGURED` beantwortet, auch wenn ein Provider konfiguriert ist. Dies ermöglicht die selektive Aktivierung einzelner Capabilities.
- **Abgeleitet von:** COMP-REQ-032 (Graceful Degradation bei fehlender LLM-Konfiguration)
- **Traceability:** SN-07 → SYS-REQ-13 → COMP-REQ-032 → UNIT-REQ-079
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `CapabilityRegistry.is_capability_enabled(capability_name)`
- **Abnahmekriterium:** Unit-Test: `LLM_CAPABILITIES=validate,decompose` → `is_capability_enabled("validate")` = True, `is_capability_enabled("decompose")` = True, `is_capability_enabled("check_consistency")` = False. Leere Config → alle False.
- **Priorität:** mandatory

---

### 6.3 LlmAuditHook

> **Zuständigkeit:** Audit-Logging für LLM-Aufrufe
> **COMP-REQs:** COMP-REQ-032 (implizit — Audit für LLM-Operationen)

---

#### UNIT-REQ-080: LLM-Aufruf-Audit-Logging

- **Beschreibung:** Die Methode `LlmAuditHook.log_llm_call(provider, capability, artifact_id, token_usage=None, success=True, error=None)` schreibt jeden LLM-Aufruf in den AuditLog. Der Eintrag enthält: Provider-Name, Capability-Name, Artefakt-ID, Token-Verbrauch (falls verfügbar), Erfolgsstatus und optionale Fehlermeldung. Der Audit-Eintrag wird mit `source="llm_adapter"` gekennzeichnet.
- **Abgeleitet von:** COMP-REQ-032 (Audit-Aspekt der LLM-Integration)
- **Traceability:** SN-11 → SYS-REQ-11 → COMP-REQ-032 → UNIT-REQ-080
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `LlmAuditHook.log_llm_call(provider, capability, artifact_id, ...)`
- **Abnahmekriterium:** Integration-Test: `validate_artifact(req_id)` via Anthropic → AuditLog-Eintrag: `{source: "llm_adapter", provider: "anthropic", capability: "validate_artifact", artifact_id: req_id, token_usage: {prompt: 150, completion: 80}, success: true}`. Fehlgeschlagener Aufruf → `success: false`, `error: "Timeout"`.
- **Priorität:** mandatory

---

#### UNIT-REQ-081: Token-Verbrauch-Tracking

- **Beschreibung:** Die Methode `LlmAuditHook.extract_token_usage(provider_response)` extrahiert den Token-Verbrauch (prompt_tokens, completion_tokens, total_tokens) aus der Provider-spezifischen Response. Jede Provider-Implementierung muss die Token-Informationen in einer standardisierten Struktur bereitstellen. Falls der Provider keine Token-Informationen liefert, wird `token_usage=None` gesetzt.
- **Abgeleitet von:** COMP-REQ-032 (Audit-Aspekt der LLM-Integration)
- **Traceability:** SN-11 → SYS-REQ-11 → COMP-REQ-032 → UNIT-REQ-081
- **Zugeordnetes AE:** AE-009 (LlmAdapter)
- **Zugeordnete Unit:** `LlmAuditHook.extract_token_usage(provider_response)`
- **Abnahmekriterium:** Unit-Test: Anthropic-Response mit `usage: {input_tokens: 150, output_tokens: 80}` → `{prompt_tokens: 150, completion_tokens: 80, total_tokens: 230}`. Response ohne Usage-Info → `None`.
- **Priorität:** should-have

---

## 7. Traceability Matrix (COMP-REQ → UNIT-REQ)

| COMP-REQ | Titel | UNIT-REQ(s) | AE |
|----------|-------|-------------|-----|
| COMP-REQ-001 | Artifact-Hierarchy Cycle Detection | UNIT-REQ-001, UNIT-REQ-002 | AE-004 |
| COMP-REQ-002 | Artifact Tree Query | UNIT-REQ-003, UNIT-REQ-004 | AE-004 |
| COMP-REQ-003 | Requirement CRUD + Workflow | UNIT-REQ-005, UNIT-REQ-006, UNIT-REQ-007, UNIT-REQ-021, UNIT-REQ-022 | AE-004 |
| COMP-REQ-007 | ArchitectureElement CRUD | UNIT-REQ-008, UNIT-REQ-009, UNIT-REQ-010 | AE-004 |
| COMP-REQ-029 | TestCase CRUD | UNIT-REQ-011, UNIT-REQ-012, UNIT-REQ-013 | AE-004 |
| COMP-REQ-044 | Export JSON/CSV | UNIT-REQ-014, UNIT-REQ-015 | AE-004 |
| COMP-REQ-045 | Export Terminologie-Metadatum | UNIT-REQ-016 | AE-004 |
| COMP-REQ-046 | Volltextsuche | UNIT-REQ-017, UNIT-REQ-018 | AE-004 |
| COMP-REQ-047 | Search Filter | UNIT-REQ-019, UNIT-REQ-020 | AE-004 |
| COMP-REQ-009 | Requirements-Tools (6) | UNIT-REQ-026, UNIT-REQ-027, UNIT-REQ-028, UNIT-REQ-029, UNIT-REQ-030, UNIT-REQ-031, UNIT-REQ-032, UNIT-REQ-033 | AE-003 |
| COMP-REQ-010 | Architecture-Tools (5) | UNIT-REQ-034, UNIT-REQ-035, UNIT-REQ-036, UNIT-REQ-037, UNIT-REQ-038 | AE-003 |
| COMP-REQ-011 | Test-Tools (5) | UNIT-REQ-039, UNIT-REQ-040, UNIT-REQ-041, UNIT-REQ-042, UNIT-REQ-043 | AE-003 |
| COMP-REQ-012 | Übergreifende Tools (4) | UNIT-REQ-044, UNIT-REQ-045, UNIT-REQ-046, UNIT-REQ-047 | AE-003 |
| COMP-REQ-022 | WorkflowDefinition-Verwaltung | UNIT-REQ-048, UNIT-REQ-049, UNIT-REQ-050, UNIT-REQ-051 | AE-005 |
| COMP-REQ-004 | Workflow-Transition-Validierung | UNIT-REQ-052, UNIT-REQ-053, UNIT-REQ-054, UNIT-REQ-055 | AE-005 |
| COMP-REQ-023 | WorkflowState History | UNIT-REQ-056, UNIT-REQ-057, UNIT-REQ-058 | AE-005 |
| COMP-REQ-024 | Workflow-Migration | UNIT-REQ-059, UNIT-REQ-060, UNIT-REQ-061 | AE-005 |
| COMP-REQ-019 | Baseline Scope + Snapshot | UNIT-REQ-062, UNIT-REQ-063, UNIT-REQ-064, UNIT-REQ-065, UNIT-REQ-066 | AE-006 |
| COMP-REQ-020 | Baseline-Vergleich | UNIT-REQ-067, UNIT-REQ-068, UNIT-REQ-069 | AE-006 |
| COMP-REQ-021 | Baseline Preset-Gate | UNIT-REQ-070, UNIT-REQ-071 | AE-006 |
| COMP-REQ-031 | LLM-Capability-Interface | UNIT-REQ-072, UNIT-REQ-073, UNIT-REQ-074, UNIT-REQ-075, UNIT-REQ-076 | AE-009 |
| COMP-REQ-032 | Graceful Degradation | UNIT-REQ-077, UNIT-REQ-078, UNIT-REQ-079, UNIT-REQ-080, UNIT-REQ-081 | AE-009 |

### Implizite COMP-REQ-Abdeckungen (Subservice-Fassaden)

| Subservice (AE-004) | UNIT-REQ(s) | Abgedeckte COMP-REQs (mitwirkend) |
|---------------------|-------------|----------------------------------|
| TraceLinkService | UNIT-REQ-021, UNIT-REQ-022 | COMP-REQ-003, COMP-REQ-007, COMP-REQ-029 |
| BaselineFacade | UNIT-REQ-023 | COMP-REQ-019, COMP-REQ-020, COMP-REQ-021 |
| WorkflowFacade | UNIT-REQ-024 | COMP-REQ-004, COMP-REQ-023 |
| PresetPolicyService | UNIT-REQ-025 | COMP-REQ-018 |

---

## 8. Zusammenfassung

### Statistik

| Metrik | Wert |
|--------|------|
| Anzahl UNIT-REQs | 81 |
| Abgedeckte AEs | 5 (AE-004, AE-003, AE-005, AE-006, AE-009) |
| Abgedeckte COMP-REQs | 22 (explizit) + 4 (implizit via Subservices) |
| Mandatory | 76 |
| Should-Have | 5 (UNIT-REQ-025, UNIT-REQ-059, UNIT-REQ-060, UNIT-REQ-061, UNIT-REQ-081) |
| COMP-REQ-043 (Docker) | Übersprungen (system-level) |

### UNIT-REQ-Verteilung nach AE

| AE | Name | UNIT-REQs | Mandatory | Should-Have |
|----|------|-----------|-----------|-------------|
| AE-004 | ApplicationService | 25 | 24 | 1 |
| AE-003 | McpServer | 22 | 22 | 0 |
| AE-005 | WorkflowEngine | 14 | 11 | 3 |
| AE-006 | BaselineService | 10 | 10 | 0 |
| AE-009 | LlmAdapter | 10 | 9 | 1 |

### UNIT-REQ-Verteilung nach Sub-Komponente

| Sub-Komponente | AE | UNIT-REQs |
|---------------|-----|-----------|
| ArtifactService | AE-004 | 4 |
| RequirementService | AE-004 | 3 |
| ArchitectureService | AE-004 | 3 |
| TestService | AE-004 | 3 |
| ExportService | AE-004 | 3 |
| SearchService | AE-004 | 4 |
| TraceLinkService | AE-004 | 2 |
| BaselineFacade | AE-004 | 1 |
| WorkflowFacade | AE-004 | 1 |
| PresetPolicyService | AE-004 | 1 |
| McpTransport | AE-003 | 2 |
| RequirementTools | AE-003 | 6 |
| ArchitectureTools | AE-003 | 5 |
| TestTools | AE-003 | 5 |
| CrossCuttingTools | AE-003 | 4 |
| WorkflowDefinitionStore | AE-005 | 4 |
| TransitionValidator | AE-005 | 4 |
| StateMutator | AE-005 | 3 |
| WorkflowMigrationHandler | AE-005 | 3 |
| ScopeResolver | AE-006 | 3 |
| SnapshotBuilder | AE-006 | 2 |
| BaselineDiff | AE-006 | 3 |
| PresetGate | AE-006 | 2 |
| LlmCapabilityInterface | AE-009 | 5 |
| CapabilityRegistry | AE-009 | 3 |
| LlmAuditHook | AE-009 | 2 |

### Traceability-Abdeckung

Alle 81 UNIT-REQs haben eine vollständige Traceability-Kette zurück zu mindestens einem Stakeholder-Need:

| SN | SYS-REQs | COMP-REQs (in Scope) | UNIT-REQ-Range |
|----|----------|---------------------|----------------|
| SN-01 (Maschinenlesbarer Kontext) | SYS-REQ-05, 06, 20 | COMP-REQ-009, 012, 046, 047 | UNIT-REQ-017..020, 026..033, 044..047 |
| SN-02 (Skalierbare SE-Tiefe) | SYS-REQ-01, 02, 07 | COMP-REQ-001, 002, 003, 018 | UNIT-REQ-001..007, 021, 022, 025 |
| SN-03 (Traceability) | SYS-REQ-01, 03, 04, 12 | COMP-REQ-002, 003, 007, 012, 029 | UNIT-REQ-003..013, 021, 022, 044..047 |
| SN-04 (Baselines) | SYS-REQ-08 | COMP-REQ-019, 020, 021 | UNIT-REQ-023, 062..071 |
| SN-05 (Item-Lifecycle) | SYS-REQ-02, 09 | COMP-REQ-004, 022, 023, 024 | UNIT-REQ-024, 048..061 |
| SN-07 (LLM optional) | SYS-REQ-13 | COMP-REQ-009, 031, 032 | UNIT-REQ-033, 072..081 |
| SN-10 (Terminologie) | SYS-REQ-19 | COMP-REQ-044, 045 | UNIT-REQ-014..016 |
| SN-11 (Audit-Trail) | SYS-REQ-11 | COMP-REQ-032 | UNIT-REQ-080, 081 |
| SN-12 (REST+MCP gleichrangig) | SYS-REQ-03, 05 | COMP-REQ-003, 009, 010, 011 | UNIT-REQ-021, 022, 028..043 |

*Hinweis: UNIT-REQs können über mehrere Traceability-Pfade von mehreren SNs erreichbar sein. Die Summe der Zeilen übersteigt daher 81.*

### Offene Punkte (aus L2 übernommen)

| OP-ID | Einfluss auf L3 |
|-------|----------------|
| OP-01 (LLM-Capability-Scope) | UNIT-REQ-072 (Interface definiert alle 4 Operationen), UNIT-REQ-079 (selektive Aktivierung) |
| OP-02 (Preset-Downgrade) | UNIT-REQ-025 (PresetPolicyService.validate_downgrade) |
| OP-03 (Workflow-Wechsel) | UNIT-REQ-059 bis UNIT-REQ-061 (WorkflowMigrationHandler) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L3 | 2026-06-17*
*Nächster Schritt: Übergabe an se-critic für Quality-Gate-Validierung der L3-Decomposition*
