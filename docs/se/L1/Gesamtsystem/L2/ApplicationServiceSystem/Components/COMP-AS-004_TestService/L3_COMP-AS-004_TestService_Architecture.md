---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 TestService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-004_TestService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der TestService ist die Service-Komponente für TestCase-CRUD und Test-Execution-Management. Er ist verantwortlich für:
- Vollständiges CRUD für TestCases mit Typ- und Status-Verwaltung
- Execution-Status-Aktualisierung (Passed, Failed, Not Run)
- Coverage-Berechnung basierend auf TraceLink-Abfragen
- Kaskadierte TraceLink-Löschung

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`TestService` (Hauptklasse):** Orchestriert CRUD (`create`, `update`, `delete`, `get`, `list`), `update_test_status()`, `get_coverage()`.
- **`TestTypeValidator` (Module):** Validiert `test_type` gegen erlaubte Werte (Unit, Integration, System, Acceptance).
- **`ExecutionStatusValidator` (Module):** Validiert `execution_status` gegen erlaubte Werte (Passed, Failed, Not Run).
- **`CoverageCalculator` (Module):** Delegiert TraceLink-Query an TraceabilityEngine, berechnet Coverage-Metriken.
- **`TestCaseDTO`:** API-Datenstruktur.

### 2.2 Datenstrukturen

- **TestCase-Entity:**
  - `id`: UUID (Primary Key)
  - `workspace_id`: UUID (Tenant)
  - `name`: String
  - `description`: Text
  - `test_type`: String (Unit|Integration|System|Acceptance)
  - `execution_status`: String (Passed|Failed|Not Run)
  - `created_at`: DateTime
  - `updated_at`: DateTime

- **CoverageResult:**
  ```json
  {
    "total": 10,
    "covered": 7,
    "percentage": 70.0
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AS004-001 (CRUD mit Typ- und Status-Verwaltung) | `create()`: Validiere test_type, setze execution_status=Not Run, initialisiere WorkflowState. `delete()`: cascade_delete_trace_links(). |
| REQ-L3-AS004-002 (Execution-Status-Aktualisierung) | `update_test_status(id, execution_status, ctx)`: Validiere Status-Wert, persistiere, publiziere TestCaseUpdated-Event. |
| REQ-L3-AS004-003 (Coverage-Berechnung) | `get_coverage(workspace_id, ctx)`: Delegiere `TraceabilityEngine.coverage(workspace_id)`, berechne {total, covered, percentage}. Keine direkten TraceLink-Queries. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **REST API / ApplicationService:** CRUD, Status-Update, Coverage-Anfragen
  - **Python Function Call:** Direkte Methodenaufrufe

- **Ausgänge (Outbound):**
  - **IF-AS-INT-005:** `COMP-AS-005` (TraceLinkService) — `cascade_delete_trace_links(test_case_id)`
  - **IF-AS-INT-011:** `COMP-AS-013` (DomainEventBus) — Publikation `TestCaseCreated / Updated / Deleted` (Outbox)
  - **IF-AS-EXT-OUT-003:** `TraceabilityEngine` — `coverage(workspace_id)` für Coverage-Berechnung
  - **IF-AS-EXT-OUT-007:** Django ORM — TestCase-Entity mit Tenant-Isolation

---

## 5. Architectural Rationale

**ADR-L3-AS004-01 — Coverage-Berechnung via TraceabilityEngine-Delegation**

*Entscheidung:* Coverage wird nicht durch direkte TestCase↔Requirement-Queries im TestService berechnet, sondern via `TraceabilityEngine.coverage()` delegiert.

*Rationale:*
- **Annahme:** TraceabilityEngine ist die Quelle der Wahrheit für TraceLink-Abfragen und kann optimiert werden (Indizes, Caching).
- **Gewählter Ansatz:**: Separation of Concerns — TestService kümmert sich um TestCase-Daten, TraceabilityEngine um Relationen.
- **Abgelehnte Alternative:** Direkte Recursive CTE im TestService — Coupling mit DB-Schema, schwer zu testen.
- **Erfüllt REQ-L3-AS004-003:** Coverage ist delegiert, TestService ist fokussiert.

---

**ADR-L3-AS004-02 — Explizite Enum-Validierung für test_type und execution_status**

*Entscheidung:* `test_type` und `execution_status` werden gegen Whitelisten validiert, nicht als offene Strings akzeptiert.

*Rationale:*
- **Annahme:** Typen und Status sind finite Sets.
- **Gewählter Ansatz:** Service-seitige Enum-Validierung vor Persistierung.
- **Abgelehnte Alternative:** Offene String-Felder → Data-Pollution, keine Constraints.
- **Erfüllt REQ-L3-AS004-001 und REQ-L3-AS004-002:** Datenqualität und vorhersagbares Verhalten.

---

**ADR-L3-AS004-03 — TestCaseUpdated-Event nach Status-Change**

*Entscheidung:* Nach jedem `update_test_status()` wird ein `TestCaseUpdated`-Domain-Event im Outbox publiziert, um Subscribers (z.B. Coverage-Recalculation) zu notifizieren.

*Rationale:*
- **Annahme:** Status-Änderungen können Geschäftslogik auslösen (z.B. Workflow-Transition, Benachrichtigungen).
- **Gewählter Ansatz:** Event-basierte Entkopplung via DomainEventBus.
- **Abgelehnte Alternative:** Direkte Callbacks im Service → Tight Coupling.
- **Erfüllt REQ-L3-AS004-002:** Entkopplung und Erweiterbarkeit.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
