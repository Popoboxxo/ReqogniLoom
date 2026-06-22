---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 AuditLogQuery Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AL-002_AuditLogQuery
> **Parent:** L2_AuditLogSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die AuditLogQuery ist die einzige Leskomponente für das Audit-Log. Sie ist verantwortlich für:
- Filterbare, paginierte Query-Schnittstelle mit Multi-Field-Filtern
- Tenant-Isolation via Custom Django Manager
- Performance-konforme Index-Nutzung
- Paginierter Export-Cursor für Archive-Lifecycle-Manager

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AuditLogQuery` (Hauptklasse):** Public API für `query()`, `get_entries_before()`.
- **`TenantIsolatingManager` (Custom Django Manager):** Filters alle Queries automatisch auf aktiven Tenant.
- **`QueryBuilder` (Module):** Konstruiert ORM-Queries mit Filtern (entity_id, actor, operation, source, timestamp-range).
- **`PaginationHelper` (Module):** Verwaltet Offset-Pagination (Default 50, Max 200).
- **`AuditLogEntryDTO` / `PaginatedResultDTO`:** API-Datenstrukturen.

### 2.2 Datenstrukturen

- **Datenbankindizes:**
  - `idx_auditlogentry_entity_id` on `(entity_id)`
  - `idx_auditlogentry_tenant_timestamp` on `(tenant_id, timestamp)` — für Partition Pruning
  - `idx_auditlogentry_actor_operation` on `(actor, operation)`

- **PaginatedResultDTO:**
  ```json
  {
    "total": 42,
    "page": 1,
    "page_size": 50,
    "entries": [/* AuditLogEntry objects */]
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AL002-001 (Filterbare, paginierte Query) | `query(entity_id=None, actor=None, operation=None, source=None, timestamp_from=None, timestamp_to=None, page=1, page_size=50, ctx)`: QueryBuilder konstruiert ORM, PaginationHelper paginiert, sortiert DESC nach timestamp. |
| REQ-L3-AL002-002 (Tenant-Isolation) | TenantIsolatingManager: alle Queries filtern automatisch auf `tenant_id` aus Request-Context. Fehlt Kontext: MissingTenantContextError. Django-Model nutzt nur diesen Custom Manager. |
| REQ-L3-AL002-003 (Performance via Indizes) | Indizes auf entity_id, (tenant_id, timestamp), (actor, operation). Query-Planner nutzt diese für Index Scans statt Seq Scans. |
| REQ-L3-AL002-004 (Export-Cursor) | `get_entries_before(cutoff_timestamp, page_size=500, ctx)`: Generator-basiert oder Cursor-Loop, streamt Daten, minimaler Memory-Footprint. Nur intern nutzbar. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AL-EXT-IN-002:** `ApplicationService` / UI — Query-Anfragen
  - **IF-AL-INT-002:** `COMP-AL-003` (ArchiveLifecycleManager) — Export-Cursor-Anfragen

- **Ausgänge (Outbound):**
  - **IF-AL-INT-001:** Gemeinsames AuditLogEntry-Modell mit `COMP-AL-001` (AuditLogWriter)
  - **IF-AL-EXT-OUT-001:** Django ORM — SELECT auf AuditLogEntry (partitioniert)

---

## 5. Architectural Rationale

**ADR-L3-AL002-01 — Custom Manager für Tenant-Isolation**

*Entscheidung:* AuditLogEntry nutzt einen Custom Django Manager `TenantIsolatingManager`, der automatisch alle Queries auf den aktiven Tenant filtert.

*Rationale:*
- **Annahme:** REQ-L3-AL002-002 fordert Tenant-Isolation auf alle Queries. Direct ORM access muss blockiert sein.
- **Gewählter Ansatz:** Custom Manager mit Override von `get_queryset()` → Automatische Tenant-Filterung.
- **Abgelehnte Alternative:** Manuelles Filterung in jedem Query-Call → Fehleranfällig, Boilerplate.
- **Erfüllt REQ-L3-AL002-002:** Tenant-Isolation ist systematisch, nicht vergessbar.

---

**ADR-L3-AL002-02 — Mehrschichtiger Filter auf entity_id, actor, operation, source, timestamp**

*Entscheidung:* `query()` akzeptiert optionale Filter für alle wichtigen Felder. QueryBuilder kombiniert sie mittels AND-Logik in die ORM.

*Rationale:*
- **Annahme:** REQ-L3-AL002-001 fordert flexible Multi-Field-Filterung.
- **Gewählter Ansatz:** Optionale Parameter mit Q-Objects oder filter()-Verkettung.
- **Abgelehnte Alternative:** Separate Query-Methoden für jede Filter-Kombination → Explosion.
- **Erfüllt REQ-L3-AL002-001:** Flexibilität bei Performance.

---

**ADR-L3-AL002-03 — Paginierter Export-Cursor für Speichereffizienz**

*Entscheidung:* `get_entries_before()` ist ein Generator oder nutzt einen DB-Cursor (`.iterator()` in Django), um Speicher bei Millionen-Exports zu sparen.

*Rationale:*
- **Annahme:** REQ-L3-AL002-004 fordert Memory-Effizienz bei großen Exports.
- **Gewählter Ansatz:** Generator/Iterator Pattern, nicht alle Rows in RAM laden.
- **Abgelehnte Alternative:** Liste aller Rows zurück → >100MB RAM bei 1M Rows.
- **Erfüllt REQ-L3-AL002-004:** Speichereffizienz ist garantiert.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
