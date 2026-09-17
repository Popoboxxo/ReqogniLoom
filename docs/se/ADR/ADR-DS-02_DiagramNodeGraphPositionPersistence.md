# ADR-DS-02: Node Graph Diagram Position Persistence & SVG Rendering Policy

**Status:** ACCEPTED  
**Datum:** 2026-08-07  
**Entscheider:** Developer (Task 10) based on Tasks 1-9 implementation  
**Betroffene REQs:** REQ-L1-100, REQ-L1-101, REQ-L1-027  
**Übergeordneter Need:** GH-353 (Node Graph Diagram Implementation)

---

## Kontext

GitHub-Issue #353 fordert ein strukturiertes Node-Graph-Diagrammformat (unabhängig vom freien Canvas-Format) mit Verknüpfung zu Anforderungen/Architektur via `artifact_ref` und automatischer DIAGRAM_REF TraceLink-Erstellung (Reconciliation). Während der Implementierung (Tasks 1-9) wurden zwei kritische Designentscheidungen getroffen, die vom WorkflowEditor-Muster abweichen und daher dokumentierungswürdig sind.

---

## Entscheidungsalternativen

### A. Position Persistence: localStorage vs. Payload

#### Option A1: localStorage (WorkflowEditor-Muster)
**Beschreibung:** Node/Edge-Positionen werden im Browser-localStorage gespeichert und sind rein transiente Editor-Zustandsverwaltung (nicht Teil des persistierten Diagramm-Inhalts). Jede Position-Änderung ist sofort sichtbar; Speichern zum Backend erfolgt nur explizit und nur für redaktionelle Inhalte (Labels, Kanten-Typen).

**Vorteile:**
- Minimale Netzwerk-Kommunikation: nur Inhalts-Änderungen gehen an Backend
- UI-responsiv: Drag-Operationen aktualisieren sofort localStorage, kein API-Latency-Ruckeln
- Skaliert gut bei großen Diagrammen (Positionen nicht ständig serialisiert)

**Nachteile:**
- Positionen gehen verloren bei Browser-Restart (localStorage ist nicht persistent über Sitzungen)
- Nicht teilbar: Zwei Nutzer sehen unterschiedliche Layouts (A hat localStorage-Positionen, B hat frische Defaults)
- Inkonsistenz-Risiko: Wenn Backend eine Export-Dienstleistung braucht (SVG, PNG), welche Positionen nutzen? Backend hat sie nicht.

**Risiko:** MITTEL — UI-Flexibilität, aber Kollaborations- und Persistenzverlust-Probleme

---

#### Option A2: Payload (EMPFOHLEN — implementiert in Task 8)
**Beschreibung:** Node/Edge-Positionen (`x`, `y`) sind Teil der JSON-Payload (`NodeGraphPayload`), die zum Backend transportiert wird. Jede Position-Änderung (Drag, Auto-Layout) wird als vollständige neue Payload zum Backend gesendet und persistent gespeichert. Frontend liest Positionen aus Payload, nicht aus localStorage.

**Vorteile:**
- Persistenz über Sitzungen hinweg: Positionen überleben Browser-Restart
- Team-Sharing: Alle Nutzer sehen das gleiche Diagramm-Layout
- Backend-Konsistenz: Server kennt exakt die Positionen, kann sie für Exports nutzen
- Trennung der Concerns: Editor-Zustand (Selection, Zoom-Level) vs. Diagram-Inhalt (Nodes, Edges, Positionen)
- API-Konsistenz: vollständiger `content` JSON beinhaltet alles, was zum Rendering nötig ist

**Nachteile:**
- Netzwerk-Kommunikation erhöht sich (jeder Position-Change triggert Payload-Serialisierung + API-Call)
- Payload wird größer (1000 Nodes mit Positionen → ~100 KB statt ~10 KB bei reiner Struktur)
- Potenzielle Speicher-Probleme wenn Positionen lokal gepuffert und komprimiert werden müssen

