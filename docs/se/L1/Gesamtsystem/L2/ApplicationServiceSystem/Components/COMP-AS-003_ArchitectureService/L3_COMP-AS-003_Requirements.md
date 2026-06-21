# L3 ArchitectureService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AS-003 — ArchitectureService
> **Parent-System:** ApplicationServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

ArchitectureElement-CRUD, automatische Versions-Inkrementierung (Optimistic Locking).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AS-004 | ArchitectureElement CRUD mit element_type, automatischem Version-Inkrement, Optimistic Locking und Cascade-Delete |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-INT-004 | ausgehend | COMP-AS-005 (TraceLinkService) | `cascade_delete_trace_links(architecture_element_id)` |
| IF-AS-INT-010 | ausgehend | COMP-AS-013 (DomainEventBus) | `ArchitectureElementCreated / Updated / Deleted` — post_commit via Outbox |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — ArchitectureElement-Entitaeten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AS003-001: ArchitectureElement CRUD mit Typ-Validierung

Der ArchitectureService SHALL vollstaendiges CRUD fuer ArchitectureElements bereitstellen. Unterstuetzte `element_type`-Werte: `Component`, `Interface`, `Subsystem`, `Layer`, `Module`. Bei Create: Version auf 1 setzen und initialen WorkflowState anlegen. Ungueltige element_type-Werte werden vor Persistierung abgelehnt.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `create_architecture_element(data, ctx)` with valid element_type creates element with version=1 and initial WorkflowState
- [ ] `create_architecture_element` with unknown element_type raises `ValidationError("Invalid element_type")`
- [ ] `get_architecture_element(id, ctx)` returns element with all fields including version
- [ ] `delete_architecture_element(id, ctx)` removes element and all associated TraceLinks atomically

---

### REQ-L3-AS003-002: Optimistic Locking bei Update

Der ArchitectureService SHALL bei jeder Update-Operation die uebergebene `expected_version` mit der gespeicherten Version vergleichen. Bei Uebereinstimmung: Datensatz aktualisieren und Version automatisch inkrementieren. Bei Abweichung: Operation abbrechen mit `OptimisticLockError`.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `update_architecture_element(id, data, expected_version=1, ctx)` with matching version succeeds and increments version to 2
- [ ] `update_architecture_element(id, data, expected_version=0, ctx)` with stored version=1 raises `OptimisticLockError`
- [ ] Two concurrent updates with same expected_version — second raises `OptimisticLockError`
- [ ] Successful update publishes `ArchitectureElementUpdated` domain event

---

### REQ-L3-AS003-003: Domain-Event-Publikation nach Mutation

Der ArchitectureService SHALL nach jeder erfolgreichen Create-, Update- oder Delete-Operation ein typisiertes Domain-Event im selben Transaktionskontext (Outbox) an den DomainEventBus publizieren. Bei Rollback der Mutation darf kein Event publiziert werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Successful `create` publishes exactly one `ArchitectureElementCreated` event in the same transaction
- [ ] Successful `update` publishes exactly one `ArchitectureElementUpdated` event
- [ ] Successful `delete` publishes exactly one `ArchitectureElementDeleted` event
- [ ] Rolled-back mutation results in zero events published (outbox entry rolled back)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
