---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:40:00Z"
schema_version: "1.0.0"
---

# L3 CoverageCalculator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-SM-004_CoverageCalculator
> **Parent:** L2_SeMetricsSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der CoverageCalculator berechnet Traceability-Coverage-Metriken aus TraceabilityEngine-Quelldaten. Er ermittelt, welcher Anteil der Requirements mindestens einen ausgehenden TraceLink beliebigen Typs besitzt, berechnet den Prozentsatz (1 Dezimalstelle), und erstellt eine Liste unabgedeckter Requirement-IDs.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`CoverageCalculator` (Klasse):** Hauptklasse mit Methode `calculate(coverage_data: CoverageData) -> CoverageResult`.
- **`TraceLinkCounter` (Klasse):** Zählt Requirements mit mindestens einem TraceLink. Aggregiert nach Requirement-ID.
- **`UncoveredCollector` (Klasse):** Sammelt IDs von Requirements ohne TraceLink. Deterministisch sortiert.
- **`CoveragePercentCalculator` (Klasse):** Berechnet (covered / total * 100), rundet auf 1 Dezimalstelle. Bei total=0: 0.0 (kein ZeroDivisionError).

### 2.2 Datenstrukturen

- **`CoverageData` (Pydantic Model):** {trace_links: List[TraceLink]} (bereitgestellt von TraceabilityEngine).
- **`TraceLink` (Pydantic Model):** {source_id, target_id, link_type}.
- **`CoverageResult` (Pydantic Model):** {total, covered, coverage_percent (float, 1 Dezimalstelle), uncovered_ids: List[str]}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-SM004-001 (Coverage-Prozent & Mengenfelder) | TraceLinkCounter extrahiert Unique source_ids aus TraceLinks (diese sind Requirements mit mindestens 1 Link). total = All Requirements in Workspace. covered = Unique source_ids. coverage_percent = (covered / total * 100), 1 Dezimalstelle. Bei total=0: 0.0. |
| REQ-L3-SM004-002 (Unabgedeckte IDs) | UncoveredCollector identifiziert Requirements ohne TraceLink (Differenz: All - covered). Sortiert deterministisch. Leere Liste bei vollständiger Coverage. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-SM-INT-003:** Von COMP-SM-002 (MetricsAggregator): `calculate(coverage_data: CoverageData) -> CoverageResult`.

**Ausgänge (Outbound):**
- Keine externen Schnittstellen. Calculator operiert stateless auf Input-Daten.

---

## 5. Architectural Rationale

**ADR-L3-SM4-01 — TraceLink-Quellen aggregieren nach source_id**

*Entscheidung:* Ein Requirement mit 3 TraceLinks zählt als "covered" genau einmal (nicht dreifach).

*Rationale:* Erfüllt REQ-L3-SM004-001 ("Requirement with multiple trace links counted as covered exactly once"). Semantisch korrekt: Coverage = "hat mindestens einen Link", nicht "hat wie viele Links". Alternative: Zählen aller Links → würde Coverage-Prozentsatz künstlich erhöhen.

---

**ADR-L3-SM4-02 — Ein-Dezimalstelle für coverage_percent**

*Entscheidung:* coverage_percent = (covered / total * 100), gerundet auf 1 Dezimalstelle.

*Rationale:* Erfüllt REQ-L3-SM004-001 ("coverage_percent rounded to exactly one decimal place (e.g., 66.7 not 66.66...)"). Präzise genug für Metriken, aber nicht übertrieben. Alternative: Ohne Dezimalstellen → würde kleine Unterschiede verlieren.

---

**ADR-L3-SM4-03 — Deterministische Sortierung uncovered_ids**

*Entscheidung:* uncovered_ids wird deterministisch sortiert (z.B. natürliche Zeichenfolgen-Ordnung).

*Rationale:* Erfüllt REQ-L3-SM004-002 ("The order of entries is not specified, must but be deterministic"). Macht Tests und Vergleiche möglich. Alternative: Unsortiert/Random → würde Flaky-Tests ermöglichen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
