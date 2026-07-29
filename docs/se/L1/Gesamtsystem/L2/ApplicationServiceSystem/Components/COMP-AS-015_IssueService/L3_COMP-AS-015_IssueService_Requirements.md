---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 IssueService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-015_IssueService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der IssueService verwaltet den vollständigen Lifecycle von Issue-Entitäten im ReqFlow-System. Er orchestriert CRUD-Operationen, delegiert Workflow-Transitions an die WorkflowFacade, verwaltet TraceLinks via TraceLinkService und publikziert Domain-Events via DomainEventBus. Issues sind zentrale Artefakte zur Dokumentation von identifizierten Problemen (Defects, Improvements), deren Severity, zuständigen Personen und Resolution-Status. Der Service implementiert Priorisierung nach Severity und Assignee-Management.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`IssueService` (Klasse):** Orchestrator für Issue-Operationen:
  - `create_issue(title, description, severity, category, assignee, due_date, tags, status, workspace_id, auth_context) → Issue`
  - `update_issue(issue_id, updates) → Issue`
  - `get_issue(issue_id) → Issue`
  - `list_issue(workspace_id, page, limit) → [Issue]`
  - `list_by_severity(workspace_id, severity) → [Issue]`
  - `list_by_assignee(workspace_id, assignee_id) → [Issue]`
  - `delete_issue(issue_id)`
  - `transition_status(issue_id, target_status, change_reason, auth_context) → Issue`
  - `create_tracelink(issue_id, target_id, link_type) → TraceLink`

- **`IssueValidator` (Klasse):** Validiert Issue-Payloads gegen Schema.

- **`AssigneeManager` (Klasse):** Verwaltet Assignee-Zuordnungen und Change-Tracking.

- **`IssueDTO` (DTO):** Data Transfer Object für Issue-Responses.

### 2.2 Datenstrukturen

- **Issue-Entity:**
  - `id`: UUID (PK)
  - `workspace_id`: UUID (FK)
  - `tenant_id`: UUID (FK)
  - `title`: String
  - `description`: String
  - `severity`: enum (critical, high, medium, low)
  - `category`: enum (defect, improvement, documentation, question)
  - `assignee_id`: UUID (optional, FK zu User)
  - `created_by`: String (User/Agent-ID)
  - `due_date`: DateTime (optional, ISO 8601)
  - `tags`: Array (optional, String-Array)
  - `status`: enum (Open, In Progress, Resolved, Closed, Wontfix)
  - `version`: Integer (Append-Only)
  - `created_at`, `updated_at`: DateTime
  - `assignee_changed_date`: DateTime (tracking)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-ISSUE-001 (Issue-Erstellung) | Methode `create_issue(payload)`: (1) Validiere Payload (title, description, severity, status erforderlich), (2) Erstelle Issue-Entity mit UUID, (3) Initialisiere WorkflowState (delegiere an WorkflowFacade für status=Open), (4) Persistiere atomare Transaktion. Rückgabe: Issue-UUID. |
