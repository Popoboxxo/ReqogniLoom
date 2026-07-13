# L3 PerformanceOptimizationLayer Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PL-005 — PerformanceOptimizationLayer
> **Parent-System:** PersistenceLayerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

PostgreSQL-Indizes (BTree, GIST/GIN, tsvector), Connection-Pooling, Latenz-SLA-Monitoring. Stellt sicher, dass Datenbank-Abfragen die definierten Latenz-SLAs (< 200ms p95 Standard-Queries, < 500ms p95 Full-Text-Search) einhalten und dass Datenbankverbindungen effizient wiederverwendet werden.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PL-003 | Performance-Indizes (BTree, GIST/GIN, tsvector) |
| REQ-L2-PL-007 | Datenbankverbindungs-Pooling |
| REQ-L2-PL-008 | Performance-Latenzziele (< 200ms / < 500ms p95) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PL-INT-004 | eingehend | COMP-PL-004 | Migrationen enthalten `AddIndex`, `RemoveIndex` Operationen |
| IF-PL-INT-005 | ausgehend | COMP-PL-001 | `Meta.indexes` und `Index`-Klasse in Modell-Definitionen |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Vertrag |
|-------|----------|-------------|-----|---------|
| IF-PL-EXT-OUT-001 | ausgehend | PostgreSQL | TCP / psycopg2 | SQL, Connection-Pool-Parameter |
| IF-PL-EXT-IN-009 | eingehend | PostgreSQL-Verbindung | physical | TCP, .env Pool-Konfiguration |

## L3 Komponenten-Anforderungen

### REQ-L3-PL005-001: Pflichtindizes fuer alle definierten Query-Pfade


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der PerformanceOptimizationLayer MUSS folgende PostgreSQL-Indizes als Django-Migrationsoperationen bereitstellen: (1) BTree-Index auf `Artifact.parent_id` fuer Hierarchie-Queries, (2) GIN-Index auf `source_id` und `target_id` in `TraceLink` fuer Graph-Traversal-Queries, (3) tsvector-GIN-Index auf `to_tsvector('german', title || ' ' || description)` fuer die Entitaeten Requirement, ArchitectureElement und TestCase. Alle Indizes MUESSEN in Django-Migrationen als `AddIndex`-Operationen deklariert sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Django migration contains `AddIndex` for `Artifact.parent_id` (BTree)
- [ ] Django migration contains `AddIndex` for `TraceLink.source_id` and `target_id` (GIN)
- [ ] Django migration contains `AddIndex` for tsvector on Requirement, ArchitectureElement, TestCase
- [ ] `EXPLAIN ANALYZE` on tree query shows Index Scan (not Seq Scan)
- [ ] `EXPLAIN ANALYZE` on TraceLink query shows Bitmap Index Scan with GIN index
- [ ] `EXPLAIN ANALYZE` on full-text query shows GIN index usage

---

### REQ-L3-PL005-002: Konfigurierbare Connection-Pool-Parameter


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der PerformanceOptimizationLayer MUSS Django's `CONN_MAX_AGE`-Parameter und optionale Pool-Groessen-Parameter ueber Umgebungsvariablen steuerbar machen. Folgende Parameter MUESSEN unterstuetzt werden: `DB_CONN_MAX_AGE` (Sekunden, Standard: 60), `DB_POOL_SIZE` (maximale Pool-Groesse, Standard: 10). Bei 50 gleichzeitigen Requests DARF keine `OperationalError: too many connections`-Exception auftreten. Die Verbindungswiederverwendungsrate MUSS bei Lasttests > 80% betragen.

**Priority:** desired
**Acceptance Criteria:**
- [ ] `DB_CONN_MAX_AGE` env variable sets Django's `CONN_MAX_AGE`
- [ ] `DB_POOL_SIZE` env variable limits maximum pool size
- [ ] Load test (50 concurrent requests): no `OperationalError: too many connections`
- [ ] Connection reuse rate > 80% measured during load test

---

### REQ-L3-PL005-003: Latenz-SLA-Einhaltung unter Last


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der PerformanceOptimizationLayer MUSS in Kombination mit den definierten Indizes und Pool-Einstellungen sicherstellen, dass die folgenden Latenzziele bei 10.000 Items und 50 gleichzeitigen Nutzern eingehalten werden: Standard-CRUD-Queries < 200ms (p95), TraceLink-Graph-Queries < 200ms (p95), Recursive-CTE-Queries (500 Knoten) < 200ms (p95), Full-Text-Search < 500ms (p95). Die Messung MUSS gegen PostgreSQL mit produktionsaehnlichem Datensatz erfolgen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Load test: standard CRUD p95 < 200ms (10,000 items, 50 concurrent users)
- [ ] Load test: TraceLink upstream traversal p95 < 200ms
- [ ] Load test: Recursive CTE (500 nodes) p95 < 200ms
- [ ] Load test: full-text search (10,000 items) p95 < 500ms
- [ ] All measurements use `EXPLAIN ANALYZE` to confirm index usage

---

---

### REQ-L3-PL005-004: Indexing & Tree-Query Performance (M-03, M-04, M-10, M-11)

Der PerformanceOptimizationLayer MUSS N+1 Probleme in Hierarchien (z.B. `get_level()`) durch LTree-Extension oder rekursive CTEs (auf DB-Ebene) auflösen. Fehlende Foreign-Key-Indizes auf Target-Feldern von `TraceLink` und auf Polling-Relevanten Spalten (z.B. `status` in `DomainEventBus`) MÜSSEN zwingend hinzugefügt werden, um Full-Table-Scans zu verhindern. Das Connection-Pooling MUSS via PgBouncer betrieben werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von M-03, M-04, M-10, M-11.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-PL-025

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
