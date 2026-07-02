# L1 End-to-End Validation Report — Canvas & Mermaid Capabilities

> **Validation ID:** VAL-002  
> **System Level:** L1 (Black-Box, User-Perspective)  
> **Datum:** 2026-06-30  
> **Validator:** se-validator-Agent  
> **Quellen:** REQ-L0-036, REQ-L0-037, REQ-L1-056, REQ-L1-057, COMP-DS-006, COMP-DS-007  
> **Verdict:** BLOCKED

---

## 1. Executive Summary

Die implementierten Canvas- und Mermaid-Capabilities liegen ausschließlich als **Backend-Komponenten** vor (COMP-DS-006, COMP-DS-007). Es existiert **kein Frontend** (keine React-Komponenten, keine API-Endpoints in views.py/urls.py), das die User-Journeys ermöglicht. Aus Stakeholder-Perspektive sind beide Needs damit **nicht erfüllt** — der User kann weder eine Canvas-Zeichenfläche öffnen noch einen Mermaid-Editor mit Live-Preview nutzen.

Die Backend-Implementierung ist solide (73 Tests, saubere Interface-Contracts, korrekte Persistenz), aber ohne Frontend-Integration und REST-Endpoints sind die User-Journeys nicht durchführbar.

---

## 2. User Journey Simulationen

### Journey 1 — Canvas zeichnen, speichern, verknüpfen (REQ-L0-036)

| Step | Erwartete Aktion | System-Status | Ergebnis |
|------|------------------|---------------|----------|
| 1. User öffnet Canvas-Zeichenfläche | ReactFrontend rendert Canvas-Editor | ❌ **Keine React-Komponente** vorhanden | BLOCKED |
| 2. User zeichnet mit Pen-Tool, fügt Formen hinzu | Canvas rendert drawing tools (pen, rect, circle, line, text, arrow) | ❌ **Keine Drawing-Tools** im Frontend | BLOCKED |
| 3. User verschiebt Form → Verbinder folgt (AC3) | Frontend recalculates connector coordinates | ❌ **Keine Connector-Dynamic** implementiert | BLOCKED |
| 4. User speichert → Diagramm versioniert, TraceLink erstellt | `POST /api/v1/diagrams/{id}/canvas-strokes` | ❌ **Kein REST-Endpoint** in views.py/urls.py | BLOCKED |
| 5. User exportiert als SVG (AC7) | Download SVG file | ⚠️ Backend `export_svg()` funktioniert, aber kein Download-Endpoint | PARTIAL |
| 6. User ruft via MCP ab (AC6) | `artifact.get` returns canvas payload | ⚠️ McpArtifactProvider unterstützt DiagramType.CANVAS implizit, kein expliziter Test | PARTIAL |

**System Coverage:** NOT FULFILLED  
**Gaps:** Kein Frontend, keine REST-Endpoints, keine Drawing-Tools, keine Connector-Dynamic, kein Auto-Save-Timer

---

### Journey 2 — Mermaid-Code eingeben, Live-Preview, exportieren (REQ-L0-037)

| Step | Erwartete Aktion | System-Status | Ergebnis |
|------|------------------|---------------|----------|
| 1. User öffnet Mermaid-Editor | ReactFrontend rendert Mermaid-Editor-Komponente | ❌ **Keine React-Komponente** vorhanden | BLOCKED |
| 2. User gibt `flowchart LR; A-->B;` ein → Live-Preview (AC1) | 500ms Debounce + mermaid.js Rendering | ❌ **Kein Live-Preview** implementiert | BLOCKED |
| 3. User wechselt zu `sequenceDiagram` → Preview aktualisiert (AC3) | Frontend re-renders on type change | ❌ **Kein Frontend** | BLOCKED |
| 4. User macht Syntax-Fehler → Fehlermeldung + Fossil (AC7) | UI shows error with line number; last valid render stays | ⚠️ Backend `ValidationResult` hat `line_number`, aber **keine UI-Anzeige**; kein Fossil-Mechanismus | PARTIAL |
| 5. User exportiert als SVG (AC5) | Download SVG/PNG file | ❌ **Kein Export-Endpoint**, kein serverseitiger SVG/PNG-Export für Mermaid | BLOCKED |
| 6. User verknüpft mit Requirement (AC6) | TraceLink creation via UI or API | ⚠️ Backend TraceabilityConnector existiert, aber **kein REST-Endpoint** für Mermaid-TraceLinks | PARTIAL |

