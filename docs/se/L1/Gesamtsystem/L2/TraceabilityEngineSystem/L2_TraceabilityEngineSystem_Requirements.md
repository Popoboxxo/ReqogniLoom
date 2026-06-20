# L2 TraceabilityEngine Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** TraceabilityEngineSystem (ARCH-L1-007)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-003 (primär), REQ-L1-001 (mitwirkend), REQ-L1-004 (mitwirkend), REQ-L1-008 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend), REQ-L1-015 (mitwirkend), REQ-L1-020 (mitwirkend), REQ-L1-025 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-TE-EXT-IN-001 | input | data | `query(artifact_id, direction, ctx)` von ApplicationService |
| IF-TE-EXT-IN-002 | input | data | `coverage(workspace_id, filters?, ctx)` von ApplicationService |
| IF-TE-EXT-IN-003 | input | data | TraceLink-CRUD von ApplicationService |
| IF-TE-EXT-IN-004 | input | data | `collect_trace_graph(workspace_id, ctx)` von BaselineService |
| IF-TE-EXT-OUT-001 | output | data | Django ORM Persistenz an ARCH-L1-010 |

---

## L2 Subsystem-Anforderungen

### REQ-L2-TE-001: TraceLink-Verwaltung mit 6 Link-Typen

Die TraceabilityEngine SHALL TraceLinks zwischen Requirements, ArchitectureElements und TestCases verwalten. Unterstützte Link-Typen: `parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`. Source und Target MÜSSEN demselben Tenant angehören.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erstelle TraceLink (source=Req-A, target=Arch-B, type=`satisfies`) → TraceLink mit UUID
- [ ] TraceLink ohne Source → Fehler `"Source entity not found"`
- [ ] Cross-Tenant-Link → Fehler `"Cross-tenant link not allowed"`
- [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
- [ ] Delete → TraceLink entfernt

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001, IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-003, REQ-L1-015 (mitwirkend)
**Rationale:** TraceLink-CRUD mit 6 Link-Typen ist die Kernfunktion.

---

### REQ-L2-TE-002: Zyklenprävention in parent-child-Hierarchien

Die TraceabilityEngine SHALL bei `parent-child`-Links validieren, dass kein Zyklus erzeugt wird. Bei Zyklus-Erkennung SHALL die Operation abgebrochen werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] A→B, B→C, dann C→A → Fehler `"Cycle detected"`
- [ ] Nach abgelehntem Zyklus existieren A→B und B→C weiterhin
- [ ] A→B, A→C (kein Zyklus) → beide OK

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-001
**Rationale:** REQ-L1-001 fordert hierarchische Strukturen „unter der Bedingung, dass Zyklen ausgeschlossen werden".

---

### REQ-L2-TE-003: Atomare Batch-Operationen für TraceLinks

Die TraceabilityEngine SHALL Batch-Erstellung und Batch-Löschung in einer atomaren Transaktion unterstützen. Bei Teilfehler SHALL die gesamte Batch-Operation zurückgesetzt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Batch von 100 TraceLinks → alle 100 persistiert
- [ ] Batch mit einem ungültigen Link → alle zurückgesetzt
- [ ] Batch von 100 TraceLinks in < 500ms

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001, IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-003, REQ-L1-025 (mitwirkend)
**Rationale:** Decompose-Workflow erstellt mehrere parent-child-Links in einer Transaktion.

---

### REQ-L2-TE-004: Upstream/Downstream-Graph-Query

Die TraceabilityEngine SHALL Upstream- und Downstream-Queries für beliebige Artefakte unterstützen. Das Ergebnis SHALL alle direkt verbundenen Knoten mit Link-Typ-Annotation enthalten. Query SHALL in < 200ms (p95) bei bis zu 10.000 Items antworten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `query_upstream(requirement_id)` → vollständiger Nachbar-Graph in ≤ 200ms (p95)
- [ ] `query_downstream(requirement_id)` → ≤ 200ms (p95)
- [ ] Ergebnis enthält Entity-ID, Entity-Typ, Link-Typ, Richtung
- [ ] PostgreSQL-Indizes (GIST/GIN) aktiv

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-003, REQ-L1-026 (mitwirkend)
**Rationale:** REQ-L1-003 fordert Upstream/Downstream-Queries in < 200ms.