**Risiko:** NIEDRIG — Standard-Ansatz in modernen Diagram-Editoren (Figma, Miro), bewährtes Pattern

---

### B. SVG-Rendering-Lage: Server-Side Read Path vs. Explicit Export

#### Option B1: Server-Side Rendering auf Read-Path
**Beschreibung:** Jedes Mal, wenn ein Benutzer ein `node_graph` Diagramm in der Web-UI öffnet, rendert der Backend einen SVG-String und sendet ihn mit. Frontend zeigt den SVG an. Export via API ist identisch.

**Vorteile:**
- Single Source of Truth für Rendering-Logik (nur Backend)
- Konsistenz: alle Clients sehen identisch gerenderten SVG
- Leichter zu cachen (SVG pre-render, ggf. im CDN)

**Nachteile:**
- Höhere Backend-Last bei häufigen Diagramm-Ansichten (jeder Read-Request triggert SVG-Rendering)
- Latency: SVG-Rendering (Layout-Berechnung, Shape-Transformation) verzögert die Antwort
- Nicht modifizierbar im UI ohne erneutes Backend-Rendering: Frontend muss Positionen ändern, aber kann kein neues SVG generieren bis zum nächsten Save
- Abhängigkeit: Backend muss SVG-Rendering-Bibliothek (reportlab, WeasyPrint, etc.) laden — adds dependency, adds risk

**Risiko:** MITTEL — Performance-Impact auf Read-Path, Abhängigkeits-Overhead

---

#### Option B2: Client-Side Rendering (React Flow) + Explicit Export (EMPFOHLEN — implementiert in Tasks 6, 8)
**Beschreibung:** Browser rendert Diagramm via React Flow-Canvas (WebGL/Canvas2D). Benutzer bearbeitet interaktiv. Explizites Export (Button "Download SVG") triggert einen Backend-API-Call (`POST /diagrams/{id}/export?format=svg`), der gezielt einen SVG rendert. Read-Path benötigt **kein** Backend-SVG-Rendering.

**Vorteile:**
- Gering Backend-Last für Read-Operationen (nur JSON-Payload senden)
- Schnelle UI-Responses: Browser rendert Canvas-basiert (GPU-optimiert)
- Einfache interaktive Bearbeitung ohne Backend-Trips für Layout-Changes
- Export ist high-value Operation: Rendering-Overhead ist akzeptabel beim Benutzer-Trigger (nicht bei jedem View)
- Flexibilität: Frontend kann Layout ändern, ohne Backend zu fragen

**Nachteile:**
- Zwei Rendering-Implementierungen: React Flow (Frontend) + SVG-Exporter (Backend) — Konsistenz-Risiko wenn Backends unterschiedlich aussehen
- Client-abhängig: JavaScript-fähiger Browser nötig; mobil/alt-Browser haben Probleme
- Caching schwerer: SVG ist dynamisch generiert, nicht statisch cachebar

**Risiko:** NIEDRIG — Standard-Muster in modernen web apps (VS Code, Figma, Excalidraw); SVG-Export ist On-Demand-High-Value-Feature

---

## Entscheidung

### Decision 1: Option A2 (Positionen im Payload) — AKZEPTIERT

**Implementiert in Task 8:** `useGraphPayload.ts` flowToPayload() persistiert alle Node-Positionen im JSON-Payload.

**Begründung:**
1. Persistenz und Kollaborations-Anforderung (REQ-L1-100: "System muss Diagramme speichern")
2. Backend-Konsistenz: POST `/export` Endpunkt braucht Positionen für SVG-Rendering
3. Zukunftssicherheit: Falls Offline-Fähigkeit oder Team-Sync-Features später gewünscht werden, sind Positionen im Payload bereits verfügbar
4. Einfacher als localStorage-Sync + Conflict-Resolution

