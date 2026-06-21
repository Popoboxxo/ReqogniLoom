# L3 AuditLogWriter Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AL-001 — AuditLogWriter
> **Parent-System:** AuditLogSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Append-Only-Persistierung von Audit-Eintraegen, atomare Transaktion mit ausloesender Operation, MCP-Anreicherung (Agent-Identitaet, API-Key-Hash); Tabelle ist monatlich per RANGE-Partitionierung auf `timestamp` partitioniert.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AL-001 | Vollstaendige Audit-Eintraege fuer alle Schreiboperationen (Create, Update, Delete) |
| REQ-L2-AL-002 | MCP-Audit-Anreicherung mit Agent-Identitaet und API-Key-Hash (SHA-256) |
| REQ-L2-AL-003 | Unveraenderlichkeit des Audit-Logs (Append-Only, DB-Constraint) |
| REQ-L2-AL-004 | Atomare Konsistenz mit ausloesender Operation (gleiche Transaktion) |
| REQ-L2-AL-006 | Tenant-Isolation: jeder Eintrag mit `tenant_id` versehen |
| REQ-L2-AL-008 | PostgreSQL-RANGE-Partitionierung auf `timestamp`, monatlich |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AL-INT-001 | ausgehend | COMP-AL-002 (AuditLogQuery) | Gemeinsames AuditLogEntry-Modell — nach INSERT lesbar (Read-Only fuer Query) |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AL-EXT-IN-001 | eingehend | DomainEventBus (post_commit) | `AuditableOperationOccurred`-Event mit Feldern: actor, actor_type, op, entity_type, entity_id, version, change_reason?, ctx |
| IF-AL-EXT-OUT-001 | ausgehend | PersistenceLayer (Django ORM) | AuditLogEntry-Entitaet (append-only), monatlich RANGE-partitioniert auf `timestamp` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AL001-001: Event-Bus-Subscription und Feld-Extraktion

Der AuditLogWriter SHALL sich als Subscriber am DomainEventBus fuer `AuditableOperationOccurred`-Events (post_commit) registrieren und alle Pflichtfelder (`actor`, `actor_type`, `op`, `entity_type`, `entity_id`, `version`, `timestamp`) sowie optionale Felder (`change_reason`, `ctx`) aus dem Event extrahieren und als AuditLogEntry persistieren.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] AuditLogWriter subscribes to `AuditableOperationOccurred` on DomainEventBus at application startup
- [ ] All mandatory event fields are mapped to AuditLogEntry columns without loss
- [ ] Missing optional fields (`change_reason`) result in NULL in DB, not an error
- [ ] Event with unknown extra fields is accepted (forward-compatible)

---

### REQ-L3-AL001-002: MCP-Kontext-Anreicherung

Der AuditLogWriter SHALL bei Eintraegen mit `actor_type = "agent"` die Felder `client_name`, `api_key_hash` (SHA-256 mit Prefix `sha256:`) und `source = "mcp"` aus dem `ctx`-Kontext des Events extrahieren und im AuditLogEntry persistieren. Der API-Key DARF NIEMALS im Klartext gespeichert werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] MCP event with API-Key in ctx → stored entry has `api_key_hash: "sha256:<hex>"`, no raw key present
- [ ] REST event → `source = "rest"`, `client_name = null`, `api_key_hash = null`
- [ ] DB column `api_key_raw` does not exist
- [ ] SHA-256 hash is reproducible: same key always produces same hash

---

### REQ-L3-AL001-003: Append-Only-Constraint auf Datenbankebene

Der AuditLogWriter SHALL die AuditLogEntry-Tabelle mit Datenbank-Constraints absichern, sodass UPDATE- und DELETE-Operationen auf persistierten Eintraegen abgelehnt werden. Die Komponente DARF keine `update_entry()`- oder `delete_entry()`-Methode exponieren.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Attempt to call `UPDATE auditlogentry SET ...` raises DB constraint error
- [ ] Attempt to call `DELETE FROM auditlogentry WHERE ...` raises DB constraint error
- [ ] AuditLogWriter public API exposes only `write(event)` — no update/delete methods
- [ ] Django model `Meta` or DB trigger enforces the constraint

---

### REQ-L3-AL001-004: Atomare Transaktion und Partition-Management

Der AuditLogWriter SHALL den INSERT in die AuditLogEntry-Tabelle innerhalb derselben Datenbank-Transaktion wie die ausloesende Geschaeftsoperation ausfuehren. Schlaegt der INSERT fehl, MUSS die gesamte Transaktion zurueckgerollt werden. Neue monatliche Partitionen MUESSEN automatisch zu Monatsbeginn erzeugt werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Simulated DB error after business INSERT → rollback: neither business entity nor audit entry in DB
- [ ] Audit INSERT error → business entity not persisted either
- [ ] On the 1st of each month: new partition for that month exists before first write
- [ ] Partition auto-creation is idempotent (no error if partition already exists)

---

### REQ-L3-AL001-005: Tenant-ID-Injektion

Der AuditLogWriter SHALL die `tenant_id` des aktiven Request-Kontexts automatisch in jeden AuditLogEntry injizieren. Fehlt die `tenant_id` im Kontext, MUSS der Write-Vorgang mit einem Fehler abgebrochen werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Write in tenant-T1 context → entry has `tenant_id = T1`
- [ ] Write attempt without active tenant context → raises `MissingTenantContextError`, no entry written
- [ ] Cross-tenant write is not possible via the public `write(event)` API

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
