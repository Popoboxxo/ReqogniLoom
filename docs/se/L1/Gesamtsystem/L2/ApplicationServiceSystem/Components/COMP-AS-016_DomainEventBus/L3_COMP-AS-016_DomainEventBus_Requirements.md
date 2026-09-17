---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 DomainEventBus Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-016_DomainEventBus
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-026 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der DomainEventBus ist die zentrale Entkopplungs-Infrastruktur für asynchrone Event-basierte Kommunikation im ApplicationServiceSystem. Er publiziert typisierte Domain-Events durch Speicherung in einem Transactional Outbox Store (inline in der Mutation-Transaktion) und stellt sie asynchron an registrierte Subscriber zu (AuditLogWriter, SeMetrics, WebhookDispatcher). Garantiert Exactly-Once-Delivery und Entkopplung von schreibenden Domain-Services.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-INT-009 bis 017 | input | event | Domain-Event-Publikation von schreibenden Services (inline in Transaktion, async dispatch) |
| IF-AS-EXT-OUT-007 | output | data | Transactional Outbox Table im PersistenceLayer (INSERT Events) |
| IF-AS-INT-013, 014 | output | async | Subscriber-Dispatch an WebhookDispatcher und AuditLog (async worker call) |
| (internal) | input | control | Worker-Queue-Polling (Django-Q/Celery) für Event-Processing |

---

## L3 Component-Anforderungen

### REQ-L3-DEB-001: Transactional Outbox Table

Der DomainEventBus SHALL Events in einer persistenten Outbox-Tabelle speichern (statt direkt in Memory):

**Tabelle: domain_event_outbox**
- `id` (PK)
- `event_id` (UUID, unique)
- `event_type` (enum: RequirementCreated, RequirementUpdated, RequirementDeleted, ArchitectureElementCreated/Updated/Deleted, TestCaseCreated/Updated/Deleted, BaselineCreated, WorkflowTransitioned, AdrCreated/Updated/Deleted, RiskCreated/Updated/Deleted, IssueCreated/Updated/Deleted)
- `workspace_id` (UUID, FK auf Workspace)
- `entity_id` (UUID, ID des betroffenen Artefakts)
- `payload` (JSONB, vollständige Event-Daten)
- `created_at` (Timestamp)
- `published_at` (Timestamp, NULL bis publiziert)
- `published` (Boolean, default FALSE)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tabelle wird als Django-Model definiert
- [ ] Event-Type wird als Enum/Choices konfiguriert
- [ ] Unique Constraint auf event_id (Idempotenz)
- [ ] Index auf (published, created_at) für Worker-Queries
- [ ] Payload wird als JSON gespeichert

**Interfaces:** IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Durability und Exactly-Once-Delivery garantiert durch DB-Persistierung.

---

### REQ-L3-DEB-002: Event-Publikation in Transactionaler Outbox

Die schreibenden Domain-Services publizieren Events durch Speicherung in der Outbox-Tabelle inline, in derselben Transaktion wie die Datenmutation:
- `DomainEventBus.publish(event)` wird innerhalb der Transaction aufgerufen
- Outbox-Row wird in derselben Transaktion wie die Mutation geschrieben
- Event ist persistent, bevor der Commit erfolgreich ist

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Outbox-INSERT erfolgt inline in der Mutation-Transaktion (kein post_commit Hook)
- [ ] Rollback verhindert sowohl Mutation als auch Event-Publikation
- [ ] Multiple Events in einer Transaktion werden alle oder keine publiziert
- [ ] Outbox-Fehler propagieren und verursachen Rollback der gesamten Mutation

**Interfaces:** IF-AS-INT-009, 010, 011, 012, 015, 016, 017, IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Garantierte Konsistenz: DB-Change ↔ Event-Publikation.

---

### REQ-L3-DEB-003: Event-Typ-Definition und Schema

Der DomainEventBus SHALL folgende Event-Typen und deren Payload-Schema definieren:

**RequirementCreated/Updated/Deleted:**
- entity_id, workspace_id, title, description, parent_id, workflow_state

**ArchitectureElementCreated/Updated/Deleted:**
- entity_id, workspace_id, element_type, title, description, version