**System Coverage:** NOT FULFILLED  
**Gaps:** Kein Frontend, keine REST-Endpoints, kein Live-Preview, kein Zoom, kein Export, keine Fehleranzeige, kein Fossil

---

## 3. AC-Coverage-Matrix

### REQ-L0-036 — Free-Hand Canvas Drawing (9 ACs)

| AC | Beschreibung | Backend | Frontend | API | E2E | Status |
|----|--------------|---------|----------|-----|-----|--------|
| AC1 | Canvas unterstützt Pen/Stift, Rechteck, Kreis, Linie, Text-Notiz, Pfeil/Verbinder | ✅ 7 Element-Typen im Datenmodell | ❌ Keine Drawing-Tools | ❌ Kein Endpoint | ❌ | **NOT FULFILLED** |
| AC2 | Elemente nachträglich auswählbar, verschiebbar, skalierbar, löschbar | ❌ N/A (Frontend-Aufgabe) | ❌ Keine Interaktion | ❌ | ❌ | **NOT FULFILLED** |
| AC3 | Verbinder bleiben assoziiert (folgen Formen) | ⚠️ SVG-Export rendert statische Koordinaten | ❌ Keine Connector-Dynamic | ❌ | ❌ | **NOT FULFILLED** |
| AC4 | JSON-Stroke-Daten persistiert (Primärformat) | ✅ `handle_stroke_update()` + `PayloadFormat.CANVAS_STROKE` | — | ❌ Kein Endpoint | ⚠️ DB-Tests | **PARTIAL** |
| AC5 | TraceLink (Typ `documents`) mit Requirements, ArchitectureElements, TestCases | ✅ `link_canvas_to_artifact()` | ❌ Keine UI | ❌ Kein Endpoint | ⚠️ Mock-Test | **PARTIAL** |
| AC6 | Canvas-Diagramme via MCP (artifact.get) abrufbar | ⚠️ Implizit via McpArtifactProvider (DiagramType.CANVAS) | — | — | ❌ Kein expliziter Test | **PARTIAL** |
| AC7 | Export als SVG/PNG möglich | ⚠️ SVG ✅ (`export_svg()`), PNG ❌ (NotImplementedError) | ❌ Kein Download | ❌ Kein Endpoint | ⚠️ SVG-Tests | **PARTIAL** |
| AC8 | Auto-Save max 5s — max 5s Datenverlust | ⚠️ Backend-Persistenzpfad getestet, aber **kein Frontend-Timer** | ❌ Kein Auto-Save-Timer | ❌ | ⚠️ DB-Tests | **PARTIAL** |
| AC9 | ≥30fps bei 500 Stroke-Elementen + 100 Formen | ❌ Nicht gemessen (clientseitiges Rendering) | ❌ Kein Rendering | — | ❌ | **NOT FULFILLED** |

**REQ-L0-036 Gesamt:** PARTIAL — Backend-Datenmodell und Persistenz sind solide, aber ohne Frontend, API-Endpoints und Performance-Messung sind 4 von 9 ACs nicht erfüllt.

---

### REQ-L0-037 — Mermaid Live Preview (10 ACs)

