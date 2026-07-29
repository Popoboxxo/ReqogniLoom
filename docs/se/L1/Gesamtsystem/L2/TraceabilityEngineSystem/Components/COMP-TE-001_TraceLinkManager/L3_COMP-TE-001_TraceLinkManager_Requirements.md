---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:50:00Z"
schema_version: "1.0.0"
---

# L3 TraceLinkManager Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-TE-001_TraceLinkManager
> **Parent:** L2_TraceabilityEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der TraceLinkManager ist die zentrale CRUD-Komponente für TraceLinks. Er verwaltet die 6 Link-Typen (parent-child, derives-from, satisfies, verifies, implements, refines), führt Link-Typ-Validierung durch, prüft auf Zyklen mittels Tarjan-Algorithmus (eager für Single-Links, end-of-transaction für Batches), enforced Tenant-Isolation, implementiert CASCADE-Löschung bei Artefakt-Deletion und erfasst Audit-Metadaten.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`TraceLinkManager` (Klasse):** Hauptklasse mit Methoden `create`, `read`, `update`, `delete` für TraceLinks.
- **`LinkTypeValidator` (Klasse):** Validiert Link-Typ gegen die 6 zulässigen Typen.
- **`CycleDetector` (Klasse):** Implementiert Tarjan-SCC-Algorithmus für Zyklenprüfung. O(V+E)-Komplexität.
- **`TenantFilter` (Klasse):** Appliziert tenant_id-Filter auf alle Queries. Enforced immutable tenant_id.
- **`AuditMetadataCapture` (Klasse):** Erfasst created_by, created_at, modified_by, modified_at. Bei MCP: agent-client-ID und gehashter API-Key.

### 2.2 Datenstrukturen

- **`TraceLink` (Pydantic Model):** {id (UUID), source_id, target_id, link_type, created_by, created_at, modified_by, modified_at, tenant_id}.
- **`CycleDetectionError` (Exception):** {cycle_path: str (z.B. "Req-A → Req-B → Req-C → Req-A"), error_code: "CYCLE_DETECTED"}.
- **`BatchOperationRequest` (Pydantic Model):** {create: List[TraceLink], delete: List[link_id]} für atomare Batch.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-TE001-001 (TraceLink CRUD) | Vier Methoden: create, read, update, delete. LinkTypeValidator prüft Link-Typ gegen 6 zulässige. TenantFilter enforced Cross-Tenant-Isolation. |
| REQ-L3-TE001-002 (Eager-Zyklenprüfung) | Vor Single-Link-Persistenz: CycleDetector.detect_cycles(graph). Detektiert Zyklus → CycleDetectionError, kein DB-Write. |
| REQ-L3-TE001-003 (Atomare Batch & Tarjan) | BatchOperationRequest mit create/delete-Listen. Transaktion: alle Links persistiert, dann Tarjan-Prüfung (einmalig, O(V+E)). Fehler → rollback. |
| REQ-L3-TE001-004 (CASCADE & Audit) | Bei Artefakt-Deletion: Constraint CASCADE löscht alle zugehörigen Links in gleicher Transaktion. AuditMetadataCapture speichert actor_identity und Zeitstempel. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-TE-EXT-IN-003:** Von ApplicationService: TraceLink CRUD-Operationen.

**Ausgänge (Outbound):**
- **IF-TE-INT-001:** Zu COMP-TE-002 (QueryEngine): `get_trace_links(workspace_id, filters) -> TraceLink[]`.
- **IF-TE-INT-002:** Zu COMP-TE-003 (CoverageCalculator): `get_trace_links(workspace_id, link_type) -> TraceLink[]`.
- **IF-TE-INT-003:** Von COMP-TE-002 (QueryEngine): `validate_graph_integrity() -> ValidationResult`.
- **IF-TE-EXT-OUT-001:** Zu PersistenceLayer (Django ORM): TraceLink-Entity schreiben/lesen.

---

## 5. Architectural Rationale

**ADR-L3-TE1-01 — Eager-Zyklenprüfung vor Single-Link, Tarjan am Batch-Ende**

*Entscheidung:* Single-Links: CycleDetector.detect_cycles() VOR Persistenz. Batch: Tarjan nach allen Schreiboperationen, atomare Transaktion.

*Rationale:* Erfüllt REQ-L3-TE001-002 und REQ-L3-TE001-003. Single-Link-Prüfung ist strict und sofort. Batch-Prüfung ist effizient (eine Tarjan-Durchlauf statt N). Alternative: Eager für beide → würde Batch-Performance leiden.

---

**ADR-L3-TE1-02 — Tarjan mit O(V+E)-Komplexität**

*Entscheidung:* Zyklenprüfung nutzt Tarjan-SCC statt Naive-DFS. Komplexität O(V+E), nicht O(V³).

*Rationale:* Erfüllt REQ-L3-TE001-003 ("Batch of 100 links completes in < 500ms"). Tarjan ist optimal für Zyklenprüfung. Alternative: Naive-DFS → würde bei größeren Graphen TLE-Fehler bekommen.

---

**ADR-L3-TE1-03 — Tenant-Filter auf alle Queries**

*Entscheidung:* TenantFilter wendet tenant_id-Constraint auf jede Query an. Ist in ORM-Layer integriert (Django QuerySet).

*Rationale:* Erfüllt REQ-L3-TE001-001 ("Cross-Tenant-Zugriffe SHALL abgewiesen werden"). Strukturell erzwungen, nicht per Honor-System. Alternative: Manuell pro Query → würde Fehler-anfällig sein.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-TE001-U000: Auto-derived from REQ-L2-TRA-004
Abgeleitet von: REQ-L2-TRA-004

### REQ-L3-TE001-U001: Auto-derived from REQ-L2-TRA-006
Abgeleitet von: REQ-L2-TRA-006

### REQ-L3-TE001-U002: Auto-derived from REQ-L2-TRA-009
Abgeleitet von: REQ-L2-TRA-009

### REQ-L3-TE001-U003: Auto-derived from REQ-L2-TRA-011
Abgeleitet von: REQ-L2-TRA-011

### REQ-L3-TE001-U004: Auto-derived from REQ-L2-TRA-003
Abgeleitet von: REQ-L2-TRA-003

### REQ-L3-TE001-U005: Auto-derived from REQ-L2-TRA-007
Abgeleitet von: REQ-L2-TRA-007

### REQ-L3-TE001-U006: Auto-derived from REQ-L2-TRA-008
Abgeleitet von: REQ-L2-TRA-008

### REQ-L3-TE001-U007: Auto-derived from REQ-L2-TRA-014
Abgeleitet von: REQ-L2-TRA-014

### REQ-L3-TE001-U008: Auto-derived from REQ-L2-TRA-005
Abgeleitet von: REQ-L2-TRA-005

### REQ-L3-TE001-U009: Auto-derived from REQ-L2-TRA-012
Abgeleitet von: REQ-L2-TRA-012

### REQ-L3-TE001-U010: Auto-derived from REQ-L2-TRA-002
Abgeleitet von: REQ-L2-TRA-002

### REQ-L3-TE001-U011: Auto-derived from REQ-L2-TRA-013
Abgeleitet von: REQ-L2-TRA-013

### REQ-L3-TE001-U012: Auto-derived from REQ-L2-TRA-010
Abgeleitet von: REQ-L2-TRA-010

### REQ-L3-TE001-U013: Auto-derived from REQ-L2-TRA-001
Abgeleitet von: REQ-L2-TRA-001
