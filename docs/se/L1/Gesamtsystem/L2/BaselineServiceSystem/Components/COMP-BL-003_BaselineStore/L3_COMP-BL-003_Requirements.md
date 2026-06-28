# L3 BaselineStore Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-BL-003 — BaselineStore
> **Parent-System:** BaselineServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Baseline-Persistenz (INSERT/SELECT), Retrieval und Listing der Delta-Index-Tabelle, Tenant-Isolation, atomare Transaktionen.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-BL-002 | Baseline Immutability — kein UPDATE/DELETE nach Erstellung |
| REQ-L2-BL-006 | Baseline Retrieval und Listing (gefiltert, sortiert) |
| REQ-L2-BL-007 | Atomare Erstellung mit vollstaendigem Rollback |
| REQ-L2-BL-008 | Baseline Creation Performance (Persistenz-Anteil) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-INT-001 | eingehend | COMP-BL-001 (DeltaIndexBuilder) | `persist_delta_index(delta_index, metadata) -> baseline_id` |
| IF-BL-INT-002 | ausgehend | COMP-BL-002 (DiffEngine) | `load_delta_index(baseline_id) -> list[tuple[item_id, version]]` |
| IF-BL-INT-004 | eingehend | COMP-BL-004 (VersionReconstructor) | `lookup_item_version(baseline_id, item_id) -> version` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-EXT-OUT-001 | ausgehend | PersistenceLayer (Django ORM) | Baseline-Entitaet (INSERT/SELECT, immutable) |
| IF-BL-EXT-IN-001 | eingehend | ApplicationService | `get(baseline_id)`, `list(workspace_id, scope?)` |

## L3 Komponenten-Anforderungen

### REQ-L3-BL003-001: Unveraenderlichkeit durch Enforcement auf Persistenzebene


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der BaselineStore SHALL Modifikationen und Loeschungen persistierter Baselines auf Ebene der Datenbankschicht verhindern. UPDATE- und DELETE-Operationen auf Baseline-Eintraegen SOLLEN einen klar formulierten Fehler ausloesen. Duplikate der Baseline-ID SOLLEN mit einem eindeutigen Fehler abgelehnt werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] UPDATE on a persisted baseline snapshot field → raises error `"Baselines are immutable"`
- [ ] DELETE of a baseline record → raises error `"Baselines are immutable"`
- [ ] INSERT with duplicate baseline_id → raises error `"Duplicate baseline ID"`
- [ ] Immutability enforced at DB constraint level (not only application layer)

---

### REQ-L3-BL003-002: Atomare Persistenz mit vollstaendigem Rollback


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der BaselineStore SHALL Baseline-Erstellungen atomar durchfuehren: entweder der vollstaendige Delta-Index (alle `(item_id, version)`-Tupel) wird persistiert oder es werden bei Fehler keinerlei Daten geschrieben (vollstaendiges Rollback).

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] DB error during snapshot write → rollback: no baseline record or index entries in DB
- [ ] Baseline with 1,000 items → either all 1,000 tuples persisted or none
- [ ] Transaction wraps both baseline header and all delta index entries

---

### REQ-L3-BL003-003: Retrieval, Listing und Tenant-Isolation


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der BaselineStore SHALL Einzelabruf (vollstaendiger Snapshot inkl. Delta-Index) und Listing (Metadaten ohne Snapshot, optional nach Scope gefiltert, sortiert nach `created_at` DESC) unterstuetzen. Alle Lesezugriffe SOLLEN auf den jeweiligen Workspace/Tenant isoliert sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `list(workspace_id=W)` → all baselines for W, sorted by created_at DESC, no delta index in response
- [ ] `list(workspace_id=W, scope="project")` → only project-scoped baselines for W
- [ ] `get(baseline_id)` → full snapshot including all delta index tuples
- [ ] `get(nonexistent_id)` → raises error `"Baseline not found"`
- [ ] `list(workspace_id=W)` does not return baselines from other workspaces

---

### REQ-L3-BL003-004: Versions-Lookup fuer VersionReconstructor


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der BaselineStore SHALL fuer einen gegebenen `(baseline_id, item_id)`-Schluessel die gespeicherte Versions-Nummer aus dem Delta-Index zurueckliefern. Wenn das Item nicht in der Baseline enthalten ist, SHALL ein Fehler ausgeloest werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `lookup_item_version(bl_id, item_id)` → returns stored version number
- [ ] `lookup_item_version(bl_id, item_id)` where item_id not in baseline → raises error `"Item not part of this baseline"`
- [ ] Lookup completes without loading full delta index into memory

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