| AC | Beschreibung | Backend | Frontend | API | E2E | Status |
|----|--------------|---------|----------|-----|-----|--------|
| AC1 | Mermaid-Editor mit Live-Preview (500ms Debounce) | ❌ N/A (Frontend-Aufgabe) | ❌ Kein Editor, kein Preview | ❌ | ❌ | **NOT FULFILLED** |
| AC2 | Mermaid-Quellcode als versioniertes Artefakt persistiert | ✅ `handle_source_update()` via DiagramManager | — | ❌ Kein Endpoint | ⚠️ Mock-Test | **PARTIAL** |
| AC3 | 5 Mermaid-Typen unterstützt | ✅ flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram | ❌ Kein Rendering | — | ✅ 5 Type-Tests | **PARTIAL** |
| AC4 | Gerendertes Diagramm ist zoombar | ❌ N/A (Frontend-Aufgabe) | ❌ Kein Zoom | — | ❌ | **NOT FULFILLED** |
| AC5 | Export als PNG und SVG | ❌ Kein serverseitiger Export (renderer.py Stubs) | ❌ Kein Frontend-Export | ❌ | ❌ | **NOT FULFILLED** |
| AC6 | TraceLink (Typ `documents`) verknüpfbar | ⚠️ TraceabilityConnector existiert, aber kein dedizierter Mermaid-TraceLink-Test | ❌ Keine UI | ❌ | ❌ | **PARTIAL** |
| AC7 | Syntaxfehler: Fehlermeldung mit Zeilennummer + Fossil | ⚠️ `ValidationResult.line_number` ✅, aber **kein Fossil-Mechanismus** | ❌ Keine Fehleranzeige | — | ⚠️ Validator-Tests | **PARTIAL** |
| AC8 | Via MCP (artifact.get) abrufbar | ⚠️ Implizit via McpArtifactProvider (DiagramType.MERMAID) | — | — | ❌ Kein expliziter Test | **PARTIAL** |
| AC9 | Fallback bei Renderer-Ausfall | ✅ `LivePreviewData.fallback_mode=True` + `error_message` | ❌ Keine Fallback-UI | — | ✅ 2 Fallback-Tests | **PARTIAL** |
| AC10 | Live-Rendering <2s bei 100 Knoten/Kanten | ❌ Nicht gemessen (clientseitiges Rendering) | ❌ Kein Rendering | — | ❌ | **NOT FULFILLED** |

**REQ-L0-037 Gesamt:** PARTIAL — Backend-Validierung, Persistenz und Fallback sind implementiert, aber ohne Frontend, API-Endpoints, Export und Performance-Messung sind 4 von 10 ACs nicht erfüllt.

---

## 4. Test-Coverage-Analyse

### Vorhandene Tests

| Komponente | Test-Datei | Tests | Coverage |
|-----------|-----------|-------|----------|
| CanvasEditor | `test_canvas_editor.py` | 39 (27 non-DB + 12 DB) | Validierung, Auto-Save, SVG-Export, TraceLink, Retrieval |
| MermaidLiveRenderer | `test_mermaid_live_renderer.py` | 23 | Type-Validierung, Source-Update, Render-Hints, Fallback, MCP, Type-Detection |
| Validator (canvas) | `test_validator.py` | 12 | `validate_mermaid_source()` für 5 Typen + Fehlerfälle |
| Renderer (hints) | `test_renderer.py` | 4 | `get_render_hints()` |
| **Gesamt** | | **78 neue Tests** | |

### Fehlende Test-Coverage

| Gap | Beschreibung | Schwere |
|-----|--------------|---------|
| Keine REST-Endpoint-Tests | Keine `APITestCase` oder `pytest-django` Tests für `POST /canvas-strokes` oder `PUT /mermaid-source` | HIGH |
| Keine Frontend-Tests | Keine Vitest/RTL-Tests für Canvas-Editor oder Mermaid-Editor React-Komponenten | HIGH |
| Keine E2E-Tests | Keine Playwright/Cypress-Tests für die vollständigen User-Journeys | HIGH |
| Kein MCP-Test für Canvas/Mermaid | McpArtifactProvider wurde nicht mit `DiagramType.CANVAS` oder `DiagramType.MERMAID` getestet | MEDIUM |
| Keine Performance-Tests | ≥30fps (Canvas) und <2s (Mermaid) nicht gemessen | MEDIUM |
| Kein TraceLink-Test für Mermaid | Expliziter TraceLink-Test für Mermaid-Diagramme fehlt | LOW |

---

## 5. Abgleich mit Stakeholder-Bedürfnissen

