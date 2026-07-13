# L3 AuditLogQuery Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AL-002 — AuditLogQuery
> **Parent-System:** AuditLogSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Paginierte Audit-Queries nach `entity_id`, `actor`, `operation`, `timestamp`, `source`; Tenant-Isolation; Performance-Ziele; stellt Daten fuer Archivierungs-Export bereit.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AL-005 | Query- und Retrieval-Faehigkeit mit Filter, Pagination, Sortierung |
| REQ-L2-AL-006 | Tenant-Isolation: Queries liefern ausschliesslich Eintraege des aktiven Tenants |
| REQ-L2-AL-007 | Performance-Ziele: entity_id-Query < 50ms (p95), Filterkombination < 200ms (p95) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AL-INT-001 | eingehend | COMP-AL-001 (AuditLogWriter) | Gemeinsames AuditLogEntry-Modell — Read-Only-Zugriff |
| IF-AL-INT-002 | eingehend | COMP-AL-003 (ArchiveLifecycleManager) | Lesezugriff auf Eintraege gefiltert nach `timestamp < (now - 2 Jahre)`, paginiert |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AL-EXT-IN-002 | eingehend | ApplicationService / UI | Query-Anfrage mit Filter-Parametern |
| IF-AL-EXT-OUT-001 | ausgehend | PersistenceLayer (Django ORM) | SELECT auf AuditLogEntry-Tabelle (partitioniert) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AL002-001: Filterbare, paginierte Query-Schnittstelle


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der AuditLogQuery SHALL eine In-Process-Python-Schnittstelle bereitstellen, die Audit-Eintraege nach den Feldern `entity_id`, `actor`, `operation`, `entity_type`, `source` und einem `timestamp`-Bereich ([from, to]) filtert. Ergebnisse MUSSEN paginiert (Default: 50, Maximum: 200 Eintraege pro Seite) und nach `timestamp` DESC sortiert zurueckgegeben werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Query `entity_id=X` returns exactly the entries for X, no entries for other IDs
- [ ] Query `actor=a&operation=delete&source=mcp` returns only matching entries
- [ ] Timestamp range filter `[from, to]` excludes entries outside the range
- [ ] Default page size = 50; `page_size=200` accepted; `page_size=201` raises validation error
- [ ] Results are sorted descending by `timestamp`

---

### REQ-L3-AL002-002: Tenant-Isolation via Custom Django Manager


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der AuditLogQuery SHALL saemtliche Queries ausschliesslich ueber einen Custom Django Manager ausfuehren, der `tenant_id` des aktiven Anfrage-Kontexts automatisch als Filterbedingung injiziert. Ohne aktiven Tenant-Kontext MUSS die Query mit einem Fehler abgebrochen werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Tenant T1 has 5 entries, T2 has 3. Query in T1 context returns exactly 5
- [ ] Query in T2 context returns exactly 3
- [ ] Direct ORM access bypassing the Custom Manager is blocked via model-level enforcement
- [ ] Query without active tenant context raises `MissingTenantContextError`

---

### REQ-L3-AL002-003: Performance-konforme Index-Nutzung


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der AuditLogQuery SHALL sicherstellen, dass Abfragen auf `entity_id` innerhalb von 50ms (p95) und Filterkombinationen innerhalb von 200ms (p95) bei 100.000 Eintraegen beantwortet werden. Dazu MUSSEN die Indizes auf `entity_id`, `(tenant_id, timestamp)` und `(actor, operation)` genutzt werden, und Timestamp-gefilterte Queries MUSSEN Partition-Pruning aktivieren.

**Priority:** desired

**Acceptance Criteria:**
- [ ] 100,000 entries in DB: query by `entity_id` completes in < 50ms (p95) across 10 runs
- [ ] Filter combination query completes in < 200ms (p95) across 10 runs
- [ ] EXPLAIN ANALYZE shows index scan (not seq scan) for entity_id queries
- [ ] EXPLAIN ANALYZE for timestamp-ranged query shows partition pruning (only relevant partitions accessed)

---

### REQ-L3-AL002-004: Paginierter Export-Cursor fuer Archivierungs-Lesezugriff


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der AuditLogQuery SHALL eine interne Methode bereitstellen, die dem ArchiveLifecycleManager (COMP-AL-003) Audit-Eintraege aelter als einen konfigurierbaren Cutoff-Timestamp seitenweise (Cursor-basiert oder Offset-basiert) zurueckliefert, ohne den gesamten Datensatz in den Speicher zu laden.

**Priority:** desired

**Acceptance Criteria:**
- [ ] `get_entries_before(cutoff, page_size=500)` returns entries with `timestamp < cutoff` in pages
- [ ] Memory usage stays below 100MB when exporting 1,000,000 entries (streamed via generator or cursor)
- [ ] All returned entries belong to the expected timestamp range
- [ ] Method is not exposed via external query interface (internal only)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
