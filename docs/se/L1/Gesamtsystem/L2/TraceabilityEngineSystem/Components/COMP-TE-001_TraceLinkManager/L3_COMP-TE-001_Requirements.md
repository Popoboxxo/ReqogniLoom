# L3 TraceLinkManager Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-TE-001 — TraceLinkManager
> **Parent-System:** TraceabilityEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

TraceLink-CRUD, Link-Typ-Validierung, Zyklenprüfung via Tarjan-Algorithmus für alle 6 Link-Typen (Bulk: am Ende der Transaktion; Single: eager vor Persistenz); Rollback mit Pfad-Fehlerbericht, atomare Batch-Operationen, referentielle Integrität (CASCADE), Audit-Metadaten.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-TE-001 | TraceLink-Verwaltung mit 6 Link-Typen |
| REQ-L2-TE-002 | Zyklenprävention für alle transitiven Link-Typen (Single-Link, Eager) |
| REQ-L2-TE-003 | Atomare Batch-Operationen mit Tarjan-Zyklenprüfung |
| REQ-L2-TE-009 | Referentielle Integrität bei Artefakt-Löschung (CASCADE) |
| REQ-L2-TE-010 | TraceLink-Audit-Metadaten |
| REQ-L2-TE-011 | Tenant-Isolation für alle TraceLink-Operationen |
| REQ-L2-TE-012 | TraceLink-Query-Performance-SLA (mitwirkend) |
| REQ-L2-TE-020 | ADR ↔ ArchitectureElement TraceLink |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-INT-001 | ausgehend | COMP-TE-002 QueryEngine | `get_trace_links(workspace_id, filters) -> TraceLink[]` |
| IF-TE-INT-002 | ausgehend | COMP-TE-003 CoverageCalculator | `get_trace_links(workspace_id, link_type) -> TraceLink[]` |
| IF-TE-INT-003 | eingehend | COMP-TE-002 QueryEngine | `validate_graph_integrity() -> ValidationResult` |

## Externe Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-EXT-IN-003 | eingehend | ApplicationService | TraceLink-CRUD (`create`, `read`, `update`, `delete`) |
| IF-TE-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM — TraceLink-Entität + Custom Manager |

---

## L3 Komponenten-Anforderungen

### REQ-L3-TE001-001: TraceLink-CRUD mit Link-Typ-Validierung und Tenant-Isolation


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkManager SHALL TraceLinks für alle registrierten Link-Typen (`parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`, `documents`, `adr-architecture`) erstellen, lesen, aktualisieren und löschen. Vor der Persistenz SHALL der Link-Typ gegen die zulässige Menge validiert werden. Alle Operationen SHALL ausschließlich TraceLinks des aktiven Tenants betreffen; Cross-Tenant-Zugriffe SHALL abgewiesen werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Create TraceLink (source, target, type=`satisfies`) → returns TraceLink with UUID and `created_at`
- [ ] Create with invalid link type → raises `InvalidLinkTypeError`
- [ ] Create with source and target from different tenants → raises `CrossTenantLinkError`
- [ ] Read TraceLink from another tenant → returns empty result (not found)
- [ ] Delete TraceLink → removed; subsequent read returns not found
- [ ] Update link type to invalid value → raises `InvalidLinkTypeError`; existing link unchanged

---

### REQ-L3-TE001-002: Eager-Zyklenprüfung vor Single-Link-Persistenz


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkManager SHALL vor der Persistenz jedes einzelnen TraceLinks eine transitive Zyklenprüfung über alle transitiven Link-Typen durchführen. Wird ein Zyklus erkannt, SHALL die Operation abgebrochen werden, bevor der Link in die Datenbank geschrieben wird.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] A→B, B→C created; attempt C→A (any link type) → raises `CycleDetectedError` with cycle path
- [ ] Cycle error raised before any DB write (no intermediate state persisted)
- [ ] Non-cyclic multi-link graph (A→B, A→C) → both links created successfully
- [ ] After rejected cycle attempt, existing links remain unchanged

---

### REQ-L3-TE001-003: Atomare Batch-Operation mit Tarjan-Zyklenprüfung am Transaktionsende


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkManager SHALL Batch-Erstellung und Batch-Löschung von TraceLinks in einer einzigen atomaren Datenbanktransaktion ausführen. Am Ende der Transaktion SHALL ein Tarjan-Algorithmus (O(V+E)) den vollständigen Link-Graphen auf Zyklen über alle transitiven Link-Typen prüfen. Bei erkanntem Zyklus oder Teilfehler SHALL die gesamte Transaktion zurückgesetzt werden; der Fehlerbericht SHALL den vollständigen Zyklus-Pfad enthalten.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Batch of 100 cycle-free TraceLinks → all 100 persisted atomically
- [ ] Batch with one invalid link → entire batch rolled back; DB unchanged
- [ ] Batch where last link closes a cycle → full rollback; error contains cycle path (e.g., `"Cycle: Req-A → Req-B → Req-C → Req-A"`)
- [ ] Tarjan check executed exactly once per batch transaction (not per link)
- [ ] Batch of 100 links completes in < 500ms

---

### REQ-L3-TE001-004: Referentielle Integrität (CASCADE) und Audit-Metadaten


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der TraceLinkManager SHALL bei Löschung eines referenzierten Artefakts automatisch alle zugehörigen TraceLinks in derselben atomaren Transaktion entfernen (CASCADE). Jeder TraceLink SHALL Audit-Felder (`created_by`, `created_at`, `modified_by`, `modified_at`) tragen; bei MCP-Operationen SHALL zusätzlich die Agent-Client-Identität und der gehashte API-Key erfasst werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Delete artifact with 3 linked TraceLinks → all 3 deleted in same transaction
- [ ] No orphaned TraceLinks visible after artifact deletion
- [ ] TraceLink created via REST API → `created_by` = authenticated User-ID
- [ ] TraceLink created via MCP → `created_by` = Agent-Client-ID; hashed API-Key stored
- [ ] Update TraceLink → `modified_by`/`modified_at` updated; `created_by`/`created_at` unchanged

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
