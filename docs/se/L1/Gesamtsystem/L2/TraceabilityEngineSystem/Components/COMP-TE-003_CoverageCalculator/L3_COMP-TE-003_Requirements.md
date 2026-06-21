# L3 CoverageCalculator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-TE-003 — CoverageCalculator
> **Parent-System:** TraceabilityEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Test-Coverage-Berechnung (Requirement → TestCase via `verifies`), gefilterte Coverage nach Artefakttyp und Link-Typ.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-TE-006 | Coverage-Berechnung: Requirement → Test-Abdeckung (≤ 500ms) |
| REQ-L2-TE-007 | Coverage-Filterung nach Artefakttyp und Link-Typ |
| REQ-L2-TE-012 | TraceLink-Query-Performance-SLA (mitwirkend) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-INT-002 | eingehend | COMP-TE-001 TraceLinkManager | `get_trace_links(workspace_id, link_type) -> TraceLink[]` |
| IF-TE-INT-004 | ausgehend | COMP-TE-004 VCRMReportGenerator | `get_coverage_data(workspace_id, baseline_id?) -> CoverageData` |

## Externe Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-TE-EXT-IN-002 | eingehend | ApplicationService | `coverage(workspace_id, filters?, ctx)` |
| IF-TE-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM — Lesezugriff auf TraceLink-Entität |

---

## L3 Komponenten-Anforderungen

### REQ-L3-TE003-001: Requirement-Test-Coverage-Berechnung

Der CoverageCalculator SHALL den Prozentsatz der Requirements berechnen, die mindestens einen `verifies`-TraceLink zu einem TestCase besitzen. Das Ergebnis SHALL `total`, `covered`, `uncovered` (IDs) und `percentage` enthalten. Die Berechnung SHALL ≤ 500ms (p95) bei bis zu 10.000 Requirements einhalten.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] 10 requirements, 7 with `verifies` links → result: `{total: 10, covered: 7, uncovered: [<3 IDs>], percentage: 70.0}`
- [ ] Empty workspace → result: `{total: 0, covered: 0, uncovered: [], percentage: 0.0}`
- [ ] 10.000 requirements → ≤ 500ms (p95)
- [ ] `uncovered` list contains exactly the IDs of requirements without any `verifies` link

---

### REQ-L3-TE003-002: Gefilterte Coverage-Berechnung nach Artefakttyp und Link-Typ

Der CoverageCalculator SOLLTE Coverage-Abfragen optional nach Artefakttyp (`artifact_type`) und Link-Typ (`link_type`) filtern können. Werden keine Filter angegeben, SHALL das Verhalten identisch zu REQ-L3-TE003-001 sein. Gefilterte Abfragen SHALL ≤ 500ms (p95) bei 10.000 Items einhalten.

**Priority:** desired

**Acceptance Criteria:**
- [ ] `coverage(workspace_id, artifact_type='ArchitectureElement', link_type='satisfies')` → filtered report containing only ArchitectureElements with `satisfies` links
- [ ] `coverage(workspace_id)` (no filters) → same result as unfiltered calculation
- [ ] Filtered query on 10.000 items → ≤ 500ms (p95)
- [ ] Unknown artifact_type or link_type → raises `InvalidFilterError`

---

### REQ-L3-TE003-003: Coverage-Daten-Export für VCRMReportGenerator

Der CoverageCalculator SHALL auf interne Anfrage des VCRMReportGenerators (IF-TE-INT-004) strukturierte Coverage-Daten zurückgeben. Das Ergebnis (`CoverageData`) SHALL für jedes Requirement die verknüpften TestCase-IDs und deren Test-Ergebnis (`Passed`, `Failed`, `Not Run`) enthalten. Optional SHALL eine Baseline-ID für historische Abfragen übergeben werden können.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `get_coverage_data(workspace_id)` → returns `CoverageData` with per-requirement test case mapping
- [ ] Requirement without test link → `test_result = "Not Run"` in returned data
- [ ] `get_coverage_data(workspace_id, baseline_id=<id>)` → returns data reflecting state at baseline snapshot
- [ ] Returned `CoverageData` is JSON-serializable

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
