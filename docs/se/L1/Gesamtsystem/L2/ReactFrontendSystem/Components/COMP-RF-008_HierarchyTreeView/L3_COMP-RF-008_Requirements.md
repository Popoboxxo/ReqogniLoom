# L3 HierarchyTreeView Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-008 — HierarchyTreeView
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-04

---

## Verantwortlichkeit

React-Komponente zur Anzeige verschachtelter Datenstrukturen, speziell Artefakte, die über `parent_id` verknüpft sind.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-029 | Hierarchy Tree-View Component |

## L3 Komponenten-Anforderungen

### REQ-L3-RF008-001: Rendering & Interaktion

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Rekursives Rendering der Knoten, basierend auf einer flachen Liste mit `parent_id` oder einer vorverarbeiteten Baum-Struktur.
- [ ] Klick auf das Caret-Icon klappt Kinder auf/zu.
- [ ] Klick auf den Text wählt das Artefakt aus (z.B. URL-Wechsel zu `/requirements/{id}`).
- [ ] Virtuelles Scrolling, um auch bei hunderten Knoten flüssig zu bleiben.
