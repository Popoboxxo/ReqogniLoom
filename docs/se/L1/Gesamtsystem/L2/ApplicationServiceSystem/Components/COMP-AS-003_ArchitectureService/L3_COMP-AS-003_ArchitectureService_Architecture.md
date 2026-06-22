---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 ArchitectureService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-003_ArchitectureService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der ArchitectureService ist die Service-Komponente für ArchitectureElement-CRUD und Versionsmanagement. Er ist verantwortlich für:
- ArchitectureElement CRUD mit Typ-Validierung
- Optimistic Locking bei konkurrenten Updates
- Automatische Versions-Inkrementierung
- Kaskadierte TraceLink-Löschung
- Domain-Event-Publikation für Änderungen

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ArchitectureService` (Hauptklasse):** Orchestriert CRUD (`create`, `update`, `delete`, `get`), Version-Management.
- **`ElementTypeValidator` (Module):** Validiert `element_type` gegen erlaubte Werte (Component, Interface, Subsystem, Layer, Module).
- **`OptimisticLockManager` (Module):** Verwaltet Version-Vergleiche und Inkrementierung.
- **`EventPublisher` (Module):** Delegiert Domain-Event-Publikation an DomainEventBus (Outbox-Pattern).
- **`ArchitectureElementDTO`:** API-Datenstruktur mit Version-Feld.

### 2.2 Datenstrukturen

- **ArchitectureElement-Entity:**
  - `id`: UUID (Primary Key)
  - `workspace_id`: UUID (Tenant)
  - `element_type`: String (Component|Interface|Subsystem|Layer|Module)
  - `name`: String
  - `description`: Text
  - `version`: Integer (für Optimistic Locking)
  - `created_at`: DateTime
  - `updated_at`: DateTime

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AS003-001 (CRUD mit Typ-Validierung) | `create(data, ctx)`: ElementTypeValidator prüft `element_type`, setzt version=1, initialisiert WorkflowState. `delete()`: cascade_delete_trace_links() aufrufen. |
| REQ-L3-AS003-002 (Optimistic Locking) | `update(id, data, expected_version, ctx)`: Version vergleichen, bei Mismatch OptimisticLockError werfen. Bei Success: Datensatz aktualisieren, version inkrementieren. |
| REQ-L3-AS003-003 (Domain-Event-Publikation) | Nach Create/Update/Delete: typisiertes Event (ArchitectureElementCreated/Updated/Deleted) im Transaktionskontext (Outbox) publizieren. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **REST API / ApplicationService:** CRUD-Aufrufe
  - **Python Function Call:** Direkte Methodenaufrufe

- **Ausgänge (Outbound):**
  - **IF-AS-INT-004:** `COMP-AS-005` (TraceLinkService) — `cascade_delete_trace_links(architecture_element_id)`
  - **IF-AS-INT-010:** `COMP-AS-013` (DomainEventBus) — Publikation `ArchitectureElementCreated / Updated / Deleted` (Outbox)
  - **IF-AS-EXT-OUT-007:** Django ORM — ArchitectureElement-Entity mit Tenant-Isolation

---

## 5. Architectural Rationale

**ADR-L3-AS003-01 — Optimistic Locking statt Pessimistic Locks**

*Entscheidung:* Konkurrente Updates werden mittels Optimistic Locking (Version-Feld) gehandhabt, nicht mit Datenbank-Locks (SELECT FOR UPDATE).

*Rationale:*
- **Annahme:** ArchitectureElements werden typischerweise von mehreren Nutzern bearbeitet, aber selten gleichzeitig.
- **Gewählter Ansatz:** Optimistic Locking erlaubt hohe Concurrency, nur echte Konflikte erzeugen Fehler.
- **Abgelehnte Alternative:** Pessimistic Locking (SELECT FOR UPDATE) → Deadlock-Risiko, schlechtere Skalierung.
- **Erfüllt REQ-L3-AS003-002:** Versionskollisionen werden erkannt und eindeutig gemacht.

---

**ADR-L3-AS003-02 — Event-Publikation im Outbox-Pattern für Durability**

*Entscheidung:* Domain-Events werden nicht direkt publisht, sondern in einer Outbox-Tabelle im selben TX wie die Mutation persistiert. Ein separater Outbox-Processor pollert und publisht async.

*Rationale:*
- **Annahme:** REQ-L3-AS003-003 fordert Atomarität: Event nur wenn Mutation erfolgt.
- **Gewählter Ansatz:** Outbox-Pattern garantiert At-Least-Once-Semantik ohne distributed TX.
- **Abgelehnte Alternative:** Direkte Publikation in Mutation-TX → Risiko von Lost Events bei DB-Fehler.
- **Erfüllt REQ-L3-AS003-003:** Atomare Mutation + zuverlässige Event-Publikation.

---

**ADR-L3-AS003-03 — Strenge Typ-Validierung vor Persistierung**

*Entscheidung:* `element_type` wird gegen eine whitelist (Component, Interface, Subsystem, Layer, Module) vor jedem INSERT validiert. Unbekannte Typen werden sofort abgewiesen.

*Rationale:*
- **Annahme:** Element-Typen sind finite und definiert.
- **Gewählter Ansatz:** Explizite Enum-Validierung in der Service-Schicht, nicht als DB-CHECK.
- **Abgelehnte Alternative:** DB-Enum für Typ → Rigide, erfordert Schema-Migration für neue Typen.
- **Erfüllt REQ-L3-AS003-001:** Datenqualität ist sichergestellt, Fehler sind früh sichtbar.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
