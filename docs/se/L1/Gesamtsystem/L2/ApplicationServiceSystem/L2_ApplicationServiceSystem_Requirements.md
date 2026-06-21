# L2 ApplicationService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** ApplicationServiceSystem (ARCH-L1-004)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** LEAF (terminal, keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-001, REQ-L1-002, REQ-L1-003, REQ-L1-004, REQ-L1-007, REQ-L1-008, REQ-L1-009, REQ-L1-010, REQ-L1-011, REQ-L1-012, REQ-L1-013, REQ-L1-015, REQ-L1-019, REQ-L1-020, REQ-L1-021, REQ-L1-022, REQ-L1-023, REQ-L1-024, REQ-L1-025, REQ-L1-026, REQ-L1-029
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

### Eingehend (Caller → ApplicationService)

| ID | Quelle | Typ | Beschreibung |
|----|--------|-----|--------------|
| IF-AS-EXT-IN-001 | ARCH-L1-002 (RestApiAdapter) | data | Use-Case-Methoden (In-Process Python) |
| IF-AS-EXT-IN-002 | ARCH-L1-003 (McpServer) | data | Use-Case-Methoden (identischer Domain-Kontrakt) |
| IF-AS-EXT-IN-003 | ARCH-L1-011 (AuthAndTenancy) | control | Auth-Kontext (User, Tenant, Rollen) |

### Ausgehend (ApplicationService → Callee)

| ID | Ziel | Typ | Beschreibung |
|----|------|-----|--------------|
| IF-AS-EXT-OUT-001 | ARCH-L1-005 (WorkflowEngine) | data | `transition()`, Workflow-Initialisierung |
| IF-AS-EXT-OUT-002 | ARCH-L1-006 (BaselineService) | data | `build()`, `diff()` |
| IF-AS-EXT-OUT-003 | ARCH-L1-007 (TraceabilityEngine) | data | `query()`, `coverage()` |
| IF-AS-EXT-OUT-004 | ARCH-L1-008 (PresetConfigEngine) | data | `get_preset()`, `is_feature_enabled()` |
| IF-AS-EXT-OUT-005 | ARCH-L1-009 (LlmAdapter) | data | `validate`, `decompose`, `check_consistency` |
| IF-AS-EXT-OUT-006 | ARCH-L1-012 (AuditLog) | data | `log_write()` |
| IF-AS-EXT-OUT-007 | ARCH-L1-010 (PersistenceLayer) | data | Datenbank-Schnittstelle (alle Entitäten) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-AS-001: Artifact-Hierarchy Cycle Detection