| Need | Priorität | User-Journey | Status | Blocking |
|------|-----------|--------------|--------|----------|
| REQ-L0-036: Free-Hand Canvas Drawing | desired | Journey 1 | **NOT FULFILLED** | **YES** — Kein Einstiegspunkt für kritische Journey |
| REQ-L0-037: Mermaid Live Preview | desired | Journey 2 | **NOT FULFILLED** | **YES** — Kein Einstiegspunkt für kritische Journey |

**Begründung BLOCKED:**
- Beide Needs haben **keinen System-Einstiegspunkt** für den End-User (kein Frontend, keine API-Endpoints).
- Die User-Journeys sind von Schritt 1 an blockiert — der User kann weder eine Canvas-Zeichenfläche noch einen Mermaid-Editor öffnen.
- Die Backend-Implementierung ist notwendig, aber nicht hinreichend — ohne Frontend-Integration ist der Stakeholder-Need nicht erfüllt.

---

## 6. Blocking Criteria

| Criterion | Severity | Status |
|-----------|----------|--------|
| Must-Have stakeholder need unfulfilled | BLOCK | ⚠️ Beide Needs sind `desired` (Should-Have), nicht Must-Have — dennoch: kein Einstiegspunkt |
| Critical journey has no system entry point | BLOCK | ✅ **ZUTREFFEND** — Journey 1 und 2 haben keinen Einstiegspunkt (kein Frontend, keine REST-Endpoints) |
| System contradicts stakeholder constraint | BLOCK | Nein |
| Safety/security need missing at L1 | BLOCK | Nein |

**Decision:** Obwohl beide Needs als `desired` (Should-Have) klassifiziert sind, ist die **kritische Journey ohne Einstiegspunkt** ein Blocking-Kriterium. Der User kann die implementierten Backend-Capabilities nicht nutzen.

---

## 7. Warnings (Non-Blocking)

| # | Issue | Need | Empfehlung |
|---|-------|------|------------|
| W-01 | PNG-Export ist clientseitiger Stub (beide Components) | REQ-L0-036 AC7, REQ-L0-037 AC5 | Für v1 akzeptabel (ADR-DS-04). v2: headless Chromium für serverseitigen PNG-Export. |
| W-02 | MCP-Registrierung für Mermaid ist no-op in v1 | REQ-L0-037 AC8 | Funktionalität implizit gegeben (McpArtifactProvider unterstützt alle DiagramTypes). Expliziten Test hinzufügen. |
| W-03 | Performance-Budget (≥30fps / <2s) nicht validiert | REQ-L0-036 AC9, REQ-L0-037 AC10 | Nach Frontend-Integration: Performance-Benchmarks mit 500 Strokes / 100 Knoten durchführen. |
| W-04 | Fossil-Mechanismus (REQ-L0-037 AC7) nicht implementiert | REQ-L0-037 AC7 | Backend liefert `line_number`, aber kein Fossil (last valid render). Frontend muss Fossil-Logik implementieren. |
| W-05 | Connector-Dynamic (REQ-L0-036 AC3) nicht implementiert | REQ-L0-036 AC3 | Backend speichert statische Koordinaten. Frontend muss Connector-Neuberechnung bei Form-Verschiebung implementieren. |

---

## 8. Over-Engineering

Kein Over-Engineering festgestellt. Die Backend-Komponenten sind minimal und fokussiert auf die spezifizierten Interfaces.

---

## 9. JSON Validation Report

