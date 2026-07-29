---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:45:00Z"
schema_version: "1.0.0"
---

# L3 WorkflowGapDetector Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-SM-005_WorkflowGapDetector
> **Parent:** L2_SeMetricsSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der WorkflowGapDetector identifiziert Workflow-Lücken aus WorkflowEngine-Quelldaten. Er erkennt Items, die einen obligatorischen Zustand ihrer aktiven WorkflowDefinition nie durchlaufen haben, und erstellt eine strukturierte Liste mit Item-ID, Item-Typ und Missing-State.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`WorkflowGapDetector` (Klasse):** Hauptklasse mit Methode `detect(incomplete_states: list[IncompleteState]) -> WorkflowGapResult`.
- **`GapItemGrouper` (Klasse):** Gruppiert IncompleteState-Einträge nach item_id. Zählt distinct Items.
- **`GapListBuilder` (Klasse):** Baut flache Liste mit {item_id, item_type, missing_state} pro Gap. Ein Item mit 2 Lücken → 2 Einträge in der Liste, aber 1 in total_incomplete.

### 2.2 Datenstrukturen

- **`IncompleteState` (Pydantic Model):** {item_id, item_type, missing_state}.
- **`WorkflowGap` (Pydantic Model):** {item_id, item_type, missing_state}.
- **`WorkflowGapResult` (Pydantic Model):** {total_incomplete: int, items: List[WorkflowGap]}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-SM005-001 (Erkennung fehlender Pflicht-Zustände) | GapItemGrouper liest IncompleteState-Liste. Ein Item ist "Lücke", wenn es im Input-List enthalten ist (von WorkflowEngine). Für jede Lücke: {item_id, item_type, missing_state}. Bei keiner WorkflowDefinition im Workspace: items=[]. |
| REQ-L3-SM005-002 (Gesamtanzahl & strukturierte Rückgabe) | total_incomplete = Unique item_ids in items-Liste (Distinct-Count). items = vollständige Lücken-Liste (ein Item mit 2 fehlenden States → 2 Einträge). |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-SM-INT-004:** Von COMP-SM-002 (MetricsAggregator): `detect(incomplete_states: list[IncompleteState]) -> WorkflowGapResult`.

**Ausgänge (Outbound):**
- Keine externen Schnittstellen. Detector operiert stateless auf Input-Daten.

---

## 5. Architectural Rationale

**ADR-L3-SM5-01 — Distinct-Count für total_incomplete, nicht total-items**

*Entscheidung:* total_incomplete = Unique item_ids. Ein Item mit mehreren fehlenden States → einmal in total_incomplete, mehrfach in items-Liste.

*Rationale:* Erfüllt REQ-L3-SM005-002 ("One item missing two mandatory states → appears twice in items list, counted once in total_incomplete"). Semantisch korrekt: "wie viele Items haben Lücken" vs. "wie viele Lücken insgesamt". Alternative: Zählen aller Lücken-Einträge → würde Semantik verzerren.

---

**ADR-L3-SM5-02 — Flache Liste statt Nested Struktur**

*Entscheidung:* WorkflowGapResult.items ist flache Liste von WorkflowGap, nicht nested per Item.

*Rationale:* Erfüllt Serialisierbarkeit und einfache Iteration (REQ-L3-SM005-002 "items as complete list of gap entries"). Nested Struktur würde Clients zwingen zu unnötigen Umstrukturierungen. Alternative: Nested {item_id: [{missing_states}]} → würde Komplexität erhöhen.

---

**ADR-L3-SM5-03 — Empty List bei keiner WorkflowDefinition**

*Entscheidung:* Workspace ohne aktive WorkflowDefinition → {total_incomplete: 0, items: []} (nicht "undefined" oder Error).

*Rationale:* Erfüllt REQ-L3-SM005-001 ("Workspace with no configured WorkflowDefinition → {total_incomplete: 0, items: []}"). Graceful: keine Lücken, wenn kein Workflow konfiguriert. Alternative: Error → würde Clients zwingen zu Fehlerbehandlung.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
