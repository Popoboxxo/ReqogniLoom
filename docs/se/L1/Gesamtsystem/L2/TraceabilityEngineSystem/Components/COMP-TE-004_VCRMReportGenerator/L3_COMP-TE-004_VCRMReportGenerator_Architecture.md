---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T11:05:00Z"
schema_version: "1.0.0"
---

# L3 VCRMReportGenerator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-TE-004_VCRMReportGenerator
> **Parent:** L2_TraceabilityEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der VCRMReportGenerator generiert die Verification Cross Reference Matrix (VCRM): eine flache Matrix mit den Spalten requirement_id, component_id, test_case_id, test_result (Passed / Failed / Not Run). Der Generator unterstützt Workspace-Filter und optional Baseline-Snapshots, CSV-Export (Pflicht) und optionalen PDF-Export via Template-Renderer.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`VCRMReportGenerator` (Klasse):** Hauptklasse mit Methoden `generate_vcrm(workspace_id, baseline_id?)`, `export_vcrm_csv(workspace_id, baseline_id?)`, `export_vcrm_pdf(workspace_id, baseline_id?)`.
- **`MatrixBuilder` (Klasse):** Baut flache Matrix aus CoverageData. Eine Zeile pro requirement–component–test_case Kombination.
- **`CSVExporter` (Klasse):** Serialisiert Matrix zu CSV-Format mit Header-Zeile.
- **`PDFExporter` (Klasse):** Nutzt Template-Renderer zur PDF-Generierung (optional; kann NotImplementedError werfen).
- **`TestResultMapper` (Klasse):** Mappt interne Test-States zu "Passed" / "Failed" / "Not Run".

### 2.2 Datenstrukturen

- **`VCRMRow` (Pydantic Model):** {requirement_id, component_id, test_case_id, test_result}.
- **`VCRMMatrix` (Pydantic Model):** {rows: List[VCRMRow]}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-TE004-001 (VCRM-Matrix-Generierung) | MatrixBuilder liest CoverageData (von COMP-TE-003). Für jedes Requirement-Component-TestCase-Tripel: eine Zeile. test_result: "Passed"|"Failed"|"Not Run" (Default: "Not Run" wenn kein Link). Optional baseline_id für Snapshot. |
| REQ-L3-TE004-002 (CSV-Export) | CSVExporter schreibt CSV mit Header (requirement_id,component_id,test_case_id,test_result) und Datenzeilen. Downloadbar. |
| REQ-L3-TE004-003 (Optionaler PDF-Export) | PDFExporter nutzt Template-Renderer. Wenn nicht implementiert: NotImplementedError oder HTTP 501. Selber Datenstand wie CSV. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-TE-EXT-IN-002:** Von ApplicationService: VCRM-Abruf.

**Ausgänge (Outbound):**
- **IF-TE-INT-004:** Zu COMP-TE-003 (CoverageCalculator): `get_coverage_data(workspace_id, baseline_id?)`.
- **IF-TE-INT-005:** Zu COMP-TE-002 (QueryEngine): `query(artifact_id, direction, ctx)` für Trace-Links.
- **IF-TE-EXT-OUT-001:** Zu PersistenceLayer (Django ORM): Lesezugriff für Metadaten.

---

## 5. Architectural Rationale

**ADR-L3-TE4-01 — Flache Matrix statt Nested Struktur**

*Entscheidung:* VCRMMatrix.rows ist flache Liste von VCRMRow, nicht nested per Requirement.

*Rationale:* Erfüllt Serialisierbarkeit und CSV-Kompatibilität (REQ-L3-TE004-002 "CSV contains one data row per requirement–component–test_case combination"). Flache Struktur ist simpel und Clients-freundlich. Alternative: Nested {requirement: [{test_cases: []}]} → würde CSV-Generierung erschweren.

---

**ADR-L3-TE4-02 — CSV-Export Pflicht, PDF optional**

*Entscheidung:* export_vcrm_csv() ist erforderlich und wirft keinen Fehler. export_vcrm_pdf() kann NotImplementedError werfen oder HTTP 501 zurückgeben.

*Rationale:* Erfüllt REQ-L3-TE004-002 und 003 (CSV mandatory, PDF optional). CSV ist universell einsetzbar. PDF erfordert zusätzliche Dependencies und Template-Maintenance. Alternative: Beides optional → würde Clients verwirren.

---

**ADR-L3-TE4-03 — Baseline-unterstützung für Snapshot-Vergleiche**

*Entscheidung:* generate_vcrm(), export_vcrm_csv(), export_vcrm_pdf() akzeptieren optional baseline_id.

*Rationale:* Erfüllt REQ-L3-TE004-001 ("baseline_id parameter ... matrix reflects state at baseline snapshot point"). Ermöglicht historische Audit-Reports. Alternative: Immer aktuell → würde keine Zeitstempel-Vergleiche ermöglichen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
