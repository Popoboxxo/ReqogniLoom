---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 AdrService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-013_AdrService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-029 (primär) — ADR-Management ist eine Cross-Cutting-Concern der L1
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der AdrService (Architectural Decision Record Service) verwaltet den vollständigen Lifecycle von ADR-Entitäten im ReqFlow-System. Er orchestriert CRUD-Operationen, delegiert Workflow-Transitions an die WorkflowEngine, Traceability-Verwaltung an die TraceabilityEngine und publikziert Domain-Events via DomainEventBus. ADRs sind zentrale Artefakte zur Dokumentation von Architektur-Entscheidungen und deren Rationale.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | ADR CRUD-Requests vom ApplicationService (create, update, get, list, delete) |
| IF-AS-INT-002 | output | data | TraceLink-Erstellung an TraceLinkService (`create_trace_link(source_id, target_id, link_type)`) |
| IF-AS-INT-003 | output | data | Workflow-State-Transition an WorkflowFacade (`transition(item_id, target_state, change_reason, ctx)`) |
| IF-AS-INT-015 | output | event | Domain-Event-Publikation (AdrCreated/Updated/Deleted) via DomainEventBus |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer (Django ORM) |

---

## L3 Component-Anforderungen

### REQ-L3-ADR-001: ADR-Erstellung mit Workflow-Initialisierung

Der AdrService SHALL ein neues ADR-Artefakt erstellen und folgende Schritte durchführen:
1. Validiere Payload (title, description, status obligatorisch)
2. Erstelle ADR-Entity mit eindeutiger UUID
3. Initialisiere WorkflowState gemäß aktiver WorkflowDefinition der Workspace
4. Persistiere Artefakt (Transactional)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] ADR wird mit valider UUID erstellt
- [ ] WorkflowState wird automatisch initialisiert
- [ ] Transaktionale Persistierung (atomic insert)
- [ ] Rückgabe der erstellten ADR-UUID

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-INT-003, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** ADRs sind versionierte Entscheidungsaufzeichnungen mit State-Management.

---

### REQ-L3-ADR-002: ADR-Update mit Versionierung

Der AdrService SHALL ADR-Updates mit Versionshistorie verwalten. Bei Änderungen an title, description oder status:
1. Alte Version wird unverändert beibehalten
2. Neue Version wird mit inkrementiertem version-Feld erstellt
3. Timestamp und Actor (User/Agent) werden erfasst

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alte ADR-Versionen bleiben lesbar
- [ ] Neue Version wird mit version+1 gekennzeichnet
- [ ] Audit-Trail ist vollständig (wer, wann, was geändert)
- [ ] Optimistic Locking verhindert Race-Conditions

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Unveränderlichkeit und Nachvollziehbarkeit.

---

### REQ-L3-ADR-003: ADR-Deletion mit Cascade-Cleanup

Bei Löschung eines ADRs SHALL der AdrService:
1. Alle TraceLinks zum ADR löschen (via TraceLinkService)
2. WorkflowState-History löschen
3. ADR-Entität selbst löschen
4. Alles in einer Transaktion (atomic)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLinks werden gelöscht
- [ ] WorkflowState wird bereinigt
- [ ] ADR wird gelöscht
- [ ] Rollback bei Fehler

**Interfaces:** IF-AS-INT-002, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Referenzielle Integrität und Datenhygiene.

---

### REQ-L3-ADR-004: ADR-Status-Transitions mit Workflow-Engine

Der AdrService SHALL Workflow-State-Transitions für ADRs delegieren an die WorkflowFacade. Gültige Status sind:
- Draft (initial)
- In Review
- Approved
- Rejected
- Superseded

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Transition wird an WorkflowFacade delegiert
- [ ] Erlaubte Übergänge werden gemäß WorkflowDefinition validiert
- [ ] change_reason wird erfasst (wenn erforderlich)
- [ ] Audit-Log-Eintrag wird geschrieben

**Interfaces:** IF-AS-INT-003, IF-AS-EXT-IN-001
**Traceability:** REQ-L1-029
**Rationale:** Konfigurierbare Workflow-Kontrolle.

---

### REQ-L3-ADR-005: TraceLink-Verwaltung für ADR-Relationen

Der AdrService SHALL TraceLinks zwischen ADRs und anderen Artefakten (Requirements, ArchitectureElements) verwalten. Unterstützte Link-Typen:
- `addresses` (ADR beantwortet ein Problem/Requirement)
- `supersedes` (ADR ersetzt frühere Entscheidung)
- `related-to` (ADR ist verwandt mit anderer ADR oder Architekt-Element)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLinks werden via TraceLinkService erstellt
- [ ] Link-Typ-Validierung gegen Whitelist
- [ ] Bidirektionale Querybarkeit (upstream/downstream)
- [ ] Link-Erstellung ist optional (keine Pflicht)

