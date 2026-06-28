# L3 ArtifactService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AS-001 — ArtifactService
> **Parent-System:** ApplicationServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Artifact-Hierarchie-CRUD, Zyklus-Pruefung bei Parent-Child-Beziehungen, Tree-Queries via PostgreSQL Recursive CTE.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AS-001 | Artifact-Hierarchy Cycle Detection — Validierung vor Persistenz |
| REQ-L2-AS-002 | Artifact Tree Query mit beliebiger Tiefe via Recursive CTE, ≤ 200ms bei 500 Artefakten |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-INT-001 | ausgehend | COMP-AS-005 (TraceLinkService) | `cascade_delete_trace_links(artifact_id)` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — alle Artifact-Entitaeten, Custom Manager mit Tenant-Isolation |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AS001-001: Zyklus-Erkennung bei Parent-Child-Zuweisung


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der ArtifactService SHALL vor jeder Erstellung oder Aenderung einer Parent-Child-Beziehung eine Pfad-Traversierung durchfuehren und die Operation abbrechen, wenn das neue Kind bereits Vorfahre des neuen Elternknotens ist.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Setting parent of C to A, where chain is A→B→C, raises `CycleDetectedError("Cycle detected: A→B→C→A")`
- [ ] Setting an artifact's parent to itself raises `CycleDetectedError("Cycle detected: self-reference")`
- [ ] A valid parent assignment (no cycle) completes without error
- [ ] Cycle check executes before any DB write

---

### REQ-L3-AS001-002: Rekursive Tree-Query via PostgreSQL CTE


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der ArtifactService SHALL eine `get_tree(root_id, workspace_id)`-Methode bereitstellen, die mittels PostgreSQL Recursive CTE die vollstaendige Nachkommenschaft als verschachtelte Baumstruktur zurueckgibt und dabei Tenant-Isolation sicherstellt.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `get_tree(root_id=B)` returns only B and its descendants, not ancestors or siblings
- [ ] Tree of 500 artifacts across 5 levels returns complete nested structure in < 200ms
- [ ] Result contains correct parent-child nesting (children list on each node)
- [ ] Query includes `tenant_id` filter — cross-tenant artifacts are not returned

---

### REQ-L3-AS001-003: Cascade-Loesung von TraceLinks bei Artifact-Delete


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der ArtifactService SHALL bei Loeschung eines Artifacts vor dem eigentlichen Delete-Aufruf `cascade_delete_trace_links(artifact_id)` am TraceLinkService aufrufen, sodass keine verwaisten TraceLinks im System verbleiben.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Deleting artifact A triggers `TraceLinkService.cascade_delete_trace_links(A.id)` before artifact row is removed
- [ ] After deletion, no TraceLink with source_id or target_id equal to A.id exists
- [ ] If TraceLinkService raises an error, the artifact deletion is rolled back (atomic)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