---

### REQ-L2-TE-005: Transitive Hüllen-Query (Impact-Analyse)

Die TraceabilityEngine SHALL transitive Hüllen berechnen — alle indirekt erreichbaren Knoten über mehrere Ebenen. Ergebnis SHALL Link-Typ, Richtung und Pfadtiefe enthalten. ≤ 200ms (p95) bei 10.000 Items.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Req-A `derives-from` Arch-B `implements` Comp-C → `query_downstream(Req-A, transitive=true)` → {Arch-B (depth=1), Comp-C (depth=2)}
- [ ] Transitive Query bei 10.000 Items → ≤ 200ms (p95)

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-003, REQ-L1-026 (mitwirkend)
**Rationale:** Impact-Analysen erfordern die vollständige Kette.

---

### REQ-L2-TE-006: Coverage-Berechnung (Requirement → Test-Abdeckung)

Die TraceabilityEngine SHALL die Test-Coverage berechnen: Prozentsatz der Requirements mit mindestens einem `verifies`-TraceLink zu einem TestCase. Ergebnis: Gesamtzahl, abgedeckte Anzahl, ungedeckte IDs, Prozent. ≤ 500ms bei 10.000 Requirements.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 10 Requirements, 7 mit verifies-Links → `{total: 10, covered: 7, uncovered: [...], percentage: 70.0}`
- [ ] Coverage für 10.000 Requirements → ≤ 500ms
- [ ] Leerer Workspace → `{total: 0, covered: 0, uncovered: [], percentage: 0.0}`

**Interfaces:**
- Incoming: IF-TE-EXT-IN-002
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-012, REQ-L1-003 (mitwirkend)
**Rationale:** REQ-L1-012 fordert Coverage-Tracking.

---

### REQ-L2-TE-007: Coverage-Filterung nach Artefakttyp und Link-Typ

Die TraceabilityEngine SOLLTE Coverage-Queries optional nach Artefakttyp und Link-Typ filterbar gestalten.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `coverage(workspace_id, artifact_type='ArchitectureElement', link_type='satisfies')` → gefilterter Report
- [ ] Performance: ≤ 500ms bei 10.000 Items

**Interfaces:**
- Incoming: IF-TE-EXT-IN-002
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-004 (mitwirkend), REQ-L1-012 (mitwirkend)
**Rationale:** Differenzierte Coverage-Reports für verschiedene Artefakttypen.

---

### REQ-L2-TE-008: Trace-Graph-Sammlung für Baseline-Snapshot

Die TraceabilityEngine SHALL auf Anfrage des BaselineService den vollständigen Trace-Graph eines Workspaces sammeln und serialisierbar zurückgeben. ≤ 500ms bei 10.000 Items.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Workspace mit 50 TraceLinks → Graph mit exakt 50 Links
- [ ] Graph JSON-serialisierbar
- [ ] Leerer Workspace → leerer Graph
- [ ] ≤ 500ms bei 10.000 Items

**Interfaces:**
- Incoming: IF-TE-EXT-IN-004
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-008 (mitwirkend)
**Rationale:** BaselineService benötigt den Trace-Zustand für Snapshots.

---

### REQ-L2-TE-009: Referentielle Integrität bei Artefakt-Löschung

Die TraceabilityEngine SHALL bei Löschung eines Artefakts automatisch alle zugehörigen TraceLinks löschen (CASCADE). Atomar innerhalb derselben Transaktion.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Lösche Requirement mit 3 TraceLinks → alle 3 gelöscht
- [ ] Kein Query zeigt orphaned TraceLinks
- [ ] CASCADE Teil der Artefakt-Löschungstransaktion

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-003, REQ-L1-025 (mitwirkend)
**Rationale:** Orphaned TraceLinks würden Reports und Queries verfälschen.