**Interfaces:** IF-AS-INT-002, IF-AS-EXT-IN-001
**Traceability:** REQ-L1-029
**Rationale:** Relationsmanagement und Impact-Analyse.

---

### REQ-L3-ADR-006: Tenant-Isolation für ADRs

Der AdrService SHALL garantieren, dass:
1. ADRs nur innerhalb der gleichen Workspace erstellt/aktualisiert werden
2. TraceLinks nicht Workspace-übergreifend erstellt werden können
3. Alle Queries tenant-isoliert sind (per Custom Manager)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant wird aus Auth-Context extrahiert
- [ ] ADR wird mit tenant_id gekennzeichnet
- [ ] Keine Cross-Tenant-Queries
- [ ] Keine Cross-Tenant-TraceLinks

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Datenisolation.

---

### REQ-L3-ADR-007: Domain-Event-Publikation für ADR-Mutations

Nach erfolgreicher Mutation (create, update, delete) SHALL der AdrService Domain-Events publikzieren:
- `AdrCreated` (mit ADR-UUID und Snapshot)
- `AdrUpdated` (mit ADR-UUID, alter/neuer Wert)
- `AdrDeleted` (mit ADR-UUID)

Diese Events werden via DomainEventBus publiziert und triggern Subscriber (AuditLog, Webhooks, Metriken).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Events werden nach Commit publiziert (post_commit Hook)
- [ ] Event-Payload ist strukturiert
- [ ] Events werden via IF-AS-INT-015 gestellt
- [ ] Event-Publishing ist Fire-and-Forget (nicht-blockierend)

**Interfaces:** IF-AS-INT-015
**Traceability:** REQ-L2-AppSvc-026 (DomainEventBus)
**Rationale:** Asynchrone Publikation für Audit und externe Systeme.

---

### REQ-L3-ADR-008: ADR-Abfragen und Listing

Der AdrService SHALL folgende Query-Operationen unterstützen:
- `get_by_id(adr_id)` → einzelnes ADR
- `list_by_workspace(workspace_id)` → alle ADRs der Workspace (paginiert)
- `list_by_status(workspace_id, status)` → gefiltert nach Status
- `search(workspace_id, query_text)` → Volltextsuche in title und description

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Query-Operationen sind tenant-isoliert
- [ ] Pagination wird für `list_*` unterstützt
- [ ] Suchabfragen nutzen PostgreSQL Full-Text-Search
- [ ] Queries sind performant (≤500ms für 1000 ADRs)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Abfrageunterstützung für UI und Agenten.

---

### REQ-L3-ADR-009: ADR-Validierung gegen Schema

Der AdrService SHALL alle ADR-Payloads gegen ein formales Schema validieren:
- `title`: string, 3-200 Zeichen, Pflicht
- `description`: string, max 10.000 Zeichen, Pflicht
- `status`: enum (Draft, In Review, Approved, Rejected, Superseded), Pflicht
- `context` (optional): string, max 5.000 Zeichen
- `consequences` (optional): string, max 5.000 Zeichen

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ungültige Payloads werden mit Error-Detail abgewiesen
- [ ] Längenbeschränkungen werden enforced
- [ ] Enum-Validierung erfolgt
- [ ] Rückgabefehler mit Feldname und Grund

**Interfaces:** IF-AS-EXT-IN-001
**Traceability:** REQ-L1-029
**Rationale:** Datenqualität und API-Konsistenz.

---

## Traceability-Matrix: REQ-L3-ADR → REQ-L2/L1

| REQ-L3 | Primäre REQ-L2/L1 |
|--------|------------------|
| REQ-L3-ADR-001 | REQ-L1-029 |
| REQ-L3-ADR-002 | REQ-L1-029 |
| REQ-L3-ADR-003 | REQ-L1-029 |
| REQ-L3-ADR-004 | REQ-L1-029 |
| REQ-L3-ADR-005 | REQ-L1-029 |
| REQ-L3-ADR-006 | REQ-L2-AppSvc-022 |
| REQ-L3-ADR-007 | REQ-L2-AppSvc-026 |
| REQ-L3-ADR-008 | REQ-L1-029 |
| REQ-L3-ADR-009 | REQ-L1-029 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
