# L3 TestService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AS-004 — TestService
> **Parent-System:** ApplicationServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

TestCase-CRUD, Test-Execution-Status-Management, Coverage-Berechnung.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AS-005 | TestCase CRUD mit test_type, WorkflowState, execution_status und Cascade-Delete |
| REQ-L2-AS-025 | Coverage-Berechnung via TraceabilityEngine (verifies-Links) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-INT-005 | ausgehend | COMP-AS-005 (TraceLinkService) | `cascade_delete_trace_links(test_case_id)` |
| IF-AS-INT-011 | ausgehend | COMP-AS-013 (DomainEventBus) | `TestCaseCreated / Updated / Deleted` — post_commit via Outbox |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-OUT-003 | ausgehend | TraceabilityEngine | `coverage(workspace_id)` |
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — TestCase-Entitaeten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AS004-001: TestCase CRUD mit Typ- und Status-Verwaltung

Der TestService SHALL vollstaendiges CRUD fuer TestCases bereitstellen. Unterstuetzte `test_type`-Werte: `Unit`, `Integration`, `System`, `Acceptance`. Initial-`execution_status`: `Not Run`. Bei Delete: TraceLinks kaskadiert loeschen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `create_test_case(data, ctx)` with valid test_type creates TestCase with execution_status="Not Run" and initial WorkflowState
- [ ] `create_test_case` with unknown test_type raises `ValidationError("Invalid test_type")`
- [ ] `delete_test_case(id, ctx)` removes TestCase and all associated TraceLinks atomically
- [ ] `list_test_cases(workspace_id, filters, ctx)` returns filtered list respecting tenant isolation

---

### REQ-L3-AS004-002: Execution-Status-Aktualisierung

Der TestService SHALL eine dedizierte Methode `update_test_status(id, execution_status, ctx)` bereitstellen, die den `execution_status` eines TestCase aktualisiert. Unterstuetzte Werte: `Passed`, `Failed`, `Not Run`. Ungueltige Werte werden abgelehnt.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `update_test_status(id, "Passed", ctx)` sets execution_status to "Passed"
- [ ] `update_test_status(id, "Failed", ctx)` sets execution_status to "Failed"
- [ ] `update_test_status(id, "InvalidStatus", ctx)` raises `ValidationError("Invalid execution_status")`
- [ ] Update publishes `TestCaseUpdated` domain event

---

### REQ-L3-AS004-003: Coverage-Berechnung

Der TestService SHALL eine `get_coverage(workspace_id, ctx)`-Methode bereitstellen, die die Abdeckung von Requirements durch TestCases berechnet. Delegation der TraceLink-Query an die TraceabilityEngine. Rueckgabe: `{total, covered, percentage}`.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] 10 requirements, 7 with at least one `verifies` TraceLink to a TestCase → `{total: 10, covered: 7, percentage: 70.0}`
- [ ] After deleting a TestCase, coverage is recalculated correctly on next call
- [ ] `get_coverage` delegates to `TraceabilityEngine.coverage(workspace_id)` — no direct DB query for TraceLinks
- [ ] Result is scoped to the requesting tenant

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
