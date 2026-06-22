---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 AuditLogWriter Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AL-001_AuditLogWriter
> **Parent:** L2_AuditLogSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der AuditLogWriter ist die einzige Schreibkomponente für das Audit-Log. Er ist verantwortlich für:
- Event-Bus-Subscription und Feld-Extraktion aus `AuditableOperationOccurred`-Events
- MCP-Kontext-Anreicherung (Agent-Identität, API-Key-Hash)
- Append-Only-Persistierung mit Datenbank-Constraints
- Transaktionale Konsistenz mit der auslösenden Operation
- Tenant-ID-Injektion in jeden Audit-Eintrag
- Automatische Partition-Verwaltung (monatlich)

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AuditLogWriter` (Hauptklasse):** DomainEventBus-Subscriber, `write(event)` Public-API.
- **`EventSubscriber` (Module):** Registriert sich beim DomainEventBus für `AuditableOperationOccurred` beim Startup.
- **`ContextEnricher` (Module):** Extrahiert MCP-Felder aus `ctx`, berechnet SHA-256 API-Key-Hash.
- **`TenantContextInjector` (Module):** Liest `tenant_id` aus Request-Context, validiert.
- **`PartitionManager` (Module):** Erstellt neue Monthly-Partitionen am Monatsbeginn.
- **`AuditLogEntryDTO`:** Interne Repräsentation eines Audit-Eintrags.

### 2.2 Datenstrukturen

- **AuditLogEntry-Entity (Append-Only):**
  - `id`: BIGSERIAL (auto-increment, Primary Key)
  - `tenant_id`: UUID (nicht-null, Tenant-Isolation)
  - `actor`: String (user_id oder agent_id)
  - `actor_type`: String (user|agent)
  - `op`: String (create|update|delete)
  - `entity_type`: String (Requirement|Artifact|ArchitectureElement|TestCase)
  - `entity_id`: UUID
  - `version`: Integer (optional, nach Mutation)
  - `change_reason`: Text (nullable, optional)
  - `timestamp`: DateTime (wird mit ON INSERT DEFAULT CURRENT_TIMESTAMP gesetzt)
  - `source`: String (rest|mcp)
  - `client_name`: String (nullable, nur bei MCP)
  - `api_key_hash`: String (nullable, nur bei MCP, SHA-256)

- **Datenbank-Constraint:**
  - `ALTER TABLE auditlogentry ADD CONSTRAINT no_updates CHECK (false) ON INSERT DO ALSO NULL;` (verhindert UPDATE/DELETE via Trigger)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AL001-001 (Event-Subscription und Feld-Extraktion) | EventSubscriber registriert sich im __init__ beim DomainEventBus. Callback extrahiert alle Felder, ContextEnricher reichert an. |
| REQ-L3-AL001-002 (MCP-Anreicherung) | Bei actor_type="agent": ctx.client_name + ctx.api_key (SHA-256-Hashing via hmac.new(b'', key, hashlib.sha256).hexdigest()). Niemals Klartext. |
| REQ-L3-AL001-003 (Append-Only-Constraint) | DB-Trigger: nach INSERT auf auditlogentry, alle UPDATE/DELETE-Attempts blockieren. Django-Model exponiert kein `update()` oder `delete()`. |
| REQ-L3-AL001-004 (Atomare TX und Partition-Management) | write() partizipiert in Caller-TX. PartitionManager läuft als Celery-Beat-Task monatlich oder wird on-demand bei fehlender Partition aufgerufen. |
| REQ-L3-AL001-005 (Tenant-ID-Injektion) | TenantContextInjector liest aktiven Tenant aus Request-Context. Fehlt er: MissingTenantContextError werfen. Jeder INSERT enthält tenant_id. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AL-EXT-IN-001:** `DomainEventBus` — Subscription auf `AuditableOperationOccurred`-Events (post_commit)

- **Ausgänge (Outbound):**
  - **IF-AL-INT-001:** Gemeinsames AuditLogEntry-Modell mit `COMP-AL-002` (AuditLogQuery)
  - **IF-AL-EXT-OUT-001:** Django ORM — INSERT in AuditLogEntry (RANGE-partitioniert)

---

## 5. Architectural Rationale

**ADR-L3-AL001-01 — Event-Bus-Subscriber Pattern für Entkopplung**

*Entscheidung:* AuditLogWriter registriert sich als asynchroner Subscriber am DomainEventBus. Business-Operations publishen Events; AuditLogWriter listens async und persistiert.

*Rationale:*
- **Annahme:** Audit-Logging soll Business-Operations nicht blockieren, ist aber sicherheitskritisch.
- **Gewählter Ansatz:** Event-Bus-Subscription mit post_commit-Hook im selben TX wie Business-OP, asynchrones Consume.
- **Abgelehnte Alternative:** Direkte Audit-API-Aufrufe in jedem Service → Boilerplate, Coupling.
- **Erfüllt REQ-L3-AL001-001:** Entkopplung ist klar, Feld-Mapping ist zentral.

---

**ADR-L3-AL001-02 — SHA-256-Hashing mit Prefix für API-Keys**

*Entscheidung:* API-Keys werden mit SHA-256 gehashed und mit `sha256:`-Prefix verspeichert. Der Klartext-Key wird NIEMALS gespeichert oder geloggt.

*Rationale:*
- **Annahme:** REQ-L3-AL001-002 fordert Sicherheit; API-Keys sind sensibel.
- **Gewählter Ansatz:** Prefix erlaubt Unterscheidung von Hash-Algorithmen in der Zukunft (SHA-256 vs. argon2, etc.).
- **Abgelehnte Alternative:** Klartext-Speicherung — Sicherheitsrisiko.
- **Erfüllt REQ-L3-AL001-002:** Sicherheit ist garantiert, Audit-Log ist sicher.

---

**ADR-L3-AL001-03 — DB-Trigger für Append-Only-Constraint**

*Entscheidung:* Die AuditLogEntry-Tabelle hat einen DB-Trigger, der UPDATE- und DELETE-Attempts blockiert. Django-Model exponiert kein `update()` oder `delete()`.

*Rationale:*
- **Annahme:** REQ-L3-AL001-003 fordert Unveränderlichkeit auf DB-Ebene, nicht nur auf Applikations-Ebene.
- **Gewählter Ansatz:** Datenbank-Trigger + AppCode-Guard (kein delete() public).
- **Abgelehnte Alternative:** Nur Applikations-Guard → DB-Admin könnte bypass via psql.
- **Erfüllt REQ-L3-AL001-003:** Append-Only ist garantiert.

---

**ADR-L3-AL001-04 — Monatliche RANGE-Partitionierung auf timestamp**

*Entscheidung:* AuditLogEntry-Tabelle ist nach `timestamp` mit monatlicher Granularität partitioniert. PartitionManager erstellt neue Partitionen am Monatsbeginn.

*Rationale:*
- **Annahme:** REQ-L3-AL001-004 fordert Partition-Management. Monatliche Granularität passt zu ArchiveLifecycleManager (2-Jahres-Retention = ~24 Partitionen).
- **Gewählter Ansatz:** `PARTITION BY RANGE (YEAR_MONTH(timestamp))`. Neue Partition auto-erstellt via Celery-Beat-Job am 1. des Monats.
- **Abgelehnte Alternative:** Keine Partitionierung — Tabelle wird schnell sehr groß (>Millionen Rows/Monat).
- **Erfüllt REQ-L3-AL001-004:** Performance und Lifecycle-Management sind optimiert.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
