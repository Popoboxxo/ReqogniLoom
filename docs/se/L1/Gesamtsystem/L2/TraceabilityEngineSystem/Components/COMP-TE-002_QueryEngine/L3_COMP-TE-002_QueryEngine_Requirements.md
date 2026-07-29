decomposition_status: terminal

# L3 QueryEngine Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-TE-002 — QueryEngine
> **Parent-System:** TraceabilityEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Upstream/Downstream-Queries (direkte Nachbarn), transitive Hüllenberechnung (Impact-Analyse), Performance-optimierte Graph-Traversierung via PostgreSQL Recursive CTE.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-TE-004 | Upstream/Downstream-Graph-Query (direkte Nachbarn, ≤ 200ms p95) |
| REQ-L2-TE-005 | Transitive Hüllen-Query — Impact-Analyse (alle Ebenen, ≤ 200ms p95) |
| REQ-L2-TE-008 | Trace-Graph-Sammlung für Baseline-Snapshot (≤ 500ms) |
| REQ-L2-TE-012 | TraceLink-Query-Performance-SLA (GIST/GIN-Indizes) |
| REQ-L2-TE-019 | TraceLink Read-Model und Recursive CTE |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-INT-001 | eingehend | COMP-TE-001 TraceLinkManager | `get_trace_links(workspace_id, filters) -> TraceLink[]` |
| IF-TE-INT-003 | ausgehend | COMP-TE-001 TraceLinkManager | `validate_graph_integrity() -> ValidationResult` |
| IF-TE-INT-005 | eingehend | COMP-TE-004 VCRMReportGenerator | `query(artifact_id, direction, ctx) -> TraceLink[]` |

## Externe Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-EXT-IN-001 | eingehend | ApplicationService | `query(artifact_id, direction, ctx)` |
| IF-TE-EXT-IN-004 | eingehend | BaselineService | `collect_trace_graph(workspace_id, ctx)` |
| IF-TE-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM — Lesezugriff auf TraceLink-Entität |

---

## L3 Komponenten-Anforderungen

### REQ-L3-TE002-001: Upstream/Downstream-Query für direkte Nachbarn


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die QueryEngine SHALL für ein beliebiges Artefakt alle direkt verbundenen Knoten in Upstream- und Downstream-Richtung zurückgeben. Das Ergebnis SHALL für jeden Knoten Entity-ID, Entity-Typ, Link-Typ und Richtung enthalten. Die Antwortzeit SHALL ≤ 200ms (p95) bei bis zu 10.000 Items im Workspace betragen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `query_upstream(artifact_id)` → returns all direct upstream neighbors with link type and direction
- [ ] `query_downstream(artifact_id)` → returns all direct downstream neighbors with link type and direction
- [ ] Each result entry contains: `entity_id`, `entity_type`, `link_type`, `direction`
- [ ] Query on workspace with 10.000 items completes in ≤ 200ms (p95)
- [ ] Artifact with no links → returns empty list (no error)

---

### REQ-L3-TE002-002: Transitive Hüllen-Query (Impact-Analyse) via PostgreSQL Recursive CTE


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die QueryEngine SHALL transitive Hüllen über mehrere Ebenen berechnen und alle indirekt erreichbaren Knoten zurückgeben. Das Ergebnis SHALL Link-Typ, Richtung und Pfadtiefe (depth) pro Knoten enthalten. Die Berechnung SHALL via PostgreSQL Recursive CTE mit GIST/GIN-Indizes implementiert werden und ≤ 200ms (p95) bei 10.000 Items einhalten.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Chain A `derives-from` B `implements` C → `query_downstream(A, transitive=True)` → `{B (depth=1), C (depth=2)}`
- [ ] Result entries contain: `entity_id`, `link_type`, `direction`, `depth`
- [ ] Transitive query on 10.000 items → ≤ 200ms (p95)
- [ ] Cyclic graph (should not exist, but if present) → query terminates without infinite loop

---

### REQ-L3-TE002-003: Trace-Graph-Sammlung für Baseline-Snapshot


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die QueryEngine SHALL auf Anfrage des BaselineService den vollständigen Trace-Graph eines Workspaces als JSON-serialisierbare Datenstruktur zurückgeben. Das Ergebnis SHALL alle TraceLinks des Workspaces enthalten. Die Laufzeit SHALL ≤ 500ms (p95) bei 10.000 Items betragen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Workspace with 50 TraceLinks → `collect_trace_graph` returns structure with exactly 50 links
- [ ] Returned structure is JSON-serializable
- [ ] Empty workspace → returns empty graph structure (no error)
- [ ] 10.000 TraceLinks → ≤ 500ms (p95)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*

---

### REQ-L3-TE002-004: L3 Context Generators Implementation

Derives from REQ-L2-TRA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-TE002-005: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-TRA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
