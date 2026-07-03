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
