# L3 DeltaIndexBuilder Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-BL-001 — DeltaIndexBuilder
> **Parent-System:** BaselineServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Scope-Aufloesung, Item-ID/Version-Ermittlung, Immutability-Enforcement, Naming/Metadata-Validierung; persistiert ausschliesslich `(item_id, version)`-Tupel ohne Payload.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-BL-001 | Scope-Aufloesung und Delta-Storage (item_id, version) |
| REQ-L2-BL-004 | Preset Gate — Scope-Verfuegbarkeit pruefen |
| REQ-L2-BL-005 | Baseline Naming und Metadata-Validierung |
| REQ-L2-BL-008 | Baseline Creation Performance (bis 10.000 Items in 5s) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-INT-001 | ausgehend | COMP-BL-003 (BaselineStore) | `persist_delta_index(delta_index, metadata) -> baseline_id` |
| IF-BL-INT-003 | ausgehend | COMP-BL-002 (DiffEngine) | `get_delta_index(baseline_id) -> list[tuple[item_id, version]]` (optional) |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-EXT-IN-001 | eingehend | ApplicationService | `build(scope, workspace_id, name, description, ctx)` |
| IF-BL-EXT-IN-002 | eingehend | PresetConfigEngine | Scope-Verfuegbarkeitsregeln |
| IF-BL-EXT-IN-003 | eingehend | TraceabilityEngine | `collect_trace_graph(workspace_id) -> item_ids, versionen, trace_links` |

## L3 Komponenten-Anforderungen

### REQ-L3-BL001-001: Scope-Aufloesung und Delta-Index-Erstellung

Der DeltaIndexBuilder SHALL fuer jeden eingehenden `build`-Aufruf den angeforderten Scope (`document`, `project`, `global`) auflösen, alle betroffenen Item-IDs mit exakter Versions-Nummer ermitteln (via TraceabilityEngine) und einen Delta-Index als Menge von `(item_id, version)`-Tupeln erstellen. Der vollstaendige Item-Payload (title, description, content) DARF NICHT im Delta-Index enthalten sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `build(scope="project", workspace_id=W)` with 10 requirements and 3 arch elements → delta index contains exactly 13 `(item_id, version)` tuples
- [ ] Delta index entries contain no title/description/content payload fields
- [ ] `build(scope="document", artifact_id=A)` with 2 children → index contains A, both children and trace link references
- [ ] `build(scope="global")` → all items across all workspaces of the tenant included

---

### REQ-L3-BL001-002: Preset-Gate-Pruefung vor Scope-Aufloesung

Der DeltaIndexBuilder SHALL vor jeder Scope-Aufloesung die PresetConfigEngine konsultieren und den Aufruf mit einem Fehler abbrechen, wenn der angeforderte Scope gemaess der aktuellen Preset-Konfiguration nicht verfuegbar ist.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Preset=Minimal → `build(scope="document")` → raises error before scope resolution starts
- [ ] Preset=Standard → `build(scope="document")` OK, `build(scope="global")` → raises error
- [ ] Preset=Extended → all three scopes accepted
- [ ] Preset check occurs before any call to TraceabilityEngine

---

### REQ-L3-BL001-003: Baseline-Naming- und Metadata-Validierung

Der DeltaIndexBuilder SHALL vor der Persistierung sicherstellen, dass der Baseline-Name nicht leer ist und im selben Workspace eindeutig ist. Die Metadata-Struktur SHALL `name`, `scope`, `workspace_id`, `created_by`, `created_at` (UTC) enthalten; `description` ist optional.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Empty name → raises error `"Baseline name must not be empty"` before persisting
- [ ] Duplicate name in same workspace → raises error `"Baseline name must be unique"`
- [ ] Same name in different workspace → accepted
- [ ] `created_at` is stored as UTC timestamp

---

### REQ-L3-BL001-004: Performance-Anforderung fuer die Delta-Index-Erstellung

Der DeltaIndexBuilder SHALL die Delta-Index-Erstellung (Scope-Aufloesung + Tupel-Zusammenstellung) fuer bis zu 10.000 Items innerhalb von 4 Sekunden abschliessen, sodass die Gesamtlatenz des BaselineService (inkl. Persistenz) das 5-Sekunden-Ziel aus REQ-L2-BL-008 einhalten kann.

**Priority:** desired
**Acceptance Criteria:**
- [ ] Scope resolution + tuple assembly for 10,000 items completes in < 4s (p95)
- [ ] No full item payload is loaded during index creation (only IDs and versions)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
