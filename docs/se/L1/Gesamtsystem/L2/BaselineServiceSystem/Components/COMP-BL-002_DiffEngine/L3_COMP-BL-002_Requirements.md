# L3 DiffEngine Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-BL-002 — DiffEngine
> **Parent-System:** BaselineServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Vergleich zweier Baselines desselben Scopes (added/removed/changed mit Versions-Delta) auf Basis von `(item_id, version)`-Paaren, Scope-Kompatibilitaetspruefung.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-BL-003 | Baseline Diff (Vergleich zweier Baselines) |
| REQ-L2-BL-008 | Baseline Diff Performance (< 2s bei je 10.000 Items) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-INT-002 | eingehend | COMP-BL-003 (BaselineStore) | `load_delta_index(baseline_id) -> list[tuple[item_id, version]]` |
| IF-BL-INT-003 | eingehend (optional) | COMP-BL-001 (DeltaIndexBuilder) | `get_delta_index(baseline_id) -> list[tuple[item_id, version]]` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-BL-EXT-IN-001 | eingehend | ApplicationService | `diff(baseline_a_id, baseline_b_id)` |

## L3 Komponenten-Anforderungen

### REQ-L3-BL002-001: Strukturierter Baseline-Diff mit drei Kategorien

Die DiffEngine SHALL beim Vergleich zweier Baselines ein strukturiertes Ergebnis mit drei Kategorien liefern: `added` (Items nur in B), `removed` (Items nur in A), `changed` (Items in beiden Baselines mit unterschiedlicher Version, inkl. `old_version` und `new_version`). Items mit identischer Version in beiden Baselines werden nicht im Ergebnis aufgefuehrt.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `diff(A, B)` returns `{added: [...], removed: [...], changed: [{id, old_version, new_version}]}`
- [ ] Item present in both A and B with same version → not included in any category
- [ ] Item in B only → appears in `added`
- [ ] Item in A only → appears in `removed`
- [ ] Item in both with different version → appears in `changed` with both version values

---

### REQ-L3-BL002-002: Scope-Kompatibilitaetspruefung

Die DiffEngine SHALL vor der Diff-Berechnung pruefen, dass beide Baselines denselben Scope besitzen. Baselines unterschiedlichen Scopes SOLLEN mit einem klar formulierten Fehler abgelehnt werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `diff(A, B)` where A.scope != B.scope → raises error `"Cannot diff baselines of different scopes"`
- [ ] `diff(A, B)` where A.scope == B.scope → diff proceeds normally
- [ ] Scope check occurs before loading delta indices from store

---

### REQ-L3-BL002-003: Diff-Performance fuer grosse Baselines

Die DiffEngine SHALL Diff-Operationen zwischen zwei Baselines mit je bis zu 10.000 Items innerhalb von 2 Sekunden abschliessen (p95).

**Priority:** desired
**Acceptance Criteria:**
- [ ] `diff(A, B)` with 10,000 items each completes in < 2s (p95)
- [ ] Diff algorithm uses set-based comparison (O(n)) rather than nested iteration (O(n²))

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
