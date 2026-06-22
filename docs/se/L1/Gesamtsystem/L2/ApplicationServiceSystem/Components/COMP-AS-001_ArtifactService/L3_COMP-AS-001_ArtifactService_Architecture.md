---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 ArtifactService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-001_ArtifactService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der ArtifactService ist die zentrale Service-Komponente für alle Artefakt-Verwaltungsoperationen (CRUD). Er ist verantwortlich für:
- Artifact-Hierarchie-Verwaltung mit Parent-Child-Beziehungen
- Zyklus-Erkennung bei Parent-Zuweisung (DAG-Validierung)
- Rekursive Tree-Queries mit PostgreSQL Recursive CTEs
- Kaskadierte TraceLink-Löschung bei Artifact-Delete

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module, nicht weitere SE-Subsysteme.

### 2.1 Klassen und Module

- **`ArtifactService` (Hauptklasse):** Orchestriert alle Artefakt-Operationen (`create`, `update`, `delete`, `get`, `get_tree`).
- **`ArtifactValidator` (Module):** Implementiert Zyklus-Erkennungslogik via DFS-Traversierung.
- **`TreeQueryBuilder` (Module):** Konstruiert PostgreSQL Recursive CTEs für hierarchische Queries.
- **`ArtifactDTO` / `TreeNodeDTO`:** Datenstrukturen für API-Übergaben.

### 2.2 Datenstrukturen

- **Artifact-Entity:**
  - `id`: UUID (Primary Key)
  - `workspace_id`: UUID (Foreign Key, Tenant-Isolation)
  - `parent_id`: UUID (Foreign Key, nullable)
  - `name`: String
  - `type`: String (z.B. "requirement", "component")
  - `created_at`: DateTime
  - `updated_at`: DateTime

- **TreeNodeDTO (API-Response):**
  ```json
  {
    "id": "uuid",
    "name": "string",
    "type": "string",
    "children": [/* recursive children */]
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AS001-001 (Zyklus-Erkennung) | `validate_no_cycle(parent_id, child_id)`: DFS-Traversierung vom neuen Parent bis zu Root, Fehler falls child_id in Pfad enthalten. Prüfung vor jedem INSERT/UPDATE. |
| REQ-L3-AS001-002 (Rekursive Tree-Query) | `get_tree(root_id, workspace_id)`: Generiert Recursive CTE `WITH RECURSIVE tree AS (...)`, rekonstruiert Baumstruktur in Python mit TreeNodeDTO-Nesting. |
| REQ-L3-AS001-003 (Cascade-TraceLink-Löschung) | `delete_artifact(id, ctx)`: Ruft vor DELETE `TraceLinkService.cascade_delete_trace_links(id)` auf. Beide Operationen im selben Transaktionskontext. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **REST API / ApplicationService:** CRUD-Methoden-Aufrufe (`POST /artifacts`, `GET /artifacts/{id}`, etc.)
  - **Python Function Call:** Direkte Methodenaufrufe von anderen Services

- **Ausgänge (Outbound):**
  - **IF-AS-INT-001:** Aufruf an `COMP-AS-005` (TraceLinkService) — `cascade_delete_trace_links(artifact_id)`
  - **IF-AS-EXT-OUT-007:** Django ORM Queries auf Artifact-Entity mit Tenant-Isolation via Custom Manager
  - **Domain Events (optional):** Publikation von `ArtifactCreated`, `ArtifactDeleted` Events via DomainEventBus (falls implementiert)

---

## 5. Architectural Rationale

**ADR-L3-AS001-01 — Zyklus-Validierung via DFS-Traversierung vor Persistierung**

*Entscheidung:* Zyklus-Erkennung erfolgt in-memory mittels DFS (Depth-First Search) vor jeder Parent-Zuweisung, nicht durch nachgelagerte Constraints.

*Rationale:*
- **Annahme:** Artefakt-Hierarchien sind tyischerweise flach (< 10 Ebenen), DAGs mit < 1000 Artefakten pro Workspace.
- **Gewählter Ansatz:** In-Memory-DFS ist O(V+E) und reagiert sofort mit aussagekräftigem Fehler.
- **Ablehnte Alternative:** Datenbank-Constraints (CHECK-Trigger, rekursive CTEs) sind komplexer zu warten und geben weniger aussagekräftige Fehlermeldungen.
- **Erfüllt REQ-L3-AS001-001:** Zyklus wird vor Persistierung erkannt, Fehler enthält Pfad.

---

**ADR-L3-AS001-02 — Recursive CTE für hierarchische Queries**

*Entscheidung:* Tree-Queries werden auf Datenbankseite via PostgreSQL Recursive CTEs ausgeführt, nicht durch mehrfache Roundtrips (N+1).

*Rationale:*
- **Annahme:** REQ-L3-AS001-002 fordert < 200ms für 500 Artefakte über 5 Ebenen.
- **Gewählter Ansatz:** Single SQL-Query mit RECURSIVE CTE + Nesting in Python.
- **Abgelehnte Alternative:** Lazy-Loading mit Rekursion (Node → children[]) → N+1 Problem, >500ms.
- **Erfüllt REQ-L3-AS001-002:** Single Datenbankabfrage, deterministische Performance.

---

**ADR-L3-AS001-03 — Transaktionale Cascade-Löschung via Service-Call**

*Entscheidung:* Bei `delete_artifact(id)` wird `TraceLinkService.cascade_delete_trace_links(id)` im selben Transaktionskontext aufgerufen, bevor das Artifact selbst gelöscht wird.

*Rationale:*
- **Annahme:** Fremdschlüssel-Constraints (CASCADE DELETE) sind nicht konfigurierbar genug für komplexe Szenarien.
- **Gewählter Ansatz:** Expliziter Service-Call mit atomarem Rollback bei Fehler.
- **Abgelehnte Alternative:** Database CASCADE DELETE auf Foreign-Key-Ebene — versteckt Logik in Schema, schwer zu audieren.
- **Erfüllt REQ-L3-AS001-003:** Cascade-Operation ist explizit, transparent und atomar.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
