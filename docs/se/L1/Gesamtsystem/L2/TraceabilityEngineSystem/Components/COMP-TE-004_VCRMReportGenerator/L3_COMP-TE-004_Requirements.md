# L3 VCRMReportGenerator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-TE-004 — VCRMReportGenerator
> **Parent-System:** TraceabilityEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Generiert die Verification Cross Reference Matrix (VCRM) als flache Matrix mit den Spalten `requirement_id`, `component_id`, `test_case_id`, `test_result` (Passed / Failed / Not Run). Filterbar nach Baseline und Workspace. Export als CSV (Pflicht) und optional als PDF via Template-Renderer.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-TE-013 | VCRM Report-Generator: flache Matrix, CSV-Export (Pflicht), PDF-Export (optional) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-INT-004 | ausgehend | COMP-TE-003 CoverageCalculator | `get_coverage_data(workspace_id, baseline_id?) -> CoverageData` |
| IF-TE-INT-005 | ausgehend | COMP-TE-002 QueryEngine | `query(artifact_id, direction, ctx) -> TraceLink[]` |

## Externe Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-EXT-IN-002 | eingehend | ApplicationService | `coverage(workspace_id, filters?, ctx)` — VCRM-Abruf |
| IF-TE-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM — Lesezugriff für Metadaten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-TE004-001: VCRM-Matrix-Generierung mit Baseline- und Workspace-Filter

Der VCRMReportGenerator SHALL eine flache Matrix mit den Spalten `requirement_id`, `component_id`, `test_case_id` und `test_result` (`Passed`, `Failed`, `Not Run`) generieren. Die Matrix SHALL nach Workspace gefiltert werden. Optional SHALL eine Baseline-ID übergeben werden können, sodass die Matrix den Zustand zum jeweiligen Snapshot-Zeitpunkt widerspiegelt.

**Priority:** desired

**Acceptance Criteria:**
- [ ] `generate_vcrm(workspace_id)` → matrix with one row per requirement–component–test-case combination
- [ ] Row without test case link → `test_result = "Not Run"`
- [ ] `generate_vcrm(workspace_id, baseline_id=<id>)` → matrix reflects state at baseline snapshot point
- [ ] Empty workspace → empty matrix returned (no error)
- [ ] Matrix rows contain exactly: `requirement_id`, `component_id`, `test_case_id`, `test_result`

---

### REQ-L3-TE004-002: CSV-Export der VCRM-Matrix

Der VCRMReportGenerator SHALL die generierte VCRM-Matrix als valide CSV-Datei exportieren. Die CSV-Datei SHALL herunterladbar sein und alle Matrix-Zeilen mit korrekter Spaltenstruktur enthalten.

**Priority:** desired

**Acceptance Criteria:**
- [ ] `export_vcrm_csv(workspace_id)` → returns valid CSV bytes with header row: `requirement_id,component_id,test_case_id,test_result`
- [ ] CSV contains one data row per requirement–component–test-case combination
- [ ] CSV file is downloadable via API response (correct `Content-Type: text/csv` header)
- [ ] Empty workspace → CSV with header only, no data rows

---

### REQ-L3-TE004-003: Optionaler PDF-Export der VCRM-Matrix via Template-Renderer

Der VCRMReportGenerator SOLLTE die VCRM-Matrix als PDF-Datei exportieren können. Der PDF-Export SHALL via Template-Renderer implementiert werden und denselben Datenstand wie der CSV-Export verwenden. Ist der PDF-Export nicht implementiert, SHALL der Endpunkt einen klar verständlichen Fehler zurückgeben.

**Priority:** optional

**Acceptance Criteria:**
- [ ] `export_vcrm_pdf(workspace_id)` → returns valid PDF bytes when PDF export is implemented
- [ ] PDF content matches CSV content (same rows and columns)
- [ ] PDF export not implemented → raises `NotImplementedError` or returns HTTP 501 with clear message
- [ ] PDF file downloadable via API response (correct `Content-Type: application/pdf` header)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
