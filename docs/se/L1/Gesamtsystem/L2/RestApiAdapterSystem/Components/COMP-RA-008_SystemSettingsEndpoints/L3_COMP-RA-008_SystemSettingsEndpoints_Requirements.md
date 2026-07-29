decomposition_status: terminal

# L3 SystemSettingsEndpoints Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-008 — SystemSettingsEndpoints
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-04

---

## Verantwortlichkeit

DRF ViewSet für das Routing von System-Konfigurationen, hier konkret `/api/v1/system/announcement`. Setzt Berechtigungen um (GET für alle Authentifizierten, PUT nur für Admins).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-022 | System Announcement API |

## L3 Komponenten-Anforderungen

### REQ-L3-RA008-001: Announcement ViewSet

Das ViewSet MUSS die Lese- und Schreibzugriffe auf das Announcement-Singleton regeln.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] GET liefert `{active: boolean, message: string}`.
- [ ] PUT erlaubt Admins das Setzen der Werte.
- [ ] Ein Nicht-Admin erhält bei PUT einen 403 Fehler.

---

### REQ-L3-RA008-002: L3 Context Generators Implementation

Derives from REQ-L2-RES-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RA008-003: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-RES-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
