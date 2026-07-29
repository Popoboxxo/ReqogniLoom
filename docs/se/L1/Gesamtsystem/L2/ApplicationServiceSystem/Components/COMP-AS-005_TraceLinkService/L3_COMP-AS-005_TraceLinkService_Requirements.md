---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 TraceLinkService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-005_TraceLinkService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der TraceLinkService ist die zentrale Service-Komponente für TraceLink-Verwaltung. Er ist verantwortlich für:
- TraceLink CRUD mit Source/Target-Existenz- und Typ-Validierung
- Kaskadierte TraceLink-Löschung bei Entity-Deletion
- TraceLink-Queries mit Richtungsfilter und Typ-Filter
- Workspace-übergreifende Validierung (Cross-Workspace-Prevention)

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`TraceLinkService` (Hauptklasse):** Orchestriert CRUD (`create_trace_link`, `query_trace_links`, `cascade_delete_trace_links`).
- **`TraceLinkValidator` (Module):** Validiert Source/Target-Existenz, Workspace-Konsistenz, Link-Type.
- **`QueryBuilder` (Module):** Konstruiert ORM-Queries mit Richtungs- und Typ-Filtern.
- **`TraceLink-Types-Enum:** Definiert erlaubte Link-Typen: `parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`.
- **`TraceLinkDTO`:** API-Datenstruktur.

### 2.2 Datenstrukturen

- **TraceLink-Entity:**
  - `id`: UUID (Primary Key)
  - `source_id`: UUID (Foreign Key, polymorphic — auf Artifact, Requirement, ArchitectureElement, TestCase)
  - `target_id`: UUID (Foreign Key, polymorphic)
  - `source_type`: String (entity type hint, z.B. "Requirement")
  - `target_type`: String
  - `link_type`: String (parent-child|derives-from|satisfies|verifies|implements|refines)
  - `workspace_id`: UUID (Tenant)
  - `created_at`: DateTime

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AS005-001 (Erstellung mit Validierung) | `create_trace_link(source_id, target_id, link_type, ctx)`: TraceLinkValidator prüft Existenz, Workspace-Zugehörigkeit, Link-Type-Gültigkeit. Bei Erfolg: INSERT. |
| REQ-L3-AS005-002 (Cascade-Delete) | `cascade_delete_trace_links(entity_id, ctx)`: DELETE alle TraceLinks mit entity_id als Source ODER Target. Im Caller-TX, idempotent. |
| REQ-L3-AS005-003 (Query mit Filter) | `query_trace_links(entity_id, direction, link_type=None, ctx)`: QueryBuilder konstruiert ORM mit `direction` (incoming|outgoing|both). Optional nach link_type filtern. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-INT-001:** `COMP-AS-001` (ArtifactService) — eingehend, `cascade_delete_trace_links(artifact_id)`
  - **IF-AS-INT-002:** `COMP-AS-002` (RequirementService) — eingehend, `create_trace_link(source_id, target_id, link_type)`
  - **IF-AS-INT-004:** `COMP-AS-003` (ArchitectureService) — eingehend, `cascade_delete_trace_links(architecture_element_id)`
  - **IF-AS-INT-005:** `COMP-AS-004` (TestService) — eingehend, `cascade_delete_trace_links(test_case_id)`

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-003:** `TraceabilityEngine` — `query(artifact_id, direction)` für TraceLink-Abfragen
  - **IF-AS-EXT-OUT-007:** Django ORM — TraceLink-Entity mit Tenant-Isolation

---

## 5. Architectural Rationale

**ADR-L3-AS005-01 — Strikte Cross-Workspace-Prevention bei TraceLink-Erstellung**

*Entscheidung:* Vor jedem `create_trace_link()` wird validiert, dass Source und Target zum selben Workspace gehören. Cross-Workspace-Links werden abgewiesen.

*Rationale:*
- **Annahme:** Workspaces sind Tenants mit Datenschranken; Cross-Workspace-Links würden Datenisolation brechen.
- **Gewählter Ansatz:** Explizite Workspace-Konsistenz-Validierung vor INSERT.
- **Abgelehnte Alternative:** DB-Constraint (Trigger) → nicht aussagekräftig, schwer zu debuggen.
- **Erfüllt REQ-L3-AS005-001:** Cross-Workspace-Risiko ist eliminiert.

---

**ADR-L3-AS005-02 — Cascade-Delete im Caller-Transaktionskontext**

*Entscheidung:* `cascade_delete_trace_links(entity_id)` wirkt sich auf den TX des Callers aus; bei Caller-Rollback wird die Cascade auch zurückgerollt.

*Rationale:*
- **Annahme:** REQ-L3-AS005-002 fordert Atomarität mit der auslösenden Operation (z.B. Artifact-Delete).
- **Gewählter Ansatz::** Service-Methode ohne eigenen TX-Scope, nutzt Caller-TX.
- **Abgelehnte Alternative:** `transaction.atomic()` innerhalb cascade_delete → Nested TX mit savepoints, komplexer.
- **Erfüllt REQ-L3-AS005-002:** Atomare Cascade-Löschung.

---

**ADR-L3-AS005-03 — Polymorphe Entitäten via source_type / target_type**

*Entscheidung:* TraceLink enthält `source_type` / `target_type` Felder (Strings), um zu dokumentieren, welcher Entity-Typ an der TraceLink beteiligt ist. Validierung erfolgt via TraceLinkValidator.

*Rationale:*
- **Annahme:** TraceLinks können zwischen verschiedenen Entity-Typen (Requirement, Artifact, ArchitectureElement, TestCase) existieren.
- **Gewählter Ansatz:** Einfache Polymorphie via Type-Hint-Felder, keine komplexen Foreign-Key-Constraints.
- **Abgelehnte Alternative:** Single-Table-Inheritance oder Separate Tables pro Type → komplexere Schema-Verwaltung.
- **Erfüllt REQ-L3-AS005-001 und REQ-L3-AS005-003:** Flexible Cross-Entity-Verlinkung, einfach abzufragen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
