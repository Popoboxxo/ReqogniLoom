---
step: testplan
agent: se-integration-and-test-manager
iteration: 1
status: done
timestamp: "2026-07-01T00:00:00Z"
schema_version: "1.0.0"
---

# L2 DiagramServiceSystem — Integration & Test Plan (Canvas + Mermaid Delta)

> **Level:** L2
> **System:** DiagramServiceSystem (ARCH-L1-013)
> **Phase:** 5b — Canvas & Mermaid Delta Integration
> **Strategy:** Bottom-Up Delta
> **Gate:** G13
> **Date:** 2026-07-01
> **Status:** INTEGRATION_READY

---

## 1. Scope

This integration plan covers the **delta integration** of two new components into the existing DiagramServiceSystem:

| Component | ID | Type | Tests Implemented | REQ-ID |
|-----------|-----|------|------------------|--------|
| CanvasEditor | COMP-DS-006 | Leaf (new) | 39 | REQ-L2-DS-006 |
| MermaidLiveRenderer | COMP-DS-007 | Leaf (new) | 34 | REQ-L2-DS-007 |

**Existing components (COMP-DS-001..005):** Already verified in Phase 1-5 integration (Steps 1-12).

### 1.1 Prerequisites (Entry Criteria)

| Check | Status | Evidence |
|-------|--------|----------|
| Step 1: PersistenceLayer ✅ | ✅ PASSED | G1-G4 gates passed per integration-strategy.md |
| Step 6: TraceabilityEngine ✅ | ✅ PASSED | G6 gate passed |
| Step 10: RestApiAdapter ✅ | ✅ PASSED | G10 gate passed |
| Step 12: ReactFrontend ✅ | ✅ PASSED | G12 gate passed |
| DiagramService (COMP-DS-001..005) verified | ✅ PASSED | Legacy components in production |
| Backend pytest suite green (1599+) | ✅ PASSED | Test-coverage-2026-06-28.md |
| E2E Playwright suite green (111+) | ✅ PASSED | implementation_status_2026-06-27.md |
| MCP E2E suite green (150+) | ✅ PASSED | test-coverage-2026-06-28.md |

### 1.2 Integration Approach

**Bottom-Up Delta:** New components (COMP-DS-006, COMP-DS-007) are integrated bottom-up against existing components (COMP-DS-001..005) in 11 sequential sub-steps (13a–13k).

```
Step 13a-13b: Isolated Leaf Verification (L3-level)
Step 13c-13h: Interface Integration (L2-level internal)
Step 13i:      Frontend Integration (L2-level external)
Step 13j:      E2E Journeys
Step 13k:      Performance Validation
```

---

## 2. Sub-Step Integration Plan

### Step 13a: COMP-DS-006 Isolated (CanvasEditor)

| Attribute | Value |
|-----------|-------|
| **Target** | COMP-DS-006 CanvasEditor in isolation |
| **Scope** | Stroke-Validierung, SVG-Export, Auto-Save, TraceLink-Erstellung |
| **Tests** | 39 implemented (test_canvas_editor.py) |
| **Coverage mapping** | TC-CNV-001..015 from test-strategy.md §2.11 |
| **Delegation** | `se-verifier` — verify COMP-DS-006 isolated |
| **Pass criteria** | All 39 tests green; stroke validation for all element types (pen, rect, circle, text, connector); SVG export produces valid DOM |
| **Gate** | Internal — no gate |

### Step 13b: COMP-DS-007 Isolated (MermaidLiveRenderer)

| Attribute | Value |
|-----------|-------|
| **Target** | COMP-DS-007 MermaidLiveRenderer in isolation |
| **Scope** | 5 Mermaid-Typen (flowchart, sequence, class, state, er); Syntax-Fehler mit Zeilennummer; Render-Hints; Fallback |
| **Tests** | 34 implemented (test_mermaid_live_renderer.py) |
| **Coverage mapping** | TC-MRM-001..017 from test-strategy.md §2.11 |
| **Delegation** | `se-verifier` — verify COMP-DS-007 isolated |
| **Pass criteria** | All 34 tests green; all 5 Mermaid types validate; syntax errors include line numbers; fallback renders code as text |
| **Gate** | Internal — no gate |

### Step 13c: COMP-DS-006 → COMP-DS-002 (IF-DS-INT-004)

