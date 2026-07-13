# Design-Proposal: Hierarchie-Tree-View für L0-L4 Zerlegungsbaum (REQ-001)

**Status:** Design-Proposal ✓ DONE (Entwurf durch ui-ux-designer am 2026-07-03)
**REQ-ID:** REQ-001 — Hierarchie-Tree-View für Requirements/Architecture-Elemente
**Scope:** Phase 1 (MVP) = ArchitectureElements nur (L0-L4), Phase 2 (Future) = + Requirement-Links

---

## 1. Placement-Empfehlung

**Empfohlen: Neues Left-Sidebar-Panel** im Architecture-Editor / Workspace-View

**Begründung:**
- Tree ist zentral für MBSE-Workflows (Zerlegung visualisieren)
- Sollte **immer sichtbar** sein (nicht Modal/Tab, würde Context brechen)
- Sidebar-Pattern bereits etabliert in Requirements-Tool
- User arbeitet mit Detail-View (Main Content) + Baum-Überblick parallel

**Alternative (sekundär):** Linker Subpanel im Workspace, kollabierbar

---

## 2. ASCII Wireframe

```
┌────────────────────────────────────────────────────────────────────┐
│  ReqFlow — Architecture Workspace                                  │
├──────────────────┬────────────────────────────────────────────────┤
│  DECOMPOSITION   │ MAIN EDITOR                                    │
│  TREE            │                                                │
├──────────────────┤ ┌──────────────────────────────────────────┐  │
│ [Search: _____]  │ │ Selected Element: L2-SubsystemA        │  │
│                  │ │ ─────────────────────────────────────── │  │
│ L0: L0-System    │ │ ID: ARCH-003                           │  │
│ ▼ (expanded)     │ │ Type: Subsystem                        │  │
│   └─ L1: SSA     │ │ Status: Active                         │  │
│     ▼ (exp)      │ │                                         │  │
│     ├─ L2-Sub1   │ │ Parent: L1-SystemA                     │  │
│     │ └─ L3-C1   │ │ Children: [L2-SubsystemB, L3-Comp1...] │  │
│     │ └─ L3-C2   │ │                                         │  │
│     └─ L2-Sub2   │ │ [Edit] [Delete] [Add Child] [Link]     │  │
│       └─ L3-C3   │ └──────────────────────────────────────┘  │
│                  │                                              │
│ L0: L0-Other     │                                              │
│ ▶ (collapsed)    │                                              │
├──────────────────┤                                              │
│ ◯ Filters:       │                                              │
│  ☐ Show all      │                                              │
│  ☑ L0-L2 only    │                                              │
│  ☑ Active        │                                              │
└──────────────────┴────────────────────────────────────────────┘
```

---

## 3. Komponenten-Spezifikation

| Komponente | Beschreibung |
|-----------|-------------|
| **Tree-Node** | Text (Name) + Expand/Collapse-Icon (▼/▶) + Level-Indikator (L0-L4) + Context-Menu (Rechtsklick) |
| **Expand/Collapse** | Click auf ▼/▶ togglet `isExpanded` state; API ruft nur beim Expand Child-Nodes ab (lazy loading) |
| **Node-Highlighting** | Click auf Node → Main-Editor zeigt Detail-View; Selected-Node bekommt Highlight (bg-color oder border) |
| **Search** | Filter Tree nach Name/ID; Filtered-Out-Knoten werden ausgeblendet (aber Parents bleiben sichtbar) |
| **Level-Badge** | Kleine Anzeige "L2" rechts neben Node-Name (Farbe nach Level: L0=dunkelblau, L1=blau, L2=cyan, L3=grün, L4=grau) |
| **Context-Menu** | Rechtsklick: Edit / Delete / Add Child / Link-to-Requirement / Show in Detail-View |
| **Breadcrumb** | (optional) Zeigt aktuellen Pfad: L0-System > L1-SubsystemA > L2-Sub1 |

---

## 4. Interaktionen