---

### REQ-L2-TE-010: TraceLink-Audit-Metadaten

Jeder TraceLink SHALL Audit-Felder (`created_by`, `created_at`, `modified_by`, `modified_at`) besitzen. Für MCP-Operationen SHALL Agent-Client-Identität und API-Key (gehashed) erfasst werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLink via REST → `created_by` = User-ID
- [ ] TraceLink via MCP → `created_by` = Agent-Client-ID
- [ ] Änderung → `modified_by`/`modified_at` aktualisiert, `created_by`/`created_at` unverändert

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-011 (mitwirkend), REQ-L1-003 (mitwirkend)
**Rationale:** Vollständige Protokollierung aller Änderungen.

---

### REQ-L2-TE-011: Tenant-Isolation für alle TraceLink-Operationen

Die TraceabilityEngine SHALL für alle Operationen sicherstellen, dass ausschließlich TraceLinks des aktiven Tenants sichtbar und manipulierbar sind. Tenant-Filterung über PersistenceLayer-Custom-Manager.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant-1 erstellt TraceLink → Tenant-2 query → nicht sichtbar
- [ ] Tenant-2 versucht Delete → Fehler `"TraceLink not found"`
- [ ] Coverage-Report enthält nur Tenant-eigene TraceLinks

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001, IF-TE-EXT-IN-002, IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-015, REQ-L1-003 (mitwirkend)
**Rationale:** Row-Level-Isolation über `tenant_id`-FK auf allen Entitäten.

---

### REQ-L2-TE-012: TraceLink-Query-Performance-SLA

Die TraceabilityEngine SHALL Performance-SLAs einhalten: ≤ 200ms (p95) für Graph-Queries, ≤ 500ms (p95) für Coverage-Reports und Graph-Sammlungen — bei bis zu 10.000 Items und 50.000 TraceLinks.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Upstream/Downstream-Query: ≤ 200ms (p95)
- [ ] Transitive Query: ≤ 200ms (p95)
- [ ] Coverage-Report: ≤ 500ms (p95)
- [ ] Graph-Sammlung: ≤ 500ms (p95)
- [ ] PostgreSQL-Indizes (GIST/GIN) vorhanden und verifiziert

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001, IF-TE-EXT-IN-002, IF-TE-EXT-IN-004
- Outgoing: IF-TE-EXT-OUT-001, IF-TE-EXT-OUT-001

**Traceability:** REQ-L1-026, REQ-L1-003 (mitwirkend)
**Rationale:** Bündelt alle Performance-Aspekte der TraceabilityEngine.

---

## Traceability-Matrix: REQ-L2-TE → REQ-L1

| REQ-L2-TE | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-TE-001 | REQ-L1-003 | REQ-L1-015 |
| REQ-L2-TE-002 | REQ-L1-001 | — |
| REQ-L2-TE-003 | REQ-L1-003 | REQ-L1-025 |
| REQ-L2-TE-004 | REQ-L1-003 | REQ-L1-026 |
| REQ-L2-TE-005 | REQ-L1-003 | REQ-L1-026 |
| REQ-L2-TE-006 | REQ-L1-012 | REQ-L1-003 |
| REQ-L2-TE-007 | REQ-L1-004 | REQ-L1-012 |
| REQ-L2-TE-008 | REQ-L1-008 | — |
| REQ-L2-TE-009 | REQ-L1-003 | REQ-L1-025 |
| REQ-L2-TE-010 | REQ-L1-011 | REQ-L1-003 |
| REQ-L2-TE-011 | REQ-L1-015 | REQ-L1-003 |
| REQ-L2-TE-012 | REQ-L1-026 | REQ-L1-003 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-TE | 12 |
| Mandatory | 11 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 9 |
| Abgedeckte REQ-L1 (mitwirkend) | 3 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Trace → REQ-L2-TE, Template-Standardisierung*
*Designation: component (terminal) — decomposition_status: terminal*