| Attribute | Value |
|-----------|-------|
| **Interface** | IF-DS-INT-004: CanvasEditor → DiagramValidator |
| **Scope** | Stroke-Daten-Validierung delegiert an DiagramValidator |
| **Prerequisites** | Step 13a ✅ (COMP-DS-006 isolated), COMP-DS-002 ✅ (legacy) |
| **Tests** | IT-CNV-01 (test_canvas_editor.py integration) |
| **Validation** | Valid `validate_canvas_strokes()` delegiert korrekt, ungültige Daten rejected |
| **Delegation** | `se-verifier` — verify interface contract IF-DS-INT-004 |

### Step 13d: COMP-DS-006 → COMP-DS-001 (IF-DS-INT-005)

| Attribute | Value |
|-----------|-------|
| **Interface** | IF-DS-INT-005: CanvasEditor → DiagramManager |
| **Scope** | Canvas-Persistierung (Stroke-Daten versioniert, Auto-Save) |
| **Prerequisites** | Step 13a ✅, COMP-DS-001 ✅ (legacy) |
| **Tests** | IT-CNV-02 (test_canvas_editor.py: `test_create_canvas_diagram`, `test_create_persists_canvas_stroke_format`) |
| **Validation** | Diagram created with type='canvas', version 1 persisted, audit entry written |
| **Delegation** | `se-verifier` — verify interface contract IF-DS-INT-005 |

### Step 13e: COMP-DS-006 → COMP-DS-004 (IF-DS-INT-006)

| Attribute | Value |
|-----------|-------|
| **Interface** | IF-DS-INT-006: CanvasEditor → TraceabilityConnector |
| **Scope** | Canvas-TraceLink (Typ 'documents') |
| **Prerequisites** | Step 13a ✅, COMP-DS-004 ✅ (legacy) |
| **Tests** | IT-CNV-03 (test_traceability_connector.py) |
| **Validation** | TraceLink vom Typ 'documents' erstellt; Target-Validierung funktioniert; Fehlerpropagation |
| **Delegation** | `se-verifier` — verify interface contract IF-DS-INT-006 |

### Step 13f: COMP-DS-007 → COMP-DS-001 (IF-DS-INT-007)

| Attribute | Value |
|-----------|-------|
| **Interface** | IF-DS-INT-007: MermaidLiveRenderer → DiagramManager |
| **Scope** | Mermaid-Persistierung (Source versioniert) |
| **Prerequisites** | Step 13b ✅, COMP-DS-001 ✅ (legacy) |
| **Tests** | IT-MRM-02 (test_mermaid_live_renderer.py: `test_handle_source_update_valid`) |
| **Validation** | Diagram created with type='mermaid', version 1, RenderHints generated |
| **Delegation** | `se-verifier` — verify interface contract IF-DS-INT-007 |

### Step 13g: COMP-DS-007 → COMP-DS-003 (IF-DS-INT-008)

| Attribute | Value |
|-----------|-------|
| **Interface** | IF-DS-INT-008: MermaidLiveRenderer → DiagramRenderer |
| **Scope** | Render-Hints (theme, engine, zoomable) |
| **Prerequisites** | Step 13b ✅, COMP-DS-003 ✅ (legacy) |
| **Tests** | IT-MRM-03 (test_renderer.py: mermaid render hint tests) |
| **Validation** | RenderHint enthält theme='default', engine='mermaid.js', zoomable=true, supported_types |
| **Delegation** | `se-verifier` — verify interface contract IF-DS-INT-008 |

### Step 13h: COMP-DS-007 → COMP-DS-005 (IF-DS-INT-009)

| Attribute | Value |
|-----------|-------|
| **Interface** | IF-DS-INT-009: MermaidLiveRenderer → McpArtifactProvider |
| **Scope** | MCP-Registrierung für Mermaid-Typ |
| **Prerequisites** | Step 13b ✅, COMP-DS-005 ✅ (legacy) |
| **Tests** | IT-MRM-04 (test_mcp_artifact_provider.py: MCP artifact tests) |
| **Validation** | Mermaid-Typ in MCP registriert; artifact.get liefert source_code + render_hints |
| **Delegation** | `se-verifier` — verify interface contract IF-DS-INT-009 |

### Step 13i: Frontend Integration

| Attribute | Value |
|-----------|-------|
| **Scope** | Canvas-Zeichenfläche, Mermaid-Editor, Live-Preview, Export UI |
| **Prerequisites** | Steps 13a-13h ✅, Step 12 ✅ (ReactFrontend) |
| **Tests** | TC-FE-CNV-001..006, TC-FE-MRM-001..005 (11 FE tests) |
| **Validation** | Pen drawing ≥30fps; Shape insertion; Text editing; Connector follows shapes; Mermaid live-preview updates on edit; Syntax error shown with line number; Export SVG/PNG functional |
| **Delegation** | `se-test-engineer` — frontend test definition; `se-verifier` — verification |

