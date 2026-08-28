---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 DomainEventBus Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-016_DomainEventBus
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der DomainEventBus ist die zentrale Entkopplungs-Infrastruktur für asynchrone Event-basierte Kommunikation im ApplicationServiceSystem. Er publiziert typisierte Domain-Events durch Speicherung in einem Transactional Outbox Store (inline in der Mutation-Transaktion) für Durability und stellt sie asynchron an registrierte Subscriber zu (AuditLog, WebhookDispatcher, Metrics). Der EventBus garantiert Exactly-Once-Delivery und FIFO-Ordering pro Workspace sowie Entkopplung von schreibenden Domain-Services.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`DomainEventBus` (Singleton):** Zentrale Event-Bus-Engine:
  - `publish(domain_event)`: Speichert Event in Outbox-Tabelle (inline in Transaktion)
  - `register_subscriber(event_type, subscriber_callable)`: Registriert Subscriber
  - `unregister_subscriber(event_type, subscriber_id)`: Deregistriert Subscriber
  - `get_subscriber_registry()`: Gibt aktuelles Subscriber-Registry zurück

- **`OutboxPoller` (Worker/Task):** Asynchroner Worker (Celery/Django-Q):
  - Polliert Outbox-Tabelle regelmäßig (WHERE published=FALSE)
  - Selektiert Events mit SELECT FOR UPDATE (Locking)
  - Dispatcht Event an alle Subscriber
  - Markiert published=TRUE, published_at=NOW
  - Bei Fehler: Retry mit exponentieller Backoff, nach max_retries → DLQ

- **`EventValidator` (Klasse):** Validiert Event-Payloads gegen Schemata (JSON-Schema oder Pydantic).

- **`SubscriberRegistry` (Klasse):** Hashmap {event_type → [subscriber_callable]}.

- **`DLQManager` (Klasse):** Verwaltet Dead-Letter-Queue (domain_event_dlq Tabelle).

### 2.2 Datenstrukturen

- **domain_event_outbox Tabelle:**
  - `id` (PK)
  - `event_id` (UUID, unique)
  - `event_type` (enum: RequirementCreated, RequirementUpdated, ..., AdrCreated, RiskCreated, IssueCreated, WorkflowTransitioned, BaselineCreated)
  - `workspace_id` (UUID, FK)
  - `entity_id` (UUID, betroffenes Artefakt)
  - `payload` (JSONB)
  - `created_at` (Timestamp)
  - `published_at` (Timestamp, NULL bis publiziert)
  - `published` (Boolean, default FALSE)

- **domain_event_dlq Tabelle:**
  - `event_id`, `event_type`, `workspace_id`, `payload`, `error_message`, `retry_count`, `moved_at`

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-DEB-001 (Transactional Outbox Table) | Django-Model definiert domain_event_outbox mit Feldern: event_id (unique), event_type (enum), workspace_id, entity_id, payload (JSONB), created_at, published_at, published. Index auf (published, created_at) für Worker-Queries. |
| REQ-L3-DEB-002 (Event-Publikation im post_commit Hook) | Schreibende Domain-Services (RequirementService, etc.) rufen `DomainEventBus.publish(event)` inline auf, innerhalb derselben DB-Transaktion wie die Mutation. Rollback verhindert Event-Publikation. Multiple Events in einer Transaktion: alle oder keine publiziert. |
| REQ-L3-DEB-003 (Event-Typ-Definition und Schema) | Event-Types dokumentiert mit Payload-Schema (JSON-Schema oder Pydantic): RequirementCreated/Updated/Deleted (entity_id, workspace_id, title, description, parent_id, workflow_state), ArchitectureElementCreated/Updated/Deleted, TestCaseCreated/Updated/Deleted, BaselineCreated, WorkflowTransitioned (old_state, new_state, change_reason), Adr/Risk/IssueCreated/Updated/Deleted (mit relevanten Feldern). Validation vor Outbox-INSERT. |
| REQ-L3-DEB-004 (Asynchroner Worker-Dispatch) | OutboxPoller-Worker: Poll-Intervall (default 1s, konfigurierbar). Query: SELECT * FROM domain_event_outbox WHERE published=FALSE ORDER BY created_at LIMIT 100. SELECT FOR UPDATE für Locking. Dispatch Event an Subscriber. Bei Erfolg: UPDATE published=TRUE, published_at=NOW. Worker-Fehler geloggt. |
| REQ-L3-DEB-005 (Subscriber-Registration) | SubscriberRegistry: dict {event_type → [callables]}. Methode `register_subscriber(event_type, callable)` fügt hinzu. Event-Type-basierte Filterung: Nur Subscriber der passenden Event-Type werden benachrichtigt. Dynamische Registrierung/Deregistrierung. Mehrere Subscriber pro Type. Vordefinierte Subscriber: AuditLogWriter, WebhookDispatcher, SeMetrics. |
| REQ-L3-DEB-006 (Exactly-Once-Delivery) | (1) Durability: Events persistent in Outbox vor Dispatch. (2) Idempotenz: unique event_id, Duplicate-Events verworfen. (3) Ordering: FIFO pro Workspace (ORDER BY created_at). (4) Atomicity: published-Flag nur nach erfolgreicher Subscriber-Verarbeitung. Keine Event-Verluste auch bei Worker-Crash. |
| REQ-L3-DEB-007 (Dead-Letter-Queue) | Events, die nach max_retries (default 5) fehlschlagen, werden zu domain_event_dlq verschoben. DLQ speichert: event_id, event_type, workspace_id, payload, error_message, retry_count, moved_at. DLQ querybar (Admin-Interface). Manual Replay aus DLQ möglich. Metriken für DLQ-Größe. |
| REQ-L3-DEB-008 (Subscriber-Timeout und Graceful Degradation) | Subscriber-Timeout: 30s (konfigurierbar). Bei Timeout/Fehler eines Subscribers: Abbrechen, zu Retry-Queue hinzufügen. Andere Subscriber blockiert nicht. Fehlgeschlagene Subscriber geloggt. Exponential Backoff für Retries. Max 5 Retries pro Event. |
| REQ-L3-DEB-009 (Workspace-spezifisches Event-Processing) | workspace_id mandatory in allen Events. Subscriber-Dispatch filtert nach workspace_id (falls konfiguriert). Keine Cross-Workspace-Event-Publikation. Worker verarbeitet Events pro Workspace isoliert. |
| REQ-L3-DEB-010 (Monitoring und Metriken) | Metriken exponiert (Prometheus-Format, `/metrics` Endpoint): Events published per event_type (counter), Events pending (gauge: WHERE published=FALSE), Events in DLQ (gauge), Subscriber-Latenz p50/p95/p99 (histogram), Subscriber-Error-Rate (gauge). Event-Type-Aggregation. Subscriber-Performance trackbar. Alerts möglich. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-INT-009 bis 017:** Domain-Event-Publikation von schreibenden Services (inline in Transaktion, async dispatch): RequirementCreated/Updated/Deleted, ArchitectureElementCreated/Updated/Deleted, TestCaseCreated/Updated/Deleted, BaselineCreated, WorkflowTransitioned, AdrCreated/Updated/Deleted, RiskCreated/Updated/Deleted, IssueCreated/Updated/Deleted.

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-007:** INSERT Events in Outbox-Tabelle (PersistenceLayer).
  - **IF-AS-INT-013, 014:** Async Worker-Dispatch an WebhookDispatcher, AuditLog (async task call).

