---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T11:00:00Z"
schema_version: "1.0.0"
---

# L3 CoverageCalculator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-TE-003_CoverageCalculator
> **Parent:** L2_TraceabilityEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der CoverageCalculator (Traceability-Engine-Version) berechnet Test-Coverage: den Prozentsatz der Requirements mit mindestens einem `verifies`-TraceLink zu einem TestCase. Er unterstützt optional Filterung nach Artefakttyp und Link-Typ, exakte Coverage-Daten (per-requirement Test-Zuordnung) für den VCRM-Report-Generator und Baseline-Snapshots.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`CoverageCalculator` (Klasse):** Hauptklasse mit Methoden `coverage(workspace_id, filters?, ctx)` und `get_coverage_data(workspace_id, baseline_id?)`.
- **`VerifiesLinkCounter` (Klasse):** Zählt Requirements mit `verifies`-Links zu TestCases.
- **`FilterApplier` (Klasse):** Appliziert optional Filter nach artifact_type und link_type.
- **`CoverageDataBuilder` (Klasse):** Erstellt strukturierte CoverageData mit per-requirement Test-Zuordnung.
- **`BaselineSnapshotReader` (Klasse):** Liest Trace-Graph-Snapshot für Baseline-ID.

### 2.2 Datenstrukturen

- **`CoverageReport` (Pydantic Model):** {total, covered, uncovered: List[str], percentage (float, 1 Dezimalstelle)}.
- **`CoverageData` (Pydantic Model):** {requirements: {req_id: {test_cases: [{id, result: "Passed"|"Failed"|"Not Run"}]}}}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-TE003-001 (Requirement-Test-Coverage) | VerifiesLinkCounter zählt Requirements mit `verifies`-Link. Berechnet total (alle Reqs), covered (mit mindestens 1 `verifies`), uncovered (Rest). percentage = (covered / total * 100), 1 Dezimalstelle. ≤500ms p95. |
| REQ-L3-TE003-002 (Gefilterte Coverage) | FilterApplier nimmt optional artifact_type und link_type. Zeigt nur Reqs des Typs, nur deren Links vom Typ. Ungültige Filter → InvalidFilterError. |
| REQ-L3-TE003-003 (Coverage-Daten-Export) | get_coverage_data() erzeugt CoverageData mit per-requirement Test-Zuordnung. Optional baseline_id für historische Abfrage. JSON-serialisierbar. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-TE-EXT-IN-002:** Von ApplicationService: `coverage(workspace_id, filters?, ctx)`.

**Ausgänge (Outbound):**
- **IF-TE-INT-002:** Zu COMP-TE-001 (TraceLinkManager): `get_trace_links(workspace_id, link_type)`.
- **IF-TE-INT-004:** Zu COMP-TE-004 (VCRMReportGenerator): `get_coverage_data(workspace_id, baseline_id?)`.
- **IF-TE-EXT-OUT-001:** Zu PersistenceLayer (Django ORM): Lesezugriff auf TraceLink-Entity.

---

## 5. Architectural Rationale

**ADR-L3-TE3-01 — Nur `verifies`-Links für Test-Coverage**

*Entscheidung:* Coverage zählt nur TraceLinks mit link_type="verifies". Andere Link-Typen zählen nicht.

*Rationale:* Erfüllt REQ-L3-TE003-001 ("coverage: Requirement → Test-Abdeckung" via `verifies`). Semantisch: `verifies` bedeutet "getestet durch". Alternative: Alle Link-Typen → würde Coverage-Prozentsatz künstlich erhöhen.

---

**ADR-L3-TE3-02 — Eine-Dezimalstelle für percentage**

*Entscheidung:* percentage = (covered / total * 100), gerundet auf 1 Dezimalstelle.

*Rationale:* Erfüllt REQ-L3-TE003-001 ("percentage: 70.0"). Konsistent mit anderen Metriken. Alternative: Unbegrenzte Dezimalstellen → würde JSON bloaten.

---

**ADR-L3-TE3-03 — Baseline-unterstützung via Snapshot-Reader**

*Entscheidung:* get_coverage_data() akzeptiert optional baseline_id. Bei Angabe: liest Trace-Graph aus Baseline-Snapshot.

*Rationale:* Erfüllt REQ-L3-TE003-003 ("Optional ... a Baseline-ID ... returns data reflecting state at baseline snapshot point"). Ermöglicht historische Berichte. Alternative: Immer aktuell → würde keine Zeitstempel-Vergleiche ermöglichen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
