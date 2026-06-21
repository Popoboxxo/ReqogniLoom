# L3 WorkflowGapDetector Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-SM-005 — WorkflowGapDetector
> **Parent-System:** SeMetricsSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Erkennt Workflow-Lücken: identifiziert aus WorkflowEngine-Quelldaten Items, die einen obligatorischen Zustand der aktiven WorkflowDefinition nie durchlaufen haben, erstellt Liste mit `item_id`, `item_type` und `missing_state`.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-SM-005 | Workflow-Lücken-Erkennung aus WorkflowEngine-Quelldaten |
| REQ-L2-SM-008 | Read-Modell ohne Seiteneffekte |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-SM-INT-004 | eingehend | COMP-SM-002 MetricsAggregator | `detect(incomplete_states: list[IncompleteState]) -> WorkflowGapResult` |

## Externe Schnittstellen (Systemgrenze)

Keine — der WorkflowGapDetector operiert auf den von COMP-SM-002 via IF-L1-046 abgerufenen Quelldaten.

---

## L3 Komponenten-Anforderungen

### REQ-L3-SM005-001: Erkennung fehlender Pflicht-Zustände je Item

Der WorkflowGapDetector SHALL aus der übergebenen Liste von `IncompleteState`-Objekten (geliefert von WorkflowEngine) alle Items identifizieren, die mindestens einen obligatorischen Zustand der aktiven WorkflowDefinition ihres Workspaces nie durchlaufen haben. Ein Item gilt als Lücke, wenn es in `find_incomplete_states`-Ergebnis enthalten ist. Für jede Lücke SHALL ein Eintrag mit `item_id`, `item_type` und `missing_state` erzeugt werden. Bei einem Workspace ohne konfigurierte WorkflowDefinition SHALL die Ergebnisliste leer sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Item with active WorkflowDefinition requiring state `reviewed`, no `reviewed` history → included in gap list with `missing_state: "reviewed"`
- [ ] Item with complete workflow history → not in gap list
- [ ] Workspace with no configured WorkflowDefinition → `{total_incomplete: 0, items: []}`
- [ ] Each gap entry contains exactly the fields `item_id`, `item_type`, `missing_state`

---

### REQ-L3-SM005-002: Gesamtanzahl und strukturierte Ergebnisrückgabe

Der WorkflowGapDetector SHALL `total_incomplete` als Anzahl aller Items mit mindestens einer Workflow-Lücke und `items` als vollständige Liste aller Lücken-Einträge zurückgeben. Ein Item mit mehreren fehlenden Pflicht-Zuständen SHALL mehrfach in `items` erscheinen (einmal je fehlendem Zustand), zählt aber in `total_incomplete` nur einmal.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Item missing two mandatory states → appears twice in `items` list, counted once in `total_incomplete`
- [ ] `total_incomplete` equals count of distinct `item_id` values in `items`
- [ ] Empty input list → `{total_incomplete: 0, items: []}`
- [ ] Result is deterministic for identical input

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
