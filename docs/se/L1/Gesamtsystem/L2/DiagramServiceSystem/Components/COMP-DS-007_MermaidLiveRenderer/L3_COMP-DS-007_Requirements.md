# L3 MermaidLiveRenderer Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-DS-007 — MermaidLiveRenderer
> **Parent-System:** DiagramServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Der MermaidLiveRenderer ist verantwortlich für die clientseitige oder serverseitige Generierung von SVG/PNG Bildern aus Mermaid-Code-Blöcken. Er stellt sicher, dass Syntax-Fehler vor dem Rendern abgefangen werden.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-DS-007 | Native Mermaid Live-Preview |

## Interne Schnittstellen

| ID | Richtung | Gegenstelle | Vertrag |
|----|----------|-------------|---------|
| IF-DS-INT-005 | eingehend | COMP-DS-001 DiagramManager | `render_mermaid(mermaid_code) -> svg_string` |

## Externe Schnittstellen

| ID | Richtung | Gegenstelle | Vertrag |
|----|----------|-------------|---------|
| IF-DS-EXT-IN-003 | eingehend | Frontend-Client | Websocket oder Polling für Live-Updates |

---

## L3 Komponenten-Anforderungen

### REQ-L3-DS007-001: Live-Preview Rendering

Der MermaidLiveRenderer MUSS Mermaid-Code in Echtzeit (Latenz < 500ms) parsen und als SVG zurückgeben können. Syntax-Fehler MÜSSEN als strukturierte Fehlermeldungen (Zeilennummer, Fehlerbeschreibung) zurückgegeben werden, anstatt als roher Stacktrace.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Gültiger Code erzeugt ein valides SVG-Dokument.
- [ ] Ungültiger Code (z.B. `flowchart XX`) erzeugt eine strukturierte Fehlermeldung.
- [ ] Rendering erfolgt sicher (kein XSS durch injiziertes SVG).

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-07-12*