**Konsequenzen:**
- JSON-Payload wird leicht größer (10–20% mehr bytes für typische Diagramme)
- Jede Position-Change triggert Network-Request (kein lokales Debounce möglich)
- Garantierte Konsistenz zwischen UI und Backend

---

### Decision 2: Option B2 (Client-Side Canvas Rendering + Explicit Export) — AKZEPTIERT

**Implementiert in Tasks 6 & 8:**
- Task 6 (Backend): `POST /diagrams/{id}/export` Endpoint mit SVG-Rendering
- Task 8 (Frontend): React Flow Canvas-Renderer für Preview; kein SVG in normaler Ansicht

**Begründung:**
1. Performance: Read-Path (Diagramm-Ansicht) sendet nur JSON, rendert Client-seitig
2. Backend-Entlastung: SVG-Rendering nur bei explizitem Export (high-value Operation)
3. Geschwindigkeit: Canvas-Rendering (WebGL/2D) schneller als Server-SVG-Rendering + Netzwerk-Transfer
4. Cluster-Skalierung: keine zentrale SVG-Rendering-Last auf Backend (stateless skalierbar)

**Konsequenzen:**
- SVG und Canvas können optisch leicht divergieren (abhängig von React Flow + Backend SVG-Renderer-Unterschieden)
  → Mitigated by: Explizite Cross-Test (E2E Canvas vs. Export-SVG)
- Mobile/JS-unfähige Clients bekommen nur Fallback oder müssen Export nutzen
  → Akzeptabel: moderne Team-Anforderung (React Flow)

---

## Auswirkungen

### Architektur-Ebene
- **Frontend:** `DiagramGraphEditor` muss flowToPayload() nutzen, alle Position-Changes ins Payload schreiben
- **Backend:** `DiagramService.create/update` akzeptiert Positionen in node_graph Payload als legit
- **Export:** `DiagramExporter` (backend/diagram/node_graph_renderer.py) rendert SVG aus Payload-Positionen

### Datenmodell
- `DiagramVersion.payload` JSON-Schema beinhaltet position-Array für alle Nodes (nicht optional)
- Migration: Bestehende canvas_stroke Diagramme behalten ihr Format (kein Auto-Upgrade zu node_graph)

### Testing
- **Frontend:** useGraphPayload.test.ts prüft flowToPayload() Serialisierung + Position-Persistenz
- **Backend:** test_node_graph_renderer.py prüft SVG-Output-Konsistenz
- **E2E:** Playwright-Test: Benutzer ändert Position, speichert, ladet Browser neu → Position ist erhalten

### Zukünftige Erweiterungen
- Falls Offline-Support nötig: Payload-Positionen sind bereits vorhanden (localStorage Sync nur für Editor-Transient-State wie Selection)
- Falls Multiplayer-Collaboration: Positionen sind im Payload, können via CRDTs synchonisiert werden
- Falls 3D-Diagramme: Payload kann um z-Coordinate erweitert werden (backwards-compatible)

---

## Verwandte ADRs & Decisions

- **ADR-DS-01 (künftig):** Pure-Funktions-Boundary für node_graph.py (keine DB-Imports)
- **REQ-L1-100:** Node Graph Payload Format Spezifikation
- **REQ-L1-101:** DIAGRAM_REF TraceLink Type (Reconciler-owned)

---

## Review Checklist

- [x] Beide Entscheidungen sind implementiert (Tasks 1-9 verifiziert)
- [x] Konsequenzen sind in Arch-Impact dokumentiert
- [x] Performance-Auswirkungen sind akzeptabel (Payload < 1 MB, Export on-demand)
- [x] Zukünftige Erweiterungen sind möglich (kein Lock-in)
- [x] Testing-Plan vorhanden (Payload-Serialisierung, SVG-Render-Konsistenz)

---

*Erstellt: 2026-08-07 | Autor: Developer (Task 10) | Basis: Tasks 1-9 Implementierung | GitHub #353*