**TestCaseCreated/Updated/Deleted:**
- entity_id, workspace_id, test_type, title, execution_status

**BaselineCreated:**
- entity_id, workspace_id, baseline_name, scope, snapshot_json

**WorkflowTransitioned:**
- entity_id, workspace_id, old_state, new_state, change_reason

**AdrCreated/Updated/Deleted, RiskCreated/Updated/Deleted, IssueCreated/Updated/Deleted:**
- entity_id, workspace_id, title, description, status/severity

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Event-Typen sind dokumentiert
- [ ] Payload-Schema ist definiert (JSON-Schema oder Pydantic)
- [ ] Validation erfolgt vor Outbox-INSERT
- [ ] Ungültige Events werden abgewiesen

**Interfaces:** IF-AS-INT-009, 010, 011, 012, 015, 016, 017
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Konsistente und validierbare Event-Struktur.

---

### REQ-L3-DEB-004: Asynchroner Worker-basierter Dispatch

Der DomainEventBus SHALL Events asynchron an Subscriber dispatchen via Worker-Queue (Django-Q oder Celery):
- Worker fragt regelmäßig Outbox-Tabelle ab (WHERE published = FALSE)
- Worker sortiert Events nach created_at (FIFO-Ordering)
- Worker lockt Event für Verarbeitung (SELECT FOR UPDATE)
- Worker dispatcht Event an registrierte Subscriber
- Bei Erfolg: Event wird als published = TRUE markiert, published_at aktualisiert

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Worker wird als Celery/Django-Q task implementiert
- [ ] Poll-Intervall ist konfigurierbar (default 1s)
- [ ] SELECT FOR UPDATE verhindert Duplicate-Processing
- [ ] Worker-Fehler werden geloggt
- [ ] Dead-Letter-Queue für fehlgeschlagene Events (nach max retries)

**Interfaces:** IF-AS-INT-013, 014, IF-AS-EXT-OUT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Nicht-blockierende Delivery garantiert schnelle API-Antworten.

---

### REQ-L3-DEB-005: Subscriber-Registration und Dispatch

Der DomainEventBus SHALL ein Subscriber-Registry anbieten:
- `register_subscriber(event_type, subscriber_callable)`
- Subscriber wird nach Event-Type gefiltert
- Event wird an alle registrierten Subscriber dieser Event-Type dispatched

Vordefinierte Subscriber:
- AuditLogWriter (all write events)
- WebhookDispatcher (RequirementCreated/Updated, WorkflowTransitioned, BaselineCreated)
- SeMetrics (all write events, für Metriken-Aggregation)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Subscriber-Registry ist implementiert
- [ ] Event-Type-basierte Filterung funktioniert
- [ ] Subscriber werden in Konfiguration definiert (nicht hard-coded)
- [ ] Subscriber können dynamisch registriert/de-registriert werden
- [ ] Mehrere Subscriber derselben Type möglich

**Interfaces:** IF-AS-INT-013, 014
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Erweiterbarkeit und Entkopplung.

---

### REQ-L3-DEB-006: Exactly-Once-Delivery Semantik

Der DomainEventBus SHALL Exactly-Once-Delivery garantieren:
1. Durability: Events werden persistent in Outbox gespeichert vor Dispatch-Versuch
2. Idempotenz: Event-ID ist unique, Duplicate-Events werden ignoriert
3. Ordering: Events werden pro Workspace in FIFO-Reihenfolge dispatched
4. Atomicity: Event-Status wird nur nach erfolgreicher Subscriber-Verarbeitung aktualisiert

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Duplicate event_ids werden verworfen (unique constraint)
- [ ] Workspace-spezifisches FIFO-Ordering
- [ ] Event-Status wird nur nach SUCCESS aktualisiert
- [ ] Keine Event-Verluste auch bei Worker-Crash (Durability)

**Interfaces:** IF-AS-EXT-OUT-007, IF-AS-INT-013, 014
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Zuverlässigkeitszusage für Subscription-basierte Systeme.

---

### REQ-L3-DEB-007: Dead-Letter-Queue und Fehlerbehandlung

Events, die nach max_retries (default 5) fehlschlagen, werden in Dead-Letter-Queue verschoben:

