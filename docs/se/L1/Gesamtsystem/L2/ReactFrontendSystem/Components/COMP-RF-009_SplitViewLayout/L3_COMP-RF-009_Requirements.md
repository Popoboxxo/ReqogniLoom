# L3 SplitViewLayout Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-009 — SplitViewLayout
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-04

---

## Verantwortlichkeit

Wrapper-Komponente, die den Bildschirm in zwei Spalten teilt und einen Resizer-Handle bereitstellt.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-030 | Split-View Layout Component |

## L3 Komponenten-Anforderungen

### REQ-L3-RF009-001: Resizable Divider

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Nimmt `leftPane` und `rightPane` als React-Children entgegen.
- [ ] Divider in der Mitte reagiert auf Mouse-Drag.
- [ ] CSS Flexbox / Grid Basis.
- [ ] Speichert das Layout (Ratio) persistiert im `localStorage`.
