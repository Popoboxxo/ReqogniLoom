# L3 CoverageCalculator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-SM-004 — CoverageCalculator
> **Parent-System:** SeMetricsSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Berechnet Traceability Coverage: ermittelt aus TraceabilityEngine-Quelldaten Anteil der Requirements mit mindestens einem ausgehenden TraceLink, berechnet `coverage_percent` (1 Nachkommastelle), erstellt Liste `uncovered_ids`.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-SM-004 | Traceability-Coverage-Berechnung aus TraceabilityEngine-Quelldaten |
| REQ-L2-SM-008 | Read-Modell ohne Seiteneffekte |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-SM-INT-003 | eingehend | COMP-SM-002 MetricsAggregator | `calculate(coverage_data: CoverageData) -> CoverageResult` |

## Externe Schnittstellen (Systemgrenze)

Keine — der CoverageCalculator operiert auf den von COMP-SM-002 via IF-L1-045 abgerufenen Quelldaten.

---

## L3 Komponenten-Anforderungen

### REQ-L3-SM004-001: Coverage-Prozent und Mengenfelder berechnen

Der CoverageCalculator SHALL aus dem `CoverageData`-Eingabeobjekt (bereitgestellt von TraceabilityEngine via IF-L1-045) `total` (Gesamtanzahl Requirements im Workspace), `covered` (Anzahl Requirements mit mindestens einem ausgehenden TraceLink beliebigen Typs) und `coverage_percent` (covered / total * 100, auf eine Nachkommastelle gerundet) berechnen. Bei `total = 0` SHALL `coverage_percent` als `0.0` zurückgegeben werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 20 requirements, 15 with at least one outgoing trace link → `{total: 20, covered: 15, coverage_percent: 75.0}`
- [ ] 0 requirements → `{total: 0, covered: 0, coverage_percent: 0.0}` (no ZeroDivisionError)
- [ ] `coverage_percent` rounded to exactly one decimal place (e.g., 66.7 not 66.66...)
- [ ] Requirement with multiple trace links counted as `covered` exactly once

---

### REQ-L3-SM004-002: Liste unabgedeckter Requirement-IDs

Der CoverageCalculator SHALL eine Liste `uncovered_ids` aller Requirements erstellen, die keinen ausgehenden TraceLink beliebigen Typs besitzen. Die Liste SHALL ausschließlich `requirement_id`-Werte enthalten. Die Reihenfolge der Einträge ist nicht spezifiziert, muss aber deterministisch sein. Bei vollständiger Coverage (alle Requirements haben TraceLinks) SHALL `uncovered_ids` eine leere Liste sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Requirements R1 (covered), R2 (not covered), R3 (not covered) → `uncovered_ids: ["R2", "R3"]`
- [ ] All requirements have trace links → `uncovered_ids: []`
- [ ] No requirements → `uncovered_ids: []`
- [ ] `uncovered_ids` contains only IDs with zero outgoing trace links, regardless of trace link type

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
