---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 IssueService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-015_IssueService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-029 (primär) — Issue-Management ist eine Cross-Cutting-Concern der L1
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der IssueService verwaltet den vollständigen Lifecycle von Issue-Entitäten im ReqFlow-System. Er orchestriert CRUD-Operationen, delegiert Workflow-Transitions an die WorkflowEngine, Traceability-Verwaltung an die TraceabilityEngine und publikziert Domain-Events via DomainEventBus. Issues sind zentrale Artefakte zur Dokumentation von identifizierten Problemen, deren Severity, zuständigen Personen und Resolution-Status.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | Issue CRUD-Requests vom ApplicationService (create, update, get, list, delete) |
| IF-AS-INT-002 | output | data | TraceLink-Erstellung an TraceLinkService (`create_trace_link(source_id, target_id, link_type)`) |
| IF-AS-INT-003 | output | data | Workflow-State-Transition an WorkflowFacade (`transition(item_id, target_state, change_reason, ctx)`) |
| IF-AS-INT-017 | output | event | Domain-Event-Publikation (IssueCreated/Updated/Deleted) via DomainEventBus |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer (Django ORM) |

---

## L3 Component-Anforderungen

### REQ-L3-ISSUE-001: Issue-Erstellung mit Workflow-Initialisierung

Der IssueService SHALL ein neues Issue-Artefakt erstellen und folgende Schritte durchführen:
1. Validiere Payload (title, description, severity, status obligatorisch)
2. Erstelle Issue-Entity mit eindeutiger UUID
3. Initialisiere WorkflowState gemäß aktiver WorkflowDefinition der Workspace
4. Persistiere Artefakt (Transactional)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Issue wird mit valider UUID erstellt
- [ ] Severity wird validiert (critical, high, medium, low)
- [ ] WorkflowState wird automatisch initialisiert
- [ ] Transaktionale Persistierung
- [ ] Rückgabe der erstellten Issue-UUID

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-INT-003, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Issues sind Lifecycle-Artefakte mit State-Management und Priorisierung.

---

### REQ-L3-ISSUE-002: Issue-Metadaten und Klassifikation

Der IssueService SHALL Issues mit strukturierten Metadaten speichern:
- `title`: string, Beschreibung des Issues
- `description`: string, detaillierte Problem-Charakterisierung
- `severity`: enum (critical, high, medium, low)
- `category`: enum (defect, improvement, documentation, question)
- `assignee`: optional User/Agent, zuständig für Resolution
- `created_by`: automatisch erfasst (User oder Agent)
- `due_date`: optional, Zieldatum für Resolution
- `tags`: array, optional Klassifikation
- `status`: enum (Open, In Progress, Resolved, Closed, Wontfix)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Felder werden validiert
- [ ] Severity ist querybar und sortierbar
- [ ] Assignee ist optional und kann geändert werden
- [ ] Due-Date wird formatiert (ISO 8601)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Strukturierte Issue-Erfassung ermöglicht Priorisierung und Verwaltung.

---

### REQ-L3-ISSUE-003: Issue-Update mit Versionierung

Der IssueService SHALL Issue-Updates mit Versionshistorie verwalten. Bei Änderungen:
1. Alte Version bleibt unverändert
2. Neue Version mit version+1 wird erstellt
3. Timestamp und Actor werden erfasst
4. Ausgangszustand wird dokumentiert (für Audit-Trail)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alte Issue-Versionen bleiben lesbar
- [ ] Neue Version wird mit version+1 gekennzeichnet
- [ ] Audit-Trail ist vollständig (wer, wann, was)
- [ ] Versionsverlauf ist querybar

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Nachvollziehbarkeit von Problem-Änderungen.

---

### REQ-L3-ISSUE-004: Issue-Deletion mit Cascade-Cleanup

Bei Löschung eines Issues SHALL der IssueService:
1. Alle TraceLinks zum Issue löschen
2. WorkflowState-History löschen
3. Issue-Entität selbst löschen
4. Alles in einer Transaktion

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLinks werden gelöscht
- [ ] WorkflowState wird bereinigt
- [ ] Issue wird gelöscht
- [ ] Atomare Transaktion mit Rollback on Error

**Interfaces:** IF-AS-INT-002, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Referenzielle Integrität und Datenhygiene.

---

### REQ-L3-ISSUE-005: Issue-Status-Transitions mit Workflow-Engine

Der IssueService SHALL Workflow-State-Transitions für Issues delegieren an WorkflowFacade. Gültige Status sind:
- Open (initial)
- In Progress
- Resolved
- Closed
- Wontfix

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Transition wird an WorkflowFacade delegiert
- [ ] Erlaubte Übergänge gemäß WorkflowDefinition
- [ ] change_reason wird erfasst (wenn erforderlich)
- [ ] Audit-Log-Eintrag wird geschrieben
- [ ] Nur Open Issues können in In Progress wechseln

**Interfaces:** IF-AS-INT-003
**Traceability:** REQ-L1-029
**Rationale:** Controlled Issue-Lifecycle.

---

### REQ-L3-ISSUE-006: TraceLink-Verwaltung für Issue-Relationen