---

## 5. Architectural Rationale

**ADR-L3-DEB-01 — Transactional Outbox statt In-Memory Event-Queue**

*Entscheidung:* Events werden persistent in Outbox-Tabelle gespeichert (nicht In-Memory Queue), bevor sie dispatched werden.

*Rationale:* Garantiert Durability auch bei Service-Crash. In-Memory Queue würde Events verlieren bei Restart. Transactional Outbox ist DB-native Lösung ohne externe Dependencies (Redis, Kafka). Alternative: Kafka/RabbitMQ → zusätzliche Infrastruktur, Komplexität. **Abgelehnt**: Outbox ist simpler und DB-native.

*Erfüllt Trigger:* REQ-L3-DEB-001, REQ-L3-DEB-006 (Durability und Exactly-Once-Delivery).

---

**ADR-L3-DEB-02 — post_commit Hook für Event-Publikation** — *superseded (Systemaudit 2026-08-27, SA-02)*

*Entscheidung:* Events werden nach erfolgreicher DB-Commit publiziert (via `transaction.on_commit()`), nicht vor oder während Commit.

*Rationale:* Garantiert Konsistenz: Entweder DB-Change+Event existieren oder beide nicht. Keine Events ohne DB-Change. Alternative: Publish vor Commit → Event könnte verloren gehen bei Rollback. **Abgelehnt**: Konsistenz erfordert post_commit Hook.

*Erfüllt Trigger:* REQ-L3-DEB-002 (Event-Publikation im post_commit Hook).

*Supersession:* Der `on_commit()`-Hook selbst wurde als Bruch derselben Konsistenz-Garantie erkannt, die er herstellen sollte — der Hook feuert *nach* COMMIT, sodass ein Crash/OOM/Verbindungsabbruch in genau diesem Fenster die Mutation committed lässt, aber das Event dauerhaft verliert. Seit SA-02 (`backend/application/event_bus.py`) läuft der Outbox-INSERT stattdessen inline in derselben Transaktion wie die Mutation (klassisches Transactional-Outbox-Pattern, siehe ADR-L3-DEB-01). Diese ADR bleibt als historischer Entscheidungsrekord stehen, ist aber nicht mehr das implementierte Verhalten.

---

**ADR-L3-DEB-03 — SELECT FOR UPDATE Locking statt Optimistic Locking**

*Entscheidung:* Worker verwendet `SELECT ... FOR UPDATE` um Events zu locken, während sie verarbeitet werden. Verhindert Duplicate-Processing.

*Rationale:* Pessimistisches Locking (SELECT FOR UPDATE) verhindert sicher, dass zwei Worker dieselbe Event gleichzeitig verarbeiten. Optimistic Locking (version-Feld) würde Retries erfordern. Alternative: Kein Locking → Duplicate-Processing möglich (Event könnte zweimal dispatched werden). **Abgelehnt**: Exactly-Once-Delivery erfordert Locking.

*Erfüllt Trigger:* REQ-L3-DEB-006 (Exactly-Once-Delivery).

---

**ADR-L3-DEB-04 — Workspace-Isolierte Event-Verarbeitung**

*Entscheidung:* Events werden pro Workspace isoliert verarbeitet. Subscriber erhalten nur Events ihrer Workspace.

*Rationale:* Sicherheit und Datenisolation: Ein Tenant/Workspace soll nicht Events anderer sehen. FIFO-Ordering pro Workspace ist praktisch. Alternative: Global FIFO (alle Workspaces gemischt) → schwerer zu debuggen, Tenant-Isolation schwächer. **Abgelehnt**: Multi-Tenancy erfordert Workspace-Isolation.

*Erfüllt Trigger:* REQ-L3-DEB-009 (Workspace-spezifisches Event-Processing).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
