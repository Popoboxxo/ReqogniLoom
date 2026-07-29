decomposition_status: terminal

# L3 SystemAnnouncementBanner Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-007 — SystemAnnouncementBanner
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-04

---

## Verantwortlichkeit

React-Komponente, die am oberen Bildschirmrand über die gesamte Breite angezeigt wird, um den aktuellen Status-Text auszugeben. Außerdem eine Admin-Einstellungsseite zur Verwaltung.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-028 | Globales System Announcement Banner |

## L3 Komponenten-Anforderungen

### REQ-L3-RF007-001: Banner Layout und Loading

Die Komponente MUSS als globale Navbar-Extension implementiert sein. Sie pollt beim Start `/api/v1/system/announcement` und bei `active=true` klappt das Banner auf.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Feste (Sticky) Position über der Navigation.
- [ ] Hintergrundfarbe passend zu Warnungen (z.B. Gelb/Rot).
- [ ] Einstellungsseite unter `/settings/system` (nur für Admins) zum Ein-/Ausschalten und Text editieren.

---

### REQ-L3-RF007-002: L3 Context Generators Implementation

Derives from REQ-L2-REA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RF007-003: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-REA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