Der IssueService SHALL TraceLinks zwischen Issues und anderen Artefakten verwalten. Unterstützte Link-Typen:
- `related-to` (Issue ist verwandt mit Requirements, ArchitectureElements, Tests)
- `blocks` (Issue blockiert andere Requirements oder Issues)
- `blocked-by` (Issue wird blockiert von anderen Issues)
- `caused-by` (Issue wird verursacht durch Risk oder ADR-Entscheidung)
- `resolves` (Issue löst ein Test-Problem oder Anforderungs-Defekt)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLinks werden via TraceLinkService erstellt
- [ ] Link-Typ-Validierung
- [ ] Bidirektionale Querybarkeit
- [ ] Link-Erstellung ist optional

**Interfaces:** IF-AS-INT-002
**Traceability:** REQ-L1-029
**Rationale:** Impact-Analyse und Abhängigkeits-Management.

---

### REQ-L3-ISSUE-007: Issue-Priorisierung nach Severity

Der IssueService SHALL Issues nach Severity priorisieren können:
- Critical: sofortige Behandlung erforderlich
- High: behandeln innerhalb 1 Woche
- Medium: behandeln innerhalb 2 Wochen
- Low: behandeln im Standard-Zyklus

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Severity ist querybar und sortierbar
- [ ] Sorting nach Severity aufsteigend/absteigend
- [ ] Filtering nach Severity-Range möglich
- [ ] Severity wird in Result-Payload geliefert

**Interfaces:** IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Priorisierung für Triage und Reporting.

---

### REQ-L3-ISSUE-008: Assignee-Management und Change-Tracking

Der IssueService SHALL Assignee-Zuordnungen verwalten:
- Assignee kann bei Erstellung oder Update geändert werden
- assignee_changed_date wird aktualisiert
- Alte Assignee-Werte werden in Audit-Trail festgehalten

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Assignee wird validiert (existierender User)
- [ ] Assignee kann null sein (unassigned)
- [ ] Assignee-Wechsel wird in Audit-Log dokumentiert
- [ ] Query nach assignee_id möglich

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Verantwortlichkeits-Management.

---

### REQ-L3-ISSUE-009: Tenant-Isolation für Issues

Der IssueService SHALL garantieren:
1. Issues nur innerhalb gleicher Workspace
2. TraceLinks nicht Workspace-übergreifend
3. Alle Queries tenant-isoliert

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant wird aus Auth-Context extrahiert
- [ ] Issue wird mit tenant_id gekennzeichnet
- [ ] Keine Cross-Tenant-Queries
- [ ] Keine Cross-Tenant-TraceLinks

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Datenisolation.

---

### REQ-L3-ISSUE-010: Domain-Event-Publikation für Issue-Mutations

Nach erfolgreicher Mutation SHALL der IssueService Domain-Events publikzieren:
- `IssueCreated` (mit Issue-UUID und Snapshot)
- `IssueUpdated` (mit Issue-UUID und Änderungen)
- `IssueDeleted` (mit Issue-UUID)

Diese Events werden via DomainEventBus publiziert.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Events werden nach Commit publiziert
- [ ] Event-Payload ist strukturiert
- [ ] Events via IF-AS-INT-017 gestellt
- [ ] Fire-and-Forget (nicht-blockierend)

**Interfaces:** IF-AS-INT-017
**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Asynchrone Publikation für Audit und externe Systeme.

---

### REQ-L3-ISSUE-011: Issue-Abfragen und Listing

Der IssueService SHALL folgende Query-Operationen unterstützen:
- `get_by_id(issue_id)` → einzelnes Issue
- `list_by_workspace(workspace_id)` → alle Issues (paginiert)
- `list_by_status(workspace_id, status)` → gefiltert nach Status
- `list_by_severity(workspace_id, severity)` → gefiltert nach Severity
- `list_by_assignee(workspace_id, assignee_id)` → meine/assigned Issues
- `search(workspace_id, query_text)` → Volltextsuche

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Queries sind tenant-isoliert
- [ ] Pagination für `list_*`
- [ ] Multi-Filter möglich (status AND severity)
- [ ] Suchabfragen nutzen FTS
- [ ] Queries performant (≤500ms)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Abfrageunterstützung für Triage und Reporting.

---

## Traceability-Matrix: REQ-L3-ISSUE → REQ-L2/L1

| REQ-L3 | Primäre REQ-L2/L1 |
|--------|------------------|
| REQ-L3-ISSUE-001 | REQ-L1-029 |
| REQ-L3-ISSUE-002 | REQ-L1-029 |
| REQ-L3-ISSUE-003 | REQ-L1-029 |
| REQ-L3-ISSUE-004 | REQ-L1-029 |
| REQ-L3-ISSUE-005 | REQ-L1-029 |
| REQ-L3-ISSUE-006 | REQ-L1-029 |
| REQ-L3-ISSUE-007 | REQ-L1-029 |
| REQ-L3-ISSUE-008 | REQ-L1-029 |
| REQ-L3-ISSUE-009 | REQ-L2-AppSvc-022 |
| REQ-L3-ISSUE-010 | REQ-L2-AppSvc-026 |
| REQ-L3-ISSUE-011 | REQ-L1-029 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
