---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 BaselineStore Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-BL-003_BaselineStore
> **Parent:** L2_BaselineServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der BaselineStore ist die ausschließliche Persistierungskomponente für Baseline-Snapshots und ihre Delta-Indices. Er speichert Baseline-Metadaten (name, scope, workspace_id, created_by, created_at, description) und alle `(item_id, version)`-Tupel in einer Append-Only-Struktur. Er enforces Immutability durch Datenbankconstraints (keine UPDATE/DELETE), bietet atomare Transaktionen für Erstellung mit vollständigem Rollback bei Fehlern und unterstützt Abruf und Listing mit Tenant-Isolation.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`BaselineStoreService` (Klasse):** Orchestriert Persistierungs-, Abruf- und Listing-Operationen.
- **`BaselineSnapshot` (Entity-Klasse):** Django ORM Model — repräsentiert eine Baseline (immutable record).
- **`BaselineDeltaIndexEntry` (Entity-Klasse):** Django ORM Model — repräsentiert ein einzelnes `(item_id, version)`-Tupel.
- **`ImmutabilityConstraint` (DB-Constraint):** Trigger/Check-Constraint auf Datenbankebene, der UPDATE/DELETE blockiert.

### 2.2 Datenstrukturen

- **BaselineSnapshot (DB-Tabelle):**
  - `id`: UUID (Primary Key)
  - `name`: str (Unique per workspace)
  - `scope`: str (enum: "document", "project", "global")
  - `workspace_id`: UUID (Foreign Key)
  - `created_by`: str (Agent ID)
  - `created_at`: datetime (UTC)
  - `description`: str | None
  - **DB-Constraint:** UNIQUE(workspace_id, name); CHECK no UPDATE/DELETE

- **BaselineDeltaIndexEntry (DB-Tabelle):**
  - `id`: UUID (Primary Key)
  - `baseline_id`: UUID (Foreign Key → BaselineSnapshot)
  - `item_id`: str
  - `version`: int
  - **DB-Constraint:** UNIQUE(baseline_id, item_id); Foreign Key constraint; no UPDATE/DELETE

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-BL003-001 (Immutability) | DB-Constraints: BEFORE UPDATE/DELETE Trigger lehnt Änderungen ab. Application-Layer-Validierung zusätzlich. Fehler bei Duplikat-baseline_id durch UNIQUE-Constraint. |
| REQ-L3-BL003-002 (Atomare Persistierung) | Django-Transaktion (transaction.atomic()): BaselineSnapshot INSERT + alle DeltaIndexEntry INSERTs in einer Transaktion. Bei Fehler: vollständiges Rollback, kein Datensatz in DB. |
| REQ-L3-BL003-003 (Retrieval & Listing) | Methode `get(baseline_id)`: lädt Snapshot + alle Deltas. Methode `list(workspace_id, scope=None)`: filtert nach workspace_id + optional scope, sortiert nach created_at DESC, gibt Metadaten ohne Deltas zurück. Tenant-Isolation durch workspace_id-Filter. |
| REQ-L3-BL003-004 (Versions-Lookup) | Methode `lookup_item_version(baseline_id, item_id)`: Query auf DeltaIndexEntry mit baseline_id + item_id. Fehlend: Fehler. Effizient durch Indexing. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-BL-INT-001:** Aufruf vom DeltaIndexBuilder: `persist_delta_index(delta_index, metadata) -> baseline_id`.
  - **IF-BL-INT-004:** Aufruf vom VersionReconstructor: `lookup_item_version(baseline_id, item_id) -> version`.
  - **IF-BL-EXT-IN-001:** Aufruf vom ApplicationService: `get(baseline_id)`, `list(workspace_id, scope=None)`.

- **Ausgänge (Outbound):**
  - **IF-BL-INT-002:** Antwort an DiffEngine: `load_delta_index(baseline_id) -> list[tuple[item_id, version]]`.
  - **IF-BL-EXT-OUT-001:** Django ORM-Calls an Datenbank (INSERT, SELECT).

---

## 5. Architectural Rationale

**ADR-L3-BL003-01 — DB-Level-Immutability-Constraint**
*Entscheidung:* Immutability wird durch Datenbankconstraints (BEFORE UPDATE/DELETE Trigger oder CHECK-Constraint) enforced, nicht nur in der Application-Layer.
*Rationale:* Verhindert unbeabsichtigte oder böswillige Modifikationen, selbst wenn Application-Code bypassed wird. Erfüllt REQ-L3-BL003-001 vollständig.
*Alternative abgelehnt:* Nur Application-Layer-Validierung — kann durch direkte DB-Queries umgangen werden.

**ADR-L3-BL003-02 — Atomare Transaktion für Snapshot + Deltas**
*Entscheidung:* persist_delta_index führt BaselineSnapshot INSERT + alle DeltaIndexEntry INSERTs in einer Transaktion aus.
*Rationale:* Garantiert Konsistenz: entweder der gesamte Snapshot mit allen Deltas wird persistiert oder nichts. Erfüllt REQ-L3-BL003-002.
*Alternative abgelehnt:* Separate Transaktionen für Snapshot und Deltas — könnte zu Inkonsistenz führen bei Fehlern zwischen den INSERTs.

**ADR-L3-BL003-03 — Lazy Delta-Loading im Listing**
*Entscheidung:* `list()` gibt nur Snapshot-Metadaten ohne Delta-Indices zurück. `get()` gibt den vollständigen Snapshot mit Deltas.
*Rationale:* Optimiert Listing-Latenz und Speicherverbrauch. Deltas nur laden, wenn explizit benötigt.
*Alternative abgelehnt:* Immer Deltas im Listing mitgeben — würde bei 1000 Baselines zu Speicher-Overhead führen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
