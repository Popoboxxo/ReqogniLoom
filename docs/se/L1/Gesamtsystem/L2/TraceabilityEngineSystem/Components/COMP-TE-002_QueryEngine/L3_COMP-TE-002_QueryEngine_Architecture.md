---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:55:00Z"
schema_version: "1.0.0"
---

# L3 QueryEngine Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-TE-002_QueryEngine
> **Parent:** L2_TraceabilityEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die QueryEngine führt Graph-Traversierungen auf dem TraceLink-Graphen durch. Sie unterstützt Upstream/Downstream-Queries (direkte Nachbarn) mit ≤200ms p95, transitive Hüllen-Abfragen (Impact-Analyse) via PostgreSQL Recursive CTE, Trace-Graph-Sammlung für Baseline-Snapshots (≤500ms) und nutzt GIST/GIN-Indizes für Query-Optimierung.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`QueryEngine` (Klasse):** Hauptklasse mit Methoden `query_upstream`, `query_downstream`, `query_transitive`, `collect_trace_graph`.
- **`DirectNeighborQuery` (Klasse):** SQL-Builder für direkte Nachbarn. Nutzt einfache Joins auf TraceLink-Tabelle.
- **`TransitiveHullQuery` (Klasse):** SQL-Builder für Recursive CTE. Berechnet alle erreichbaren Knoten mit depth.
- **`TraceGraphCollector` (Klasse):** Aggregiert alle TraceLinks eines Workspaces in JSON-serialisierbare Struktur.
- **`QueryPerformanceMonitor` (Klasse):** Instrumentiert Query-Laufzeiten. Warnt bei SLA-Überschreitung.

### 2.2 Datenstrukturen

- **`NeighborResult` (Pydantic Model):** {entity_id, entity_type, link_type, direction}.
- **`TransitiveResult` (Pydantic Model):** {entity_id, link_type, direction, depth}.
- **`TraceGraph` (Pydantic Model):** {links: List[TraceLink]}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-TE002-001 (Upstream/Downstream) | DirectNeighborQuery filtert TraceLinks nach source/target. Upstream = target=artifact_id. Downstream = source=artifact_id. Response: {entity_id, entity_type, link_type, direction}. ≤200ms p95. |
| REQ-L3-TE002-002 (Transitive Hüllen via Recursive CTE) | TransitiveHullQuery baut PostgreSQL WITH RECURSIVE CTE. Startet von artifact_id, traversiert bis Blatt. Depth-Tracking. ≤200ms p95 bei 10.000 Items. Cyclic-Handling (sollte nicht vorkommen, aber defensiv). |
| REQ-L3-TE002-003 (Trace-Graph-Sammlung) | TraceGraphCollector lädt alle Links des Workspaces. JSON-Serialisierung. ≤500ms p95. Empty Workspace → empty graph (no error). |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-TE-EXT-IN-001:** Von ApplicationService: `query(artifact_id, direction, ctx) -> TraceLink[]`.
- **IF-TE-EXT-IN-004:** Von BaselineService: `collect_trace_graph(workspace_id, ctx) -> TraceGraph`.

**Ausgänge (Outbound):**
- **IF-TE-INT-001:** Zu COMP-TE-001 (TraceLinkManager): `get_trace_links(workspace_id, filters) -> TraceLink[]`.
- **IF-TE-INT-003:** Zu COMP-TE-001 (TraceLinkManager): `validate_graph_integrity() -> ValidationResult`.
- **IF-TE-INT-005:** Zu COMP-TE-004 (VCRMReportGenerator): `query(artifact_id, direction, ctx) -> TraceLink[]`.
- **IF-TE-EXT-OUT-001:** Zu PersistenceLayer (Django ORM): Lesezugriff auf TraceLink-Entity.

---

## 5. Architectural Rationale

**ADR-L3-TE2-01 — PostgreSQL Recursive CTE für Transitive Hüllen**

*Entscheidung:* TransitiveHullQuery nutzt native PostgreSQL Recursive CTE, nicht in-Application-Graph-Traversierung.

*Rationale:* Erfüllt REQ-L3-TE002-002 ("via PostgreSQL Recursive CTE ... ≤ 200ms (p95)"). Datenbank-native Lösung ist optimal für Graph-Traversierung. Alternative: Python NetworkX → würde alle Links laden, dann traversieren; zu langsam.

---

**ADR-L3-TE2-02 — GIST/GIN-Indizes für Query-Performance**

*Entscheidung:* Django-Model nutzt GIST- oder GIN-Indizes auf (source_id, target_id) Spalten.

*Rationale:* Erfüllt REQ-L3-TE002-001 und 002 ("GIST/GIN-Indizes"). GIST optimal für Range-Queries und Spatial-Daten. GIN für Exact-Match. Zusammen ermöglichen sie sublineare Query-Zeit. Alternative: Keine Indizes → würde O(N) Scans führen; violiert SLA.

---

**ADR-L3-TE2-03 — QueryPerformanceMonitor für SLA-Tracking**

*Entscheidung:* Jede Query wird instrumentiert. Laufzeit >= SLA-Schwelle → Warning-Log (kein Error, nicht kritisch).

*Rationale:* Ermöglicht proaktive Überwachung ohne Query zu blockieren. Fehler-Logs nur bei kritischen Problemen. Alternative: Silent Performance → würde Degradation nicht bemerken.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
