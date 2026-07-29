---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 DiffEngine Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-BL-002_DiffEngine
> **Parent:** L2_BaselineServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die DiffEngine vergleicht zwei Baselines desselben Scopes und erzeugt ein strukturiertes Diff-Ergebnis mit drei Kategorien: `added` (Items nur in Baseline B), `removed` (Items nur in Baseline A), `changed` (Items in beiden mit unterschiedlicher Version). Sie validiert vorab Scope-Kompatibilität, lädt Delta-Indices aus dem BaselineStore und führt effiziente Set-basierte Vergleiche durch — keine Payload-Manipulationen.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`DiffEngine` (Klasse):** Orchestriert Scope-Validierung, Index-Loading und Diff-Berechnung.
- **`DiffResult` (Datenklasse):** Strukturiert die Diff-Ausgabe mit `added`, `removed`, `changed`.
- **`ChangedItem` (Datenklasse):** Reprä­sentiert ein Item mit `id`, `old_version`, `new_version`.
- **`IndexSet` (Helfer-Klasse):** Verwaltet `(item_id, version)`-Paare mit effizienten Lookups (dict-backed oder frozenset).

### 2.2 Datenstrukturen

- **Index-Representation (In-Memory):**
  - `baseline_a_items: dict[str, int]` — { item_id: version }
  - `baseline_b_items: dict[str, int]` — { item_id: version }
  - Größe: bis zu 10.000 Items pro Baseline

- **DiffResult:**
  - `added: list[str]` — item_ids nur in Baseline B
  - `removed: list[str]` — item_ids nur in Baseline A
  - `changed: list[ChangedItem]` — Items mit unterschiedlicher Version

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-BL002-001 (Strukturierter Diff) | Methode `diff(baseline_a_id, baseline_b_id)`: Lädt beide Indices, iteriert über set(a_items.keys() ∪ b_items.keys()), klassifiziert jedes Item in added/removed/changed. Gibt DiffResult zurück. |
| REQ-L3-BL002-002 (Scope-Kompatibilität) | Methode `_validate_scopes(baseline_a, baseline_b)`: Vergleicht baseline_a.scope == baseline_b.scope vor Index-Loading. Bei Fehler: ValueError mit klarer Nachricht. |
| REQ-L3-BL002-003 (Performance) | Set-basierter Vergleich O(n): Beide Indices als dict laden, einmalige Iteration. Ziel: < 2s für 10.000 Items pro Baseline. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-BL-EXT-IN-001:** Aufruf vom ApplicationService mit `diff(baseline_a_id, baseline_b_id)`.

- **Ausgänge (Outbound):**
  - **IF-BL-INT-002:** Aufruf an BaselineStore: `load_delta_index(baseline_id) -> list[tuple[item_id, version]]` (2x für baseline_a und baseline_b).

---

## 5. Architectural Rationale

**ADR-L3-BL002-01 — Set-basierter Diff-Algorithmus**
*Entscheidung:* Diff-Berechnung verwendet O(n) Set-Union-Operationen statt O(n²) verschachtelter Schleifen.
*Rationale:* Erfüllt REQ-L3-BL002-003 (Performance < 2s). Skalierbar für große Baselines.
*Alternative abgelehnt:* Nested-Loop-Vergleich — O(n²), würde 10.000 Items in > 2s verarbeiten.

**ADR-L3-BL002-02 — Early Scope-Validation**
*Entscheidung:* Scope-Kompatibilität wird geprüft BEVOR Indices geladen werden.
*Rationale:* Fail-fast, spart Index-Loading bei inkompatiblen Baselines.
*Alternative abgelehnt:* Scope-Check nach Index-Loading — verschwendet Ressourcen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