### Step 13j: E2E Journeys

| Attribute | Value |
|-----------|-------|
| **Scope** | Vollständige User-Journeys über Frontend → REST → DiagramService → PersistenceLayer → TraceabilityEngine → MCP |
| **Prerequisites** | Steps 13a-13i ✅ |
| **Tests** | E2E-CNV-01, E2E-CNV-02, E2E-MRM-01, E2E-MRM-02, E2E-MRM-03 (5 E2E tests) |
| **Validation** | Canvas zeichnen → speichern → verknüpfen → MCP abrufen; Mermaid-Code eingeben → Preview → korrigieren → exportieren; 5 Mermaid-Typen rendern; Mermaid TraceLink → MCP |
| **Delegation** | `se-validator` — system-level validation |

### Step 13k: Performance Validation

| Attribute | Value |
|-----------|-------|
| **Scope** | Canvas ≥30fps bei 500 Strokes+100 Shapes; Mermaid-Render <2s bei 100 Knoten |
| **Prerequisites** | Steps 13a-13j ✅ |
| **Tests** | TC-PERF-CNV-001..004, TC-PERF-MRM-001..004 (8 performance tests) |
| **Validation** | Canvas: ≥60fps minimal, ≥30fps guaranteed, ≥20fps graceful degradation; Mermaid: <500ms minimal, <1000ms normal, <2000ms guaranteed |
| **Delegation** | `se-verifier` — performance verification |

---

## 3. Delegation Summary

| Sub-Step | Agent | Action | Input | Output |
|----------|-------|--------|-------|--------|
| 13a | se-verifier | Verify COMP-DS-006 isolated | CanvasEditor implementation, test_canvas_editor.py | Verification report (pass/fail) |
| 13b | se-verifier | Verify COMP-DS-007 isolated | MermaidLiveRenderer impl., test_mermaid_live_renderer.py | Verification report (pass/fail) |
| 13c | se-verifier | Verify IF-DS-INT-004 | CanvasEditor ↔ DiagramValidator tests | Interface verification report |
| 13d | se-verifier | Verify IF-DS-INT-005 | CanvasEditor ↔ DiagramManager tests | Interface verification report |
| 13e | se-verifier | Verify IF-DS-INT-006 | CanvasEditor ↔ TraceabilityConnector tests | Interface verification report |
| 13f | se-verifier | Verify IF-DS-INT-007 | MermaidLiveRenderer ↔ DiagramManager tests | Interface verification report |
| 13g | se-verifier | Verify IF-DS-INT-008 | MermaidLiveRenderer ↔ DiagramRenderer tests | Interface verification report |
| 13h | se-verifier | Verify IF-DS-INT-009 | MermaidLiveRenderer ↔ McpArtifactProvider tests | Interface verification report |
| 13i | se-test-engineer + se-verifier | Define & verify FE tests | Canvas/Mermaid UI components | FE test results |
| 13j | se-validator | Validate E2E journeys | E2E test scenarios | Validation report |
| 13k | se-verifier | Verify performance SLAs | Performance test scenarios | Performance report |

---

## 4. Traceability Matrix

| REQ-ID | Requirement | Test Coverage | Verification | Status |
|--------|-------------|---------------|-------------|--------|
| REQ-L2-DS-006 | CanvasEditor: Free-hand drawing, SVG export, Auto-Save, TraceLink, MCP | TC-CNV-001..015, IT-CNV-01..03, TC-FE-CNV-001..006, E2E-CNV-01..02, TC-PERF-CNV-001..04 | 39 CanvasEditor tests | ASSIGNED |
| REQ-L2-DS-007 | MermaidLiveRenderer: 5 types, syntax errors, fallback, render hints, MCP | TC-MRM-001..017, IT-MRM-01..04, TC-FE-MRM-001..005, E2E-MRM-01..03, TC-PERF-MRM-001..04 | 34 MermaidLiveRenderer tests | ASSIGNED |

### Interface Traceability