| REQ-L3-ISSUE-002 (Issue-Metadaten) | Issue-Entity speichert: title, description, severity (critical/high/medium/low), category (defect/improvement/documentation/question), assignee (optional User/Agent), created_by (automatisch erfasst), due_date (optional, ISO 8601), tags (optional Array), status (enum). Alle Felder validiert. Severity ist querybar und sortierbar. |
| REQ-L3-ISSUE-003 (Update mit Versionierung) | Methode `update_issue(issue_id, updates)`: Alte Version beibehalten, neue Version mit version+1 erstellen. Timestamp und Actor erfasst. Audit-Trail vollständig. Versionsverlauf querybar. |
| REQ-L3-ISSUE-004 (Deletion mit Cascade-Cleanup) | Methode `delete_issue(issue_id)` in `transaction.atomic()`: (1) Lösche TraceLinks, (2) Lösche WorkflowState-History, (3) Lösche Issue. Bei Fehler: Rollback. |
| REQ-L3-ISSUE-005 (Status-Transitions) | Methode `transition_status(issue_id, target_status, change_reason)`: Delegiere an WorkflowFacade. Gültige Status: Open (initial) → In Progress (nur von Open) → Resolved → Closed (oder Wontfix). change_reason erfasst (wenn erforderlich). Audit-Log-Eintrag geschrieben. |
| REQ-L3-ISSUE-006 (TraceLink-Verwaltung) | Methode `create_tracelink(issue_id, target_id, link_type)`: Unterstützte Link-Typen: related-to, blocks (Issue blockiert andere), blocked-by (Issue blockiert von anderen), caused-by (Issue verursacht von Risk/ADR), resolves (Issue löst Test-Problem). Rufe TraceLinkService auf. Bidirektionale Querybarkeit. |
| REQ-L3-ISSUE-007 (Priorisierung nach Severity) | Issue-Priorisierung: Critical (sofortige Behandlung), High (1 Woche), Medium (2 Wochen), Low (Standard-Zyklus). Severity ist querybar und sortierbar. Sorting aufsteigend/absteigend. Filtering nach Severity-Range möglich (z.B. High+Critical). Severity wird in Result-Payload geliefert. |
| REQ-L3-ISSUE-008 (Assignee-Management) | Methode `assign_issue(issue_id, assignee_id)`: Validiere Assignee (existierender User). Assignee kann null sein (unassigned). Assignee-Wechsel wird in Audit-Log dokumentiert. assignee_changed_date aktualisiert. Query nach assignee_id möglich (list_by_assignee()). |
| REQ-L3-ISSUE-009 (Tenant-Isolation) | Tenant wird aus Auth-Context extrahiert. Issue wird mit tenant_id gekennzeichnet. Keine Cross-Tenant-Queries. Keine Cross-Tenant-TraceLinks. |
| REQ-L3-ISSUE-010 (Domain-Event-Publikation) | Nach erfolgreicher Mutation: Publiziere Event via DomainEventBus (post_commit Hook). Events: IssueCreated, IssueUpdated, IssueDeleted. Event-Payload strukturiert. Fire-and-Forget. |
| REQ-L3-ISSUE-011 (Abfragen und Listing) | Methoden: get_by_id(), list_by_workspace(), list_by_status(), list_by_severity(), list_by_assignee(), search(query_text). Alle Queries tenant-isoliert. Pagination. Multi-Filter möglich (status AND severity). FTS. Queries performant (≤500ms). |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API Endpoints für Issue CRUD.

- **Ausgänge (Outbound):**
  - **IF-AS-INT-002:** Aufruf TraceLinkService.
  - **IF-AS-INT-003:** Aufruf WorkflowFacade.
  - **IF-AS-INT-017 (Domain-Event):** Publikation IssueCreated/Updated/Deleted Events via DomainEventBus.
  - **IF-AS-EXT-OUT-007:** ORM-Aufrufe an PersistenceLayer.

---

## 5. Architectural Rationale

**ADR-L3-ISSUE-01 — Enum-Severity statt Freier Numerischer Priorisierung**

*Entscheidung:* Severity ist enum (critical, high, medium, low), nicht freie numerische Eingabe.

*Rationale:* Vereinfacht Klassifikation und Konsistenz. Benutzer wählt aus 4 Kategorien mit klaren SLA-Implikationen (Critical=sofort, High=1 Woche, etc.). Alternative: Numerische Priorisierung (1-10) → Inkonsistenzen zwischen Teams. **Abgelehnt**: Enum ist praktikabler und klarere Semantik.

*Erfüllt Trigger:* REQ-L3-ISSUE-002 (Issue-Metadaten), REQ-L3-ISSUE-007 (Priorisierung).

---

**ADR-L3-ISSUE-02 — Assignee-Tracking mit Change-History**

*Entscheidung:* Assignee-Zuordnungen werden tracked: assignee_changed_date aktualisiert bei Änderung, alte Werte im Audit-Log dokumentiert.

*Rationale:* Ermöglicht Accountability-Tracking: "Wer war wann für dieses Issue verantwortlich?" Alternative: Keine Assignee-History → schwerer nachzuverfolgeb, wer was wann übernommen hat. **Abgelehnt**: Issue-Management erfordert Change-Tracking für Verantwortlichkeit.

*Erfüllt Trigger:* REQ-L3-ISSUE-008 (Assignee-Management).

---

**ADR-L3-ISSUE-03 — Multi-Filter-Support (Status AND Severity)**

*Entscheidung:* Listing unterstützt Multi-Filter: `list(status=['Open', 'In Progress'], severity=['Critical', 'High'])` → Issues die Open/In Progress UND Critical/High sind.

*Rationale:* Praktischer für Triage: "Zeige mir alle offenen Critical/High Issues". Alternative: Nur Single-Filter → Nutzer müsste mehrere Queries kombinieren. **Abgelehnt**: Multi-Filter ist User-freundlicher.

*Erfüllt Trigger:* REQ-L3-ISSUE-011 (Abfragen und Listing).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