```json
{
  "validation_id": "VAL-002",
  "system_level": "L1",
  "stakeholder_needs_reviewed": [
    {
      "need_id": "REQ-L0-036",
      "need_text": "Teams müssen Diagramme innerhalb von ReqFlow frei auf einer Zeichenfläche (Canvas) erstellen können, ohne auf externe Zeichenprogramme ausweichen zu müssen.",
      "user_journeys": [
        {
          "journey_name": "Canvas zeichnen, speichern, verknüpfen",
          "actor": "Software Engineer / Systems Engineer",
          "trigger": "User öffnet Canvas-Zeichenfläche im Workspace",
          "steps": [
            "User öffnet Canvas-Zeichenfläche im Workspace",
            "User zeichnet mit Pen-Tool, fügt Rechteck, Text-Notiz und Pfeil hinzu",
            "User verschiebt eine Form → Verbinder folgt (AC3)",
            "User speichert → Diagramm wird versioniert, TraceLink erstellt",
            "User exportiert als SVG (AC7)",
            "User ruft via MCP ab (AC6)"
          ],
          "expected_outcome": "Canvas-Diagramm erstellt, versioniert, verknüpft und exportierbar",
          "acceptance_signal": "Canvas-Editor sichtbar; Drawing-Tools funktional; Diagramm gespeichert und exportierbar",
          "system_coverage": "Not Fulfilled",
          "gaps": [
            "Keine React-Komponente für Canvas-Editor",
            "Keine REST-Endpoints (POST /api/v1/diagrams/{id}/canvas-strokes)",
            "Keine Drawing-Tools (Pen, Shapes, Text, Arrow) im Frontend",
            "Keine Connector-Dynamic (Form verschieben → Verbinder folgt)",
            "Kein Auto-Save-Timer im Frontend (5s Intervall)",
            "Keine Performance-Validierung (≥30fps bei 500 Strokes)",
            "PNG-Export nur als clientseitiger Stub"
          ]
        }
      ],
      "overall_status": "Not Fulfilled",
      "blocking": true
    },
    {
      "need_id": "REQ-L0-037",
      "need_text": "Teams müssen Mermaid-Diagrammcode direkt in ReqFlow eingeben und das gerenderte Diagramm grafisch im Browser sehen können — mit Live-Preview während der Eingabe.",
      "user_journeys": [
        {
          "journey_name": "Mermaid-Code eingeben, Live-Preview, exportieren",
          "actor": "Software Engineer / Systems Engineer",
          "trigger": "User öffnet Mermaid-Editor",
          "steps": [
            "User öffnet Mermaid-Editor",
            "User gibt flowchart LR; A-->B; ein → Live-Preview zeigt gerendertes Diagramm (AC1)",
            "User wechselt zu sequenceDiagram → Preview aktualisiert (AC3)",
            "User macht Syntax-Fehler → Fehlermeldung + Fossil bleibt sichtbar (AC7)",
            "User exportiert als SVG (AC5)",
            "User verknüpft mit Requirement (AC6)"
          ],
          "expected_outcome": "Mermaid-Code eingegeben, Live-Preview gerendert, exportierbar und verknüpfbar",
          "acceptance_signal": "Editor + Preview sichtbar; Live-Rendering funktional; Export und TraceLink arbeiten",
          "system_coverage": "Not Fulfilled",
          "gaps": [
            "Keine React-Komponente für Mermaid-Editor",
            "Keine REST-Endpoints (PUT /api/v1/diagrams/{id}/mermaid-source)",
            "Kein Live-Preview (500ms Debounce + mermaid.js Rendering)",
            "Keine Zoom-Controls (Mausrad, Pinch, Buttons)",
            "Kein SVG/PNG-Export für Mermaid-Diagramme",
            "Keine Fehleranzeige mit Zeilennummer im UI",
            "Kein Fossil-Mechanismus (last valid render)",
            "Keine Performance-Validierung (<2s bei 100 Knoten)"
          ]
        }
      ],
      "overall_status": "Not Fulfilled",
      "blocking": true
    }
  ],
  "blocking_issues": [
    {
      "need_id": "REQ-L0-036",
      "issue": "Critical journey has no system entry point: Keine Frontend-Komponente und keine REST-Endpoints für Canvas-Drawing vorhanden.",
      "recommendation": "Frontend-Integration (React Canvas-Editor) + REST-Endpoints + Auto-Save-Timer implementieren."
    },
    {
      "need_id": "REQ-L0-037",
      "issue": "Critical journey has no system entry point: Keine Frontend-Komponente und keine REST-Endpoints für Mermaid Live-Preview vorhanden.",
      "recommendation": "Frontend-Integration (React Mermaid-Editor + Live-Preview) + REST-Endpoints + Export implementieren."
    }
  ],
  "warnings": [
    {
      "need_id": "REQ-L0-036",
      "issue": "PNG-Export ist clientseitiger Stub (NotImplementedError). Kein serverseitiger PNG-Export.",
      "recommendation": "Für v1 akzeptabel. v2: headless Chromium für serverseitigen PNG-Export."
    },
    {
      "need_id": "REQ-L0-037",
      "issue": "MCP-Registrierung für Mermaid ist no-op in v1. Kein expliziter MCP-Test für DiagramType.MERMAID.",
      "recommendation": "Expliziten MCP-Test für Canvas und Mermaid hinzufügen."
    },
    {
      "need_id": "REQ-L0-036",
      "issue": "Performance-Budget ≥30fps bei 500 Strokes nicht validiert.",
      "recommendation": "Nach Frontend-Integration: Performance-Benchmarks durchführen."
    },
    {
      "need_id": "REQ-L0-037",
      "issue": "Performance-Budget <2s bei 100 Knoten/Kanten nicht validiert.",
      "recommendation": "Nach Frontend-Integration: Performance-Benchmarks durchführen."
    },
    {
      "need_id": "REQ-L0-037",
      "issue": "Fossil-Mechanismus (last valid render bei Syntaxfehler) nicht implementiert.",
      "recommendation": "Frontend muss Fossil-Logik implementieren (last successful SVG im State halten)."
    },
    {
      "need_id": "REQ-L0-036",
      "issue": "Connector-Dynamic (Verbinder folgen Formen) nicht implementiert.",
      "recommendation": "Frontend muss Connector-Koordinaten bei Form-Verschiebung neu berechnen."
    }
  ],
  "over_engineering": [],
  "validation_verdict": "BLOCKED",
  "rationale": "Beide Stakeholder-Needs (REQ-L0-036, REQ-L0-037) sind als kritische User-Journeys ohne System-Einstiegspunkt implementiert. Die Backend-Komponenten (COMP-DS-006, COMP-DS-007) sind solide (73 Tests, saubere Interface-Contracts), aber ohne Frontend-Integration und REST-Endpoints kann der User weder eine Canvas-Zeichenfläche öffnen noch einen Mermaid-Editor mit Live-Preview nutzen. Die User-Journeys sind von Schritt 1 an blockiert."
}
```