```json
{
  "interactions": [
    {
      "action": "Click Node",
      "effect": "Main-Editor zeigt Detail-View des Elements",
      "state_change": "selected_node_id = Node.id"
    },
    {
      "action": "Click Expand-Icon (▼)",
      "effect": "Children werden angezeigt (oder versteckt bei Collapse ▶)",
      "state_change": "isExpanded[node_id] = true/false",
      "api_call": "GET /api/v1/architecture-elements/?parent_id={id} (nur beim Expand)"
    },
    {
      "action": "Double-Click Node",
      "effect": "Öffnet Modal/Editor für In-Line-Edit des Node-Names",
      "prevents": "Navigation zur Detail-View (verhindert Verwechslung mit Single-Click)"
    },
    {
      "action": "Right-Click Node",
      "effect": "Context-Menu: Edit / Delete / Add Child / Link",
      "menu_items": [
        "Show Details",
        "Edit",
        "Add Child",
        "Link to Requirement",
        "Delete"
      ]
    },
    {
      "action": "Type in Search-Field",
      "effect": "Tree wird gefiltert; nur Nodes mit Name/ID-Match + ihre Parents werden angezeigt",
      "state": "search_query = text",
      "debounce": "300ms"
    },
    {
      "action": "Drag Node to Parent",
      "effect": "Reparentierung: Node.parent_id = NewParent.id (optional Phase 2)",
      "note": "Nicht in MVP — nur mit Confirmation-Dialog"
    }
  ]
}
```

---

## 5. Scope-Klärung

**Frage: Nur ArchitectureElements oder auch Requirements hierarchisch?**

**Empfehlung (Hybrid-Ansatz):**

**Phase 1 (MVP):** Nur **ArchitectureElements** (L0-L4)
- Reine Zerlegungs-Hierarchie
- API liefert bereits flache Liste mit `parent_id` → einfach zu implementieren
- Clear Scope für Design & Frontend

**Phase 2 (Future):** ArchitectureElements **+ Requirement-Links** (Traceability)
- Requirement-Knoten in anderem Stil/Farbe anzeigen (z.B. gepunktet)
- Nur als Referenz, nicht im Hierarchy-Tree selbst
- Erfordert zusätzliche API für Requirement→ArchElement-Links

**Für diese Design-Spec: Phase-1-Scope (nur ArchitectureElements)**

---

## 6. Design-System: Tree-Komponente

```yaml
tree_component:
  spacing:
    indent_per_level: "16px"    # Nesting-Tiefe visuell
    item_height: "32px"         # Jeder Node
    gap_between_items: "2px"
  
  node_styling:
    default:
      text_color: "#111827"     # neutral.text-primary
      bg_color: "transparent"
      padding: "4px 8px"
    
    hover:
      bg_color: "#F3F4F6"       # neutral.background, subtle
      cursor: "pointer"
    
    selected:
      bg_color: "#DBEAFE"       # primary.light
      border_left: "3px solid #3B82F6"  # primary.main
    
    disabled:
      text_color: "#D1D5DB"     # neutral.text-disabled
      cursor: "not-allowed"
  
  level_badge:
    L0: { bg: "#1E3A8A", text: "white" }  # Dunkelblau
    L1: { bg: "#3B82F6", text: "white" }  # Blau
    L2: { bg: "#06B6D4", text: "white" }  # Cyan
    L3: { bg: "#10B981", text: "white" }  # Grün
    L4: { bg: "#9CA3AF", text: "white" }  # Grau
    size: "12px, 4px 8px"                 # Small badge
  
  expand_icon:
    size: "16px"
    color_default: "#6B7280"
    color_hover: "#111827"
    animation: "rotate 200ms ease-out"

search_box:
  placeholder: "Search elements..."
  height: "32px"
  border_radius: "4px"
  border: "1px solid #E5E7EB"
  padding: "0 8px"
  
context_menu:
  width: "180px"
  item_height: "32px"
  border_radius: "4px"
  shadow: "0 10px 15px rgba(0,0,0,0.1)"
  divider_color: "#E5E7EB"
```

---

## 7. User Journey: "Subsystem-Hierarchie durchsuchen und Detail-Ansicht öffnen"

```
JOURNEY: Decomposition Tree Navigation | PERSONA: Systems Engineer | GOAL: L3-Komponente finden und bearbeiten

Step 1: Tree-View öffnen
└─ User sieht Workspace mit Tree-Panel links
└─ L0-System bereits expandiert, L1-Subsysteme eingeklappt

Step 2: Suchen (optional)
└─ User typen "Comp" in Search-Box
└─ Tree filtert: Zeigt nur L3-Komponenten mit "Comp" im Namen + ihre Parents
└─ Search-Result: 3 Nodes sichtbar

Step 3: Knoten expandieren
└─ User klickt ▼ neben "L1-SubsystemA"
└─ Children (L2-Sub1, L2-Sub2) werden sichtbar

Step 4: Knoten auswählen
└─ User klickt "L3-Component-01"
└─ Main-Editor rechts zeigt Detail-View: ID, Type, Parent-Link, Children
└─ Node wird highlighted (blue background)

Step 5: In Editor bearbeiten (optional)
└─ User sieht [Edit] Button → Modal öffnet sich
└─ User ändert Name / Description / Status
└─ Save → Update zurück in Tree, Node-Text aktualisiert sich

Exit: Zurück zur Tree-Navigation
└─ User kann sofort nächsten Node klicken (no reload)
└─ Expanded-State bleibt erhalten

REQ-Abdeckung:
- REQ-001: Tree-Visualisierung der L0-L4 Hierarchie
- REQ-002: Click-Navigation zwischen Nodes
- REQ-003: Expand/Collapse für Performance
- REQ-004: Search/Filter für große Bäume
```

