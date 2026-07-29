decomposition_status: terminal

# L3 ListToolbar Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-010 — ListToolbar
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-04

---

## Verantwortlichkeit

Generische Filter-, Such- und Sortierleiste für Listenansichten.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-031 | Reusable List-Toolbar |

## L3 Komponenten-Anforderungen

### REQ-L3-RF010-001: Form-Handling und URL-Sync

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Suchfeld für Text mit 300ms Debounce, feuert `onSearch` Callback.
- [ ] Filter-Dropdowns können dynamisch via Props konfiguriert werden (z.B. `{label: 'Status', key: 'state', options: [...]}`).
- [ ] Jede Änderung aktualisiert den URL Search-Query (`?search=foo&state=approved`).
- [ ] Beim Laden der Komponente werden die initialen Werte aus der URL ausgelesen.

---

### REQ-L3-RF010-002: L3 Context Generators Implementation

Derives from REQ-L2-REA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RF010-003: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-REA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