**DLQ-Tabelle: domain_event_dlq**
- `event_id`, `event_type`, `workspace_id`, `payload`, `error_message`, `retry_count`, `moved_at`

Operatoren können DLQ inspizieren und manuell erneut versuchen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Fehlgeschlagene Events werden nach max_retries in DLQ verschoben
- [ ] DLQ ist querybar (Admin-Interface)
- [ ] Error-Message wird mit Event gespeichert
- [ ] Manual Replay aus DLQ möglich
- [ ] Metriken für DLQ-Größe verfügbar

**Interfaces:** IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Operational Visibility und Recovery-Optionen.

---

### REQ-L3-DEB-008: Subscriber-Timeout und Graceful Degradation

Wenn ein Subscriber fehlschlägt oder zu lange dauert (Timeout > 30s):
- Event-Verarbeitung wird abgebrochen
- Event wird zu Retry-Queue hinzugefügt
- Andere Subscriber werden nicht blockiert
- Worker versucht Event später erneut

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Subscriber-Timeout ist 30s (konfigurierbar)
- [ ] Subscriber-Fehler blockiert nicht andere Subscriber
- [ ] Fehlgeschlagene Subscriber werden geloggt
- [ ] Retry-Logik verwendet Exponential Backoff
- [ ] Max 5 Retries pro Event

**Interfaces:** IF-AS-INT-013, 014
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Robustheit bei Subscriber-Fehlern.

---

### REQ-L3-DEB-009: Workspace-spezifisches Event-Processing

Der DomainEventBus SHALL Events pro Workspace isoliert verarbeiten:
- Subscriber erhalten nur Events ihrer eigenen Workspace
- Keine Cross-Workspace-Event-Publikation
- workspace_id wird in Event-Payload und Outbox-Table erfasst

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] workspace_id ist mandatory in allen Events
- [ ] Subscriber-Dispatch filtert nach workspace_id
- [ ] Keine Cross-Tenant-Event-Leak
- [ ] Workspace-spezifische Subscriber-Registrierung möglich

**Interfaces:** IF-AS-EXT-OUT-007, IF-AS-INT-013, 014
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Datenisolation.

---

### REQ-L3-DEB-010: Monitoring und Metriken

Der DomainEventBus SHALL Metriken exponieren:
- Events published per event_type (counter)
- Events pending (gauge: WHERE published = FALSE)
- Events in DLQ (gauge)
- Subscriber-Latenz p50/p95/p99 (histogram)
- Subscriber-Error-Rate (gauge)

Diese Metriken sind Prometheus-kompatibel und über `/metrics`-Endpoint abrufbar.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Metriken werden in Prometheus-Format exponiert
- [ ] Event-Type-Aggregation ist vorhanden
- [ ] Subscriber-Performance ist trackbar
- [ ] Alerts sind möglich (z.B. >100 pending Events)

**Interfaces:** (metrics export, keine inter-service IF)
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Operational Observability.

---

## Traceability-Matrix: REQ-L3-DEB → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-DEB-001 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-002 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-003 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-004 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-005 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-006 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-007 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-008 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-009 | REQ-L2-AppSvc-022, REQ-L2-AppSvc-026 |
| REQ-L3-DEB-010 | REQ-L2-AppSvc-026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


---

### REQ-L3-DEB-011: Atomare Event-Bus Claims & DLQ-Moves (S-01, S-02, S-20)

Der `DomainEventBus` MUSS beim Polling von Outbox-Events eine Race-Condition durch atomare Datenbank-Claims (z.B. `select_for_update(skip_locked=True)` in einer `transaction.atomic()`) verhindern. Das Verschieben in die DLQ und Löschen in der Outbox MÜSSEN in derselben Transaktion erfolgen (Split-Brain Vermeidung). Die Funktionalität MUSS dediziert getestet werden (`dlq_service`).

**Implementation State:** Planned
**Review Findings:** Abgeleitet von S-01, S-02, S-20.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-AS-040

---

## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-DEB-001 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-002 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-003 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-004 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-005 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-006 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-007 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-008 | REQ-L2-AppSvc-026 |
| REQ-L3-DEB-009 | REQ-L2-AppSvc-022 |
| REQ-L3-DEB-010 | REQ-L2-AppSvc-026 |