---

## 8. API-Integration

**GET /api/v1/architecture-elements/**
```json
{
  "results": [
    {
      "id": "ARCH-001",
      "name": "L0-System",
      "parent_id": null,
      "level": "L0",
      "type": "System"
    },
    {
      "id": "ARCH-002",
      "name": "L1-SubsystemA",
      "parent_id": "ARCH-001",
      "level": "L1",
      "type": "Subsystem"
    }
  ]
}
```

**Frontend-Logik (Pseudo-Code):**
```typescript
// 1. Flache API-Liste in Tree-Struktur transformieren
const treeData = flatListToTree(apiResponse.results);

// 2. Bei Expand-Click: nur unmittelbare Children laden (optional, für Performance)
const children = treeData
  .filter(node => node.parent_id === parentId)
  .map(node => ({
    ...node,
    isExpanded: false,
    hasChildren: treeData.some(n => n.parent_id === node.id)
  }));

// 3. Bei Click: ID speichern, Detail-View laden
onNodeClick(id) {
  setSelectedNodeId(id);
  dispatch(fetchArchitectureElementDetail(id));
}
```

---

## 9. Responsive Verhalten

| Breakpoint | Layout |
|-----------|--------|
| ≥1200px | Sidebar 280px + Main 100% |
| 768-1199px | Sidebar 200px + Main 100% (Tree etwas komprimiert) |
| <768px | Sidebar collapsiert (Hamburger-Menu), Tree als Drawer |

---

## 10. Accessibility (WCAG AA)

- **ARIA-Labels:** `<ul role="tree">`, `<li role="treeitem" aria-expanded="true/false">`
- **Keyboard-Navigation:** Arrow Up/Down zum Navigieren, Enter zum Expand/Click, Escape zum Collapse
- **Screen-Reader:** Node-Name + Level-Badge + Parent-Path werden vorgelesen
- **Color-Contrast:** Level-Badges mit Weiß-Text auf Farbe (min. 4.5:1)
- **Focus-Indicator:** Blauer Ring um Selected-Node (3px, #3B82F6)

---

## Zusammenfassung: Design-Entscheidungen

| Entscheidung | Begründung |
|-------------|-----------|
| **Placement: Left Sidebar** | Permanent sichtbar, paralleles Arbeiten mit Detail-View |
| **Lazy-Loading Children** | Performance bei 100+ Elementen |
| **Search mit Filter** | Große Bäume navigierbar |
| **Level-Badges mit Farbe** | Schnelle visuelle Orientierung L0-L4 |
| **Scope Phase 1: ArchElements-Only** | Reduzierter MVP-Scope, Phase-2-Ready |
| **Expand/Collapse obligatorisch** | Verhindert Information-Overload |
| **Right-Click Context-Menu** | Kompakte Aktionen ohne Toolbar-Clutter |

---

## REQ-Zuordnung

| REQ-ID | Screen-Element | Status |
|--------|--|---|
| **REQ-001** | Tree-View Panel (Sidebar) | ✅ Spezifiziert |
| **REQ-001** | Node mit Parent-Child-Relation | ✅ Spezifiziert |
| **REQ-001** | Expand/Collapse Interaction | ✅ Spezifiziert |
| **REQ-001** | Level-Badge (L0-L4 Visual) | ✅ Spezifiziert |
| **(Future)** | Search/Filter | ✅ Spezifiziert (Phase 1) |
| **(Future)** | Requirement-Link-Traceability | 📋 Phase 2 |

---

## Nächste Schritte (Implementation Phase — nicht Teil dieses Proposals)

1. **Frontend Developer:** TreeView-Komponente aus diesem Design implementieren
2. **API Enhancement:** Wenn nötig, Child-Nodes Lazy-Loading Endpoint
3. **Testing:** E2E Tests für Expand/Collapse, Search, Navigation
4. **Phase 2:** Requirement-Link Integration wenn L1 System-Validierung abgeschlossen