---

## 10. Nächste Schritte

### Empfohlene Reihenfolge für Abschluss:

1. **REST-Endpoints implementieren** (HIGH, BLOCKER):
   - `POST /api/v1/diagrams/{id}/canvas-strokes` → `canvas_auto_save()`
   - `GET /api/v1/diagrams/{id}/canvas` → `get_canvas_diagram()`
   - `PUT /api/v1/diagrams/{id}/mermaid-source` → `update_mermaid_source()`
   - `GET /api/v1/diagrams/{id}/mermaid-preview` → `get_mermaid_preview()`

2. **Frontend Canvas-Editor** (HIGH, BLOCKER):
   - React-Komponente mit Drawing-Tools (pen, rect, circle, line, text, arrow, connector)
   - Auto-Save-Timer (5s Intervall) → `POST /canvas-strokes`
   - SVG-Export-Download
   - Connector-Dynamic (Form verschieben → Verbinder folgt)

3. **Frontend Mermaid-Editor** (HIGH, BLOCKER):
   - React-Komponente mit Code-Editor + Live-Preview (mermaid.js, 500ms Debounce)
   - Zoom-Controls (Mausrad, Pinch, Buttons)
   - Fehleranzeige mit Zeilennummer + Fossil-Mechanismus
   - SVG/PNG-Export-Download

4. **MCP-Tests ergänzen** (MEDIUM):
   - Expliziter Test: `artifact.get` für `DiagramType.CANVAS`
   - Expliziter Test: `artifact.get` für `DiagramType.MERMAID`

5. **Performance-Benchmarks** (MEDIUM, nach Frontend-Integration):
   - Canvas: ≥30fps bei 500 Strokes + 100 Formen
   - Mermaid: <2s bei 100 Knoten/Kanten

---

*Erstellt durch se-validator-Agent | ReqFlow SE-Kaskade | 2026-06-30*  
*Nächster Schritt: Frontend-Integration + REST-Endpoints für Canvas und Mermaid.*