Der ApplicationService SHALL bei Erstellung oder Änderung einer Parent-Child-Beziehung validieren, dass keine zyklischen Abhängigkeiten eingeführt werden. Validierung VOR Persistenz. Bei Zyklus-Erkennung: Operation abbrechen mit Fehlermeldung.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
- [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
- [ ] Gültige Parent-Änderung → erfolgreich

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-001
**Rationale:** Zyklische Hierarchien korrodieren Datenintegrität und machen Tree-Queries nicht-terminierend.

---

### REQ-L2-AS-002: Artifact Tree Query mit beliebiger Tiefe

Der ApplicationService SHALL eine Tree-Query-Operation bereitstellen, die die vollständige Artefakt-Hierarchie als verschachtelte Struktur bis zu einer variablen Tiefe (N) zurückgibt. ≤ 200ms bei 500 Artefakten.

**Domain:** software
**Priority:** mandatory
**Arch Impact:** true
**Arch Trigger:** Effiziente hierarchische Datenabfrage bis zu variabler Tiefe.
**Acceptance Criteria:**
- [ ] Tree-Query über 500 Artefakte in 5 Ebenen → vollständige Struktur in < 200ms
- [ ] `get_tree(root_id=B)` → nur B und Nachkommen
- [ ] Integration-Test: 3-stufige Hierarchie → korrekt verschachtelt

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-001
**Rationale:** Tree-Query ist Basis für UI-Baumdarstellung, MCP-Tool `artifact.get_tree` und Export.

---

### REQ-L2-AS-003: Requirement CRUD with Workflow Integration

Der ApplicationService SHALL vollständiges CRUD für Requirements bereitstellen. Bei Erstellung: automatischer initialer WorkflowState. Bei Update: `change_reason` validieren (Pflicht im Extended-Preset). Bei Delete: Cascade-Löschung aller TraceLinks. Jede Schreiboperation delegiert Workflow-Validierung an WorkflowEngine und schreibt AuditLog.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_requirement()` → Requirement mit initialem WorkflowState
- [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
- [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
- [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-002
**Rationale:** Requirements sind die Kernentität; Workflow-Integration ersetzt hartcodierten Status-Enum.

---

### REQ-L2-AS-004: ArchitectureElement CRUD with Versioning

Der ApplicationService SHALL vollständiges CRUD für ArchitectureElements bereitstellen mit: element_type (Component, Interface, Subsystem, Layer, Module), automatischem Version-Inkrement, Optimistic Locking. Bei Delete: Cascade TraceLinks.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_architecture_element()` → version=1, initialer WorkflowState
- [ ] `update()` → version=2
- [ ] Parallel-Update mit stale version → `OptimisticLockError`
- [ ] Delete → zugehörige TraceLinks gelöscht

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-004
**Rationale:** ArchitectureElements als eigenständiger, versionierter Typ.

---

### REQ-L2-AS-005: TestCase CRUD with Test Status Management

Der ApplicationService SHALL vollständiges CRUD für TestCases bereitstellen mit: test_type (Unit, Integration, System, Acceptance), WorkflowState, execution_status (Passed, Failed, Not Run). Bei Delete: Cascade TraceLinks.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
- [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
- [ ] Query mit Filtern → gefilterte Liste
- [ ] Delete → TraceLinks gelöscht

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-012
**Rationale:** Testmanagement ist Teil des v1-Funktionsumfangs.

---

### REQ-L2-AS-006: Export in JSON and CSV

Der ApplicationService SHALL Export-Operationen für Requirements, ArchitectureElements, TestCases und TraceLinks in JSON und CSV bereitstellen. Scope: Workspace oder einzelnes Artefakt. Export von 1.000 Requirements ≤ 5 Sekunden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
- [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
- [ ] 1.000 Requirements in < 5 Sekunden exportiert

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-019
**Rationale:** Export ist Must-Have für v1.

---

### REQ-L2-AS-007: Export with Terminology Profile Metadata

Der ApplicationService SHALL das aktive Terminologie-Profil als Metadatum in jeden Export einbetten. JSON: `metadata.terminology_profile`. CSV: Kommentarzeile am Dateianfang.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] JSON-Export im SE-Modus → `"metadata": {"terminology_profile": "se_mode"}`
- [ ] CSV-Export → `# terminology_profile: se_mode` in erster Zeile
- [ ] Nach Profilwechsel → Export reflektiert neues Profil

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-02
- Outgoing: IF-AS-EXT-OUT-004, IF-AS-EXT-OUT-07

**Traceability:** REQ-L1-019, REQ-L1-014 (mitwirkend)
**Rationale:** Korrekte Interpretation des Exports in der jeweiligen Zielgruppe.

---

### REQ-L2-AS-008: Full-Text Search across Artifact Types

Der ApplicationService SHALL artefakttyp-übergreifende Volltextsuche über Requirements, ArchitectureElements und TestCases bereitstellen. Suche berücksichtigt Wortstämme und Tippfehler (Fuzzy Search/Stemming). Ergebnisse nach Relevanz sortiert mit Artefakttyp-Annotation. ≤ 500ms bei 10.000 Items.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Suche über 5 Requirements, 3 ArchElements, 2 TestCases → alle Matches mit `artifact_type`-Feld
- [ ] Suche über 10.000 Items → < 500ms

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-020
**Rationale:** Volltextsuche ist expliziter v1-Bestandteil.

---

### REQ-L2-AS-009: Search Type-Filter and Workspace-Filter

Der ApplicationService SHALL optionale Filter für Artefakttyp und Workspace in Suchoperationen unterstützen. Beide Filter KÖNNEN kombiniert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
- [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
- [ ] Kombination beider Filter → korrekt gefiltert

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-020
**Rationale:** Filter notwendig für gezielte Suche in großen Workspaces.

---

### REQ-L2-AS-010: TraceLink Orchestration

Der ApplicationService SHALL TraceLink-Erstellung, -Query und -Löschung als Orchestrierung über die TraceabilityEngine bereitstellen. Validierung: Source und Target existieren und gehören zum selben Workspace. Unterstützte Link-Typen: `parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`. AuditLog für Schreiboperationen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
- [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
- [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
- [ ] Nach Erstellung: AuditLog-Eintrag vorhanden

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-003, IF-AS-EXT-OUT-006

**Traceability:** REQ-L1-003
**Rationale:** Orchestriert TraceLink-Operationen als Teil von Use-Cases.

---

### REQ-L2-AS-011: Baseline Lifecycle Orchestration

Der ApplicationService SHALL Baseline-Erstellung, -Abruf und -Diff als Facade über den BaselineService orchestrieren. VOR Erstellung: PresetConfigEngine konsultieren (Scope-Verfügbarkeit). Nach Erstellung: AuditLog.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_baseline(scope="global")` im Minimal → Fehler `"Scope not permitted"`
- [ ] `create_baseline(scope="project")` im Standard → Baseline erstellt, immutable
- [ ] Nach Erstellung: AuditLog-Eintrag
- [ ] `diff_baseline(a, b)` → Diff mit added/removed/changed

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-002, IF-AS-EXT-OUT-004, IF-AS-EXT-OUT-006

**Traceability:** REQ-L1-008
**Rationale:** Facade bündelt Cross-Service-Orchestrierung.

---

### REQ-L2-AS-012: Workflow Transition Orchestration

Der ApplicationService SHALL Workflow-Transitionen als Facade über die WorkflowEngine orchestrieren. Delegiert Validierung (Rollen, change_reason) an WorkflowEngine. Nach Transition: AuditLog. DARF WorkflowState nicht direkt modifizieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `transition(id, "approved", change_reason="Review passed", ctx)` im Extended → State aktualisiert, History-Eintrag
- [ ] `transition(id, "approved", change_reason=None)` im Extended → Fehler
- [ ] `transition` mit Viewer-Rolle für Approver-Transition → Fehler
- [ ] Nach Transition: AuditLog-Eintrag

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006

**Traceability:** REQ-L1-009
**Rationale:** Kapselt Delegationslogik, trennt Verantwortlichkeiten.

---

### REQ-L2-AS-013: LLM Capability Orchestration

Der ApplicationService SHALL LLM-gestützte Capabilities (validate, decompose, check_consistency) durch Delegierung an den LlmAdapter orchestrieren. Ohne LLM-Konfiguration: graceful Fehler. LLM-Ergebnisse strukturell validieren VOR Persistierung.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `validate_requirement(id)` mit LLM → strukturiertes Ergebnis
- [ ] `validate_requirement(id)` ohne LLM → Fehler `"LLM not configured"`
- [ ] `decompose_requirement(id)` mit LLM → Kind-Requirements + TraceLinks
- [ ] Strukturell ungültiges LLM-Ergebnis → Fehler, keine partiellen Daten

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-005

**Traceability:** REQ-L1-013
**Rationale:** LLM als pluggable Capability; System bleibt ohne LLM funktionsfähig.

---

### REQ-L2-AS-014: CSV Bulk Import

Der ApplicationService SHALL CSV-Import für Requirements, ArchitectureElements und TestCases bereitstellen. Validierung gegen Datenmodell. Fehler mit Zeilennummer. Importiert Items mit UUIDs. Atomar: entweder alle gültigen Zeilen oder keine.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] CSV mit 100 Requirements → 100 Items mit UUIDs
- [ ] CSV mit 2 ungültigen Zeilen → Fehlerbericht mit Zeilennummern
- [ ] Pflichtfeld-Fehler → gesamte Operation abgebrochen (atomar)
- [ ] Ergebnisbericht: Anzahl erfolgreich importierter Items + Fehler

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-021
**Rationale:** Migration bestehender Anforderungsdaten ohne manuelle Neueingabe.

---

### REQ-L2-AS-015: GitHub Integration

Der ApplicationService SOLLTE die Verknüpfung von Requirements mit GitHub Issues und PRs unterstützen. Bidirektional abrufbar. GitHub-Token und zugreifbare Repositories erforderlich.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `link_github_issue(req_id, issue_url)` mit Token → Verknüpfung hergestellt
- [ ] `get_github_links(req_id)` → Liste verknüpfter Issues/PRs
- [ ] Ohne Token → Fehler `"GitHub token not configured"`
- [ ] Mit ungültigem Token → Fehler `"GitHub authentication failed"`

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-022
**Rationale:** GitHub-Integration ist Should-Have für die Zielgruppe.

---

### REQ-L2-AS-016: PDF Report Export

Der ApplicationService SOLLTE PDF-Report-Export für Anforderungsdokumente und Traceability-Matrizen bereitstellen. Inklusive Metadaten (Version, Baseline-Referenz, Workflow-State, Audit-History). Scope: Workspace, Artefakt oder Baseline.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
- [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
- [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-023
**Rationale:** SE-Zielgruppe benötigt dokumentierbare Übergaben für Reviews.

---

### REQ-L2-AS-017: Webhook Dispatch

Der ApplicationService SOLLTE konfigurierbare Webhooks für Ereignis-Typen (Requirement erstellt, geändert, Status-Übergang, Baseline erstellt) dispatchen. HTTP POST an konfigurierte URL mit JSON-Payload. Der Dispatch der Webhooks MUSS asynchron erfolgen und DARF die auslösende Operation nicht blockieren. Entkopplung über asynchronen Messaging-Mechanismus (REQ-L2-AS-029).

**Domain:** software
**Priority:** desired
**Arch Impact:** true
**Arch Trigger:** Asynchroner, entkoppelter Webhook-Dispatch ohne Blockierung der synchronen Anfrage.
**Acceptance Criteria:**
- [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
- [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
- [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
- [ ] Webhook deaktiviert → kein Dispatch

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Incoming (intern): IF-AS-EXT-OUT-006 (Domain Events via asynchronen Entkopplungsmechanismus)

**Traceability:** REQ-L1-024
**Rationale:** Ermöglicht externen Systemen auf Änderungen zu reagieren. Entkopplung vom ApplicationService via asynchronen Entkopplungsmechanismus reduziert synchrone Abhängigkeiten.

---

### REQ-L2-AS-018: Transactional Consistency (ACID)

Der ApplicationService SHALL alle Datenänderungen atomar und konsistent persistieren. Bei Fehlern: vollständiges Rollback. Die Atomizität MUSS über das gesamte System sichergestellt sein (ACID-Garantien).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `decompose_requirement()` schlägt fehl nach Kind-INSERT → alle Kinder zurückgerollt
- [ ] `create_baseline()` schlägt fehl während Snapshot → keine Baseline persistiert
- [ ] Simulierter DB-Fehler → vollständiges Rollback

**Interfaces:**
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-025
**Rationale:** Datenkonsistenz ist fundamentale Non-Functional-Anforderung.

---

### REQ-L2-AS-019: Audit Log Writing

Der ApplicationService SHALL nach jeder Schreiboperation einen AuditLog-Eintrag schreiben: actor, operation, entity_id, timestamp, optionale Details. Der AuditLog-Eintrag MUSS durch einen entkoppelten, asynchronen Mechanismus (REQ-L2-AS-029) geschrieben werden. Die Persistierung des Events für das Audit-Log MUSS im selben Transaktionskontext erfolgen wie die Mutation (Eventual-Write-Garantie, kein Fire-and-Forget), ohne den AuditLogWriter direkt synchron aufzurufen.

**Domain:** software
**Priority:** mandatory
**Arch Impact:** true
**Arch Trigger:** Eventual-Write-Garantie für Audit-Logs ohne synchrone Kopplung an Mutationen.
**Acceptance Criteria:**
- [ ] Nach `create_requirement()` → AuditLog-Eintrag mit op="create" vorhanden (spätestens nach Event-Verarbeitung)
- [ ] Nach `update_requirement()` → AuditLog-Eintrag mit op="update" vorhanden
- [ ] Nach `transition()` → AuditLog-Eintrag mit op="transition" vorhanden
- [ ] Rollback der Entity-Änderung → auch das Domain-Event wird zurückgerollt → kein AuditLog-Eintrag
- [ ] Ausfall des async Workers nach Event-Persistierung → Event bleibt persistent gespeichert, AuditLog wird nach Wiederanlauf nachgeholt

**Interfaces:**
- Outgoing: IF-AS-EXT-OUT-006

**Traceability:** REQ-L1-011
**Rationale:** Entkopplung von synchroner Schreiboperation und AuditLog-Schreibung via asynchronen Entkopplungsmechanismus. Dies sichert Eventual-Write-Garantie ohne starre In-Transaction-Kopplung.

---

### REQ-L2-AS-020: Preset Policy Enforcement

Der ApplicationService SHALL PresetConfigEngine konsultieren vor preset-abhängigen Operationen: (a) Baseline-Scope-Verfügbarkeit, (b) change_reason-Pflicht, (c) Preset-Downgrade-Validierung.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_baseline(scope="global")` im Minimal → Fehler
- [ ] `update(change_reason=None)` im Extended → Fehler
- [ ] `update(change_reason=None)` im Minimal → erfolgreich
- [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler

**Interfaces:**
- Outgoing: IF-AS-EXT-OUT-004

**Traceability:** REQ-L1-007
**Rationale:** Configurable Rigor als Querschnitts-Konzept.

---

### REQ-L2-AS-021: Auth Context Propagation

Der ApplicationService SHALL Auth-Kontext (User, Tenant, Rollen) von AuthAndTenancy für jede Operation empfangen und an Downstream-Calls weiterreichen. DARF keine Auth-Primitiven direkt aufrufen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Jeder Use-Case-Aufruf enthält `ctx` mit User, Tenant, Roles
- [ ] `create_requirement(ctx)` mit Viewer → Fehler `"Permission denied"`
- [ ] `transition()` → Auth-Kontext an WorkflowEngine weitergereicht
- [ ] Keine direkten Auth-Primitiven im ApplicationService-Code

**Interfaces:**
- Incoming: IF-AS-EXT-IN-003
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-002, IF-AS-EXT-OUT-003

**Traceability:** REQ-L1-010
**Rationale:** Trennung von Auth (ARCH-L1-011) und Geschäftslogik.

---

### REQ-L2-AS-022: Tenant Context Propagation

Der ApplicationService SHALL sicherstellen, dass jede DB-Query auf den aktiven Tenant beschränkt ist. Tenant aus Auth-Kontext extrahiert und an PersistenceLayer propagiert. DARF Tenant-Filter nicht umgehen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
- [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
- [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
- [ ] Kein Code-Pfad umgeht Custom Manager

**Interfaces:**
- Incoming: IF-AS-EXT-IN-003
- Outgoing: IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-015
**Rationale:** Row-Level-Isolation ist Voraussetzung für v2-SaaS.

---

### REQ-L2-AS-023: Performance Contribution

Der ApplicationService SHALL maximal 50ms Orchestrierungs-Overhead pro Use-Case hinzufügen (exklusive Downstream-Latenz). Batch-Operationen wo möglich. Keine N+1-Queries.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_requirement()` Overhead (ohne DB) < 50ms
- [ ] `decompose_requirement()` mit 10 Kindern → Batch-INSERT, keine N+1
- [ ] `get_tree()` über 500 Artefakte → < 200ms gesamt
- [ ] Code-Review: keine N+1-Query-Muster

**Interfaces:**
- Outgoing: IF-AS-EXT-OUT-001..07

**Traceability:** REQ-L1-026
**Rationale:** 50ms-Obergrenze stellt sicher, dass das System die API-SLAs erreicht.

---

### REQ-L2-AS-024: Requirement Decomposition Orchestration

Der ApplicationService SHALL die Decomposition eines Requirements in Kind-Requirements orchestrieren. Mit übergebenen Children: direkt validieren und persistieren. Ohne Children: an LlmAdapter delegieren. Nach Erstellung: parent-child-TraceLinks, WorkflowState-Initialisierung, AuditLog.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `decompose(id, children=[...])` → Kinder erstellt, TraceLinks gesetzt, WorkflowStates initialisiert, AuditLog
- [ ] `decompose(id)` ohne children, mit LLM → LLM aufgerufen, Kinder persistiert
- [ ] `decompose(id)` ohne children, ohne LLM → Fehler `"LLM not configured"`
- [ ] Decomposition atomar — Fehler nach Kind-INSERT → Rollback

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-003, IF-AS-EXT-OUT-005, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-002, REQ-L1-013 (mitwirkend)
**Rationale:** Zentraler AI-nativer Workflow erfordert Multi-Subsystem-Orchestrierung.

---

### REQ-L2-AS-025: Coverage Calculation

Der ApplicationService SHALL Coverage-Berechnung bereitstellen: welche Requirements haben mindestens einen `verifies`-TraceLink zu einem TestCase. Ergebnis: total, covered, percentage. Delegiert TraceLink-Query an TraceabilityEngine.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 10 Requirements, 7 mit TestCases → Coverage = 70%
- [ ] `get_coverage(workspace_id)` → `{total: 10, covered: 7, percentage: 70.0}`
- [ ] Nach TestCase-Löschung → Coverage aktualisiert

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-003

**Traceability:** REQ-L1-012
**Rationale:** Coverage-Tracking ist Grundlage für AI-gestützte Test-Lücken-Analyse.

---

### REQ-L2-AS-026: ADR CRUD

Der ApplicationService SOLLTE vollständiges CRUD für Architecture Decision Records (ADRs) bereitstellen. Mit Status-Übergängen, Verlinkung zu betroffenen ArchitectureElements und Requirements.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `create_adr()` → ADR mit initialem Status erstellt
- [ ] `update_adr_status(id, "accepted")` → AuditLog-Eintrag mit op="update_status" vorhanden
- [ ] `link_adr(adr_id, target_id="REQ-123")` → TraceLink zu Requirement erstellt
- [ ] `link_adr(adr_id, target_id="ARCH-123")` → TraceLink zu ArchitectureElement erstellt

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-029
**Rationale:** Dokumentation von Architektur-Entscheidungen im Kontext der betroffenen Elemente.

---

### REQ-L2-AS-027: Risiko CRUD

Der ApplicationService SOLLTE vollständiges CRUD für Risiken (Risks) bereitstellen. Mit Severity, Probability, Mitigation-Strategien und TraceLinks zu Requirements/ArchitectureElements.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `create_risk(severity="high", probability="low")` → Risiko mit korrekten Werten erstellt
- [ ] `link_risk(risk_id, target_id="REQ-123")` → TraceLink zu Requirement erstellt
- [ ] `link_risk(risk_id, target_id="ARCH-123")` → TraceLink zu ArchitectureElement erstellt
- [ ] `delete_risk(id)` → Risiko und alle damit verbundenen TraceLinks gelöscht

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-029
**Rationale:** Risikomanagement als integrierter Bestandteil des SE-Lifecycles.

---

### REQ-L2-AS-028: Issue CRUD

Der ApplicationService SOLLTE vollständiges CRUD für System-Issues bereitstellen. Mit Status, Assignee, und TraceLinks zu betroffenen Artefakten.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `create_issue(status="open", assignee="user1")` → Issue mit Status und Assignee erstellt
- [ ] `link_issue(issue_id, target_id="REQ-123")` → TraceLink zu Requirement erstellt
- [ ] `link_issue(issue_id, target_id="ARCH-123")` → TraceLink zu ArchitectureElement erstellt
- [ ] `update_issue_status(id, "closed")` → AuditLog-Eintrag mit op="update_status" vorhanden

**Interfaces:**
- Incoming: IF-AS-EXT-IN-001, IF-AS-EXT-IN-002
- Outgoing: IF-AS-EXT-OUT-001, IF-AS-EXT-OUT-006, IF-AS-EXT-OUT-007

**Traceability:** REQ-L1-029
**Rationale:** Integriertes Issue-Tracking für das laufende System-Engineering.

---

### REQ-L2-AS-029: Asynchroner Entkopplungsmechanismus

Der ApplicationService SHALL nach jeder erfolgreichen Mutation ein typisiertes Domain-Event publizieren. Unterstützte Event-Typen: `RequirementCreated`, `RequirementUpdated`, `RequirementDeleted`, `BaselineCreated`, `WorkflowTransitioned`. Das Event-Publishing MUSS atomar an die auslösende Transaktion gebunden sein (Garantie: kein Event verloren, kein Event für zurückgerollte Mutation). AuditLogWriter, SeMetricsCollector und WebhookDispatcher empfangen Events asynchron. Der ApplicationService kennt keine Subscriber — die Kopplung erfolgt ausschließlich über den Event-Typ.

**Domain:** software
**Priority:** mandatory
**Arch Impact:** true
**Arch Trigger:** Transaktionssicheres, entkoppeltes Event-Publishing zur asynchronen Benachrichtigung von Subsystemen.
**Acceptance Criteria:**
- [ ] `create_requirement()` → `RequirementCreated`-Event persistiert, bevor HTTP-Response zurückkommt
- [ ] Rollback der Mutation → kein Event persistiert → kein Subscriber wird ausgelöst
- [ ] AuditLogWriter empfängt Event und schreibt AuditLog-Eintrag asynchron
- [ ] SeMetricsCollector empfängt Event und aktualisiert Metriken asynchron
- [ ] WebhookDispatcher empfängt Event und dispatcht Webhook asynchron (sofern konfiguriert)
- [ ] Ausfall eines Subscribers → andere Subscriber nicht betroffen
- [ ] Ausfall des async Workers → Event verbleibt persistent gespeichert, wird nach Wiederanlauf verarbeitet
- [ ] Neuer Subscriber kann registriert werden ohne Änderung am ApplicationService

**Interfaces:**
- Outgoing: IF-AS-EXT-OUT-006 (AuditLog via Event)
- Outgoing: IF-AS-EXT-OUT-007 (Ereignis-Persistierung via PersistenceLayer)

**Traceability:** REQ-L1-026 (Performance), REQ-L1-011 (Audit)
**Rationale:** Synchrone Direktaufrufe von AuditLog, SeMetrics und WebhookDispatcher nach jeder Mutation verlängern Antwortzeiten und erzeugen starre strukturelle Kopplung. Der asynchrone Entkopplungsmechanismus entkoppelt Publisher und Subscriber, reduziert Orchestrierungs-Overhead und ermöglicht unabhängige Skalierung der Subscriber.

---

## Traceability-Matrix: REQ-L2-AS → REQ-L1

| REQ-L2-AS | Titel (Kurz) | REQ-L1 | Priorität |
|-----------|-------------|--------|-----------|
| REQ-L2-AS-001 | Cycle Detection | REQ-L1-001 | mandatory |
| REQ-L2-AS-002 | Tree Query | REQ-L1-001 | mandatory |
| REQ-L2-AS-003 | Requirement CRUD | REQ-L1-002 | mandatory |
| REQ-L2-AS-004 | ArchElement CRUD | REQ-L1-004 | mandatory |
| REQ-L2-AS-005 | TestCase CRUD | REQ-L1-012 | mandatory |
| REQ-L2-AS-006 | Export JSON/CSV | REQ-L1-019 | mandatory |
| REQ-L2-AS-007 | Export Metadata | REQ-L1-019, REQ-L1-014 | mandatory |
| REQ-L2-AS-008 | Volltextsuche | REQ-L1-020 | mandatory |
| REQ-L2-AS-009 | Search Filter | REQ-L1-020 | mandatory |
| REQ-L2-AS-010 | TraceLink Orchestration | REQ-L1-003 | mandatory |
| REQ-L2-AS-011 | Baseline Lifecycle | REQ-L1-008 | mandatory |
| REQ-L2-AS-012 | Workflow Transition | REQ-L1-009 | mandatory |
| REQ-L2-AS-013 | LLM Orchestration | REQ-L1-013 | mandatory |
| REQ-L2-AS-014 | CSV Import | REQ-L1-021 | mandatory |
| REQ-L2-AS-015 | GitHub Integration | REQ-L1-022 | desired |
| REQ-L2-AS-016 | PDF Export | REQ-L1-023 | desired |
| REQ-L2-AS-017 | Webhooks | REQ-L1-024 | desired |
| REQ-L2-AS-018 | ACID | REQ-L1-025 | mandatory |
| REQ-L2-AS-019 | Audit Writing | REQ-L1-011 | mandatory |
| REQ-L2-AS-020 | Preset Policy | REQ-L1-007 | mandatory |
| REQ-L2-AS-021 | Auth Propagation | REQ-L1-010 | mandatory |
| REQ-L2-AS-022 | Tenant Propagation | REQ-L1-015 | mandatory |
| REQ-L2-AS-023 | Performance | REQ-L1-026 | mandatory |
| REQ-L2-AS-024 | Decomposition | REQ-L1-002, REQ-L1-013 | mandatory |
| REQ-L2-AS-025 | Coverage | REQ-L1-012 | mandatory |
| REQ-L2-AS-026 | ADR CRUD | REQ-L1-029 | desired |
| REQ-L2-AS-027 | Risiko CRUD | REQ-L1-029 | desired |
| REQ-L2-AS-028 | Issue CRUD | REQ-L1-029 | desired |
| REQ-L2-AS-029 | Asynchroner Entkopplungsmechanismus | REQ-L1-026, REQ-L1-011 | mandatory |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-AS | 29 |
| Mandatory | 23 |
| Desired | 6 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 21 |
| Abgedeckte REQ-L1 (mitwirkend) | 11 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-AppSvc → REQ-L2-AS, Template-Standardisierung*
*Designation: LEAF (terminal, keine L3-Zerlegung)*
