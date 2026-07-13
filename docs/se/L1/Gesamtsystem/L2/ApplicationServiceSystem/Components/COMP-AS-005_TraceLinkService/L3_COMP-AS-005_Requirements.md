# L3 TraceLinkService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AS-005 — TraceLinkService
> **Parent-System:** ApplicationServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

TraceLink-CRUD, Quell/Ziel-Validierung, Link-Typ-Validierung, AuditLog-Ausloesung.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AS-010 | TraceLink-Orchestration mit Validierung und AuditLog |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-INT-001 | eingehend | COMP-AS-001 (ArtifactService) | `cascade_delete_trace_links(artifact_id)` |
| IF-AS-INT-002 | eingehend | COMP-AS-002 (RequirementService) | `create_trace_link(source_id, target_id, link_type)` |
| IF-AS-INT-004 | eingehend | COMP-AS-003 (ArchitectureService) | `cascade_delete_trace_links(architecture_element_id)` |
| IF-AS-INT-005 | eingehend | COMP-AS-004 (TestService) | `cascade_delete_trace_links(test_case_id)` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-OUT-003 | ausgehend | TraceabilityEngine | `query(artifact_id, direction)` |
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — TraceLink-Entitaeten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AS005-001: TraceLink-Erstellung mit Existenz- und Typ-Validierung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkService SHALL vor Erstellung eines TraceLink pruefen, dass Source und Target existieren, zum selben Workspace gehoeren und der `link_type` gueltig ist. Unterstuetzte Typen: `parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `create_trace_link(source_id, target_id, "satisfies", ctx)` with both entities existing in same workspace creates link
- [ ] Source entity not found raises `NotFoundError("Source entity not found")`
- [ ] Target entity not found raises `NotFoundError("Target entity not found")`
- [ ] Invalid link_type raises `ValidationError("Invalid link type")`
- [ ] Source and target in different workspaces raises `ValidationError("Cross-workspace TraceLink not permitted")`

---

### REQ-L3-AS005-002: Cascade-Delete aller TraceLinks einer Entitaet


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkService SHALL eine `cascade_delete_trace_links(entity_id)`-Methode bereitstellen, die alle TraceLinks loescht, bei denen `entity_id` als Source oder Target vorkommt. Die Operation muss im Transaktionskontext des Aufrufers ausgefuehrt werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] After `cascade_delete_trace_links(entity_id)`, no TraceLink with source_id=entity_id exists
- [ ] After `cascade_delete_trace_links(entity_id)`, no TraceLink with target_id=entity_id exists
- [ ] Operation participates in the caller's transaction (rolls back if caller rolls back)
- [ ] No error if entity has zero TraceLinks (idempotent)

---

### REQ-L3-AS005-003: TraceLink-Query per Entitaet und Richtung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkService SHALL eine Query-Methode bereitstellen, die alle TraceLinks einer Entitaet nach Richtung (eingehend / ausgehend / beide) und optional nach Link-Typ gefiltert zurueckgibt. Die Query delegiert an die TraceabilityEngine.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `query_trace_links(artifact_id, direction="outgoing", ctx)` returns only links where artifact_id is source
- [ ] `query_trace_links(artifact_id, direction="incoming", ctx)` returns only links where artifact_id is target
- [ ] Optional `link_type` filter reduces results to matching type only
- [ ] Results are scoped to the requesting tenant

---

### REQ-L3-AS005-004: TraceLink Konsistenz & Coverage (S-05, S-08, S-13)

Der TraceLinkService MUSS die Suspect-Markierung bidirektional entlang der semantischen Link-Beziehung propagieren. Exception-Remapping MUSS über typisierte Exceptions erfolgen (kein String-Matching). Die Coverage-Berechnung MUSS N+1-Query-optimiert sein.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von S-05, S-08, S-13.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-AS-042, REQ-L2-AS-044

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
