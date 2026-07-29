decomposition_status: terminal

# L3 CanvasEditor Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-DS-006 — CanvasEditor
> **Parent-System:** DiagramServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Der CanvasEditor ermöglicht die freie, grafische Positionierung von Diagramm-Elementen. Im Gegensatz zu Mermaid-Diagrammen, die automatisch layouten, bietet der CanvasEditor absolute Kontrolle über Koordinaten (x, y, width, height) und visuelle Eigenschaften. Die Datenstruktur wird als JSON gespeichert und persistiert.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-DS-008 | Freies Canvas-Layout |
| REQ-L2-DS-009 | Canvas Node-Typen (Rechteck, Ellipse, Text-Label) |
| REQ-L2-DS-010 | Canvas Edge-Typen (Verbindungslinien) |
| REQ-L2-DS-011 | Canvas JSON-Serialisierung |
| REQ-L2-DS-012 | Migration: Mermaid zu Canvas |

## Interne Schnittstellen

| ID | Richtung | Gegenstelle | Vertrag |
|----|----------|-------------|---------|
| IF-DS-INT-004 | ausgehend | COMP-DS-001 DiagramManager | `save_canvas_json(diagram_id, json_data)` |

## Externe Schnittstellen

| ID | Richtung | Gegenstelle | Vertrag |
|----|----------|-------------|---------|
| IF-DS-EXT-IN-002 | eingehend | ApplicationService | REST API für Canvas-Updates |

---

## L3 Komponenten-Anforderungen

### REQ-L3-DS006-001: JSON-Datenmodell für Canvas

Der CanvasEditor MUSS Diagramme im JSON-Format serialisieren und verarbeiten. Das JSON MUSS Arrays für `nodes` und `edges` beinhalten. Nodes MÜSSEN `id`, `type`, `x`, `y`, `width`, `height` und `label` enthalten. Edges MÜSSEN `id`, `source`, `target` und `type` enthalten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] JSON-Schema Validierung schlägt fehl, wenn `x` oder `y` fehlen.
- [ ] DiagramManager speichert das JSON nativ in der Datenbank (JSONField).

---

### REQ-L3-DS006-002: Unterstützte Node- und Edge-Typen

Der CanvasEditor MUSS mindestens folgende Typen unterstützen:
- Nodes: `rectangle`, `ellipse`, `text`
- Edges: `solid`, `dashed`, `dotted` (optional mit Pfeilspitzen)

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ein Node vom Typ `triangle` wird vom Schema abgelehnt.
- [ ] Ein Edge kann optional ein Label haben.

---

### REQ-L3-DS006-003: Migration von Mermaid zu Canvas

Der CanvasEditor MUSS eine Konvertierungsfunktion bereitstellen, die ein bestehendes Mermaid-Diagramm (`flowchart` oder `classDiagram`) parst, die Knoten und Kanten extrahiert und ein initiales Canvas-JSON mit auto-generierten Koordinaten (z.B. Dagre-Layout) erzeugt.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Konvertierung erzeugt gültiges Canvas-JSON.
- [ ] Die topologische Struktur des ursprünglichen Mermaid-Diagramms bleibt erhalten.

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-07-12*

---

### REQ-L3-DS006-004: L3 Context Generators Implementation

Derives from REQ-L2-DIA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-DS006-005: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-DIA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