| Interface | Source | Target | Integration Test | Status |
|-----------|--------|--------|-----------------|--------|
| IF-DS-INT-004 | COMP-DS-006 | COMP-DS-002 | IT-CNV-01, IT-MRM-01 | ASSIGNED |
| IF-DS-INT-005 | COMP-DS-006 | COMP-DS-001 | IT-CNV-02 | ASSIGNED |
| IF-DS-INT-006 | COMP-DS-006 | COMP-DS-004 | IT-CNV-03 | ASSIGNED |
| IF-DS-INT-007 | COMP-DS-007 | COMP-DS-001 | IT-MRM-02 | ASSIGNED |
| IF-DS-INT-008 | COMP-DS-007 | COMP-DS-003 | IT-MRM-03 | ASSIGNED |
| IF-DS-INT-009 | COMP-DS-007 | COMP-DS-005 | IT-MRM-04 | ASSIGNED |

---

## 5. Gate G13 Assessment

### Entry Criteria (pre-check)

| Criterion | Required | Actual | Status |
|-----------|----------|--------|--------|
| Steps 1, 6, 10, 12 completed | ✅ | ✅ Integration strategy confirmed | ✅ PASSED |
| DiagramService (COMP-DS-001..005) verified | ✅ | ✅ Legacy components operational | ✅ PASSED |
| CanvasEditor (COMP-DS-006) implemented | ✅ | ✅ 39 tests (test_canvas_editor.py) | ✅ PASSED |
| MermaidLiveRenderer (COMP-DS-007) implemented | ✅ | ✅ 34 tests (test_mermaid_live_renderer.py) | ✅ PASSED |
| All 6 new interfaces defined (IF-DS-INT-004..009) | ✅ | ✅ Test strategy §2.11 defines IF specs | ✅ PASSED |
| Test data fixtures available | ✅ | ✅ conftest.py: VALID_CANVAS_STROKES, VALID_MERMAID_* | ✅ PASSED |

### Exit Criteria (post-verification target)

| Criterion | Target | Verification |
|-----------|--------|-------------|
| Canvas-Stroke-Daten versioniert persistierbar | ✅ | CanvasEditor persistence + DiagramManager versioning |
| Auto-Save ≤5s | ✅ | Auto-Save timer configurable; persistence tested |
| ≥30fps bei 500 Strokes+100 Shapes | ✅ | TC-PERF-CNV-002 |
| Mermaid 5 Typen valide/invalide | ✅ | TC-MRM-001..005 (valid), TC-MRM-006 (invalid line number) |
| Syntax-Fehler mit Zeilennummer | ✅ | TC-MRM-006 |
| Live-Preview <2s bei 100 Knoten | ✅ | TC-PERF-MRM-003 |
| Fallback bei Renderer-Ausfall | ✅ | TC-MRM-009, test_fallback_on_renderer_exception |
| TraceLink 'documents' für beide Typen | ✅ | TC-CNV-011, TC-MRM-014, test_traceability_connector.py |
| MCP artifact.get für Canvas+Mermaid | ✅ | TC-CNV-012, TC-MRM-015, test_mcp_artifact_provider.py |
| Verbinder folgt verschobenen Formen | ✅ | TC-CNV-010 |

### Risk Assessment

| Risk ID | Risk | Likelihood | Impact | Mitigation |
|---------|------|-----------|--------|-----------|
| R-09 | Canvas-Performance < 30fps bei 500 Strokes | MEDIUM | MEDIUM | TC-PERF-CNV-001..004 in implementation; requestAnimationFrame monitoring |
| R-10 | Mermaid-Live-Preview > 2s bei 100 Knoten | MEDIUM | MEDIUM | TC-PERF-MRM-001..004; render time monitoring |
| R-11 | Verbinder-Assoziation bricht bei Form-Verschiebung | LOW | MEDIUM | TC-CNV-010 implemented |
| R-12 | Mermaid-Syntax-Validator erkennt Fehler nicht | LOW | LOW | Expanded test coverage for 5 types; edge case matrix |

---

## 6. Next Steps

1. **Immediate:** Delegate Steps 13a-13b to `se-verifier` for isolated verification
2. **Sequential:** After 13a-13b pass → delegate 13c-13h (interface verification)
3. **Cumulative:** After all component/integration steps pass → 13i (FE), 13j (E2E), 13k (Perf)
4. **Gate G13:** All sub-steps must pass before declaring G13: PASSED
5. **Eskalationspfad:**
   - Unit/Component failures → `developer` (component fix)
   - Interface contract violations → `se-architect` (interface review)
   - E2E validation failures → `se-requirements` (stakeholder need clarification)
   - Performance SLA violations → `se-architect` (architecture optimization)
