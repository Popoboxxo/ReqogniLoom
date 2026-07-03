# L3 UserProfileSettings Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-006 — UserProfileSettings
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

React-Komponente zur Verwaltung der Benutzereinstellungen, fokussiert auf das Management von Personal Access Tokens (PAT). Sie zeigt eine Liste aktiver Tokens und bietet Dialoge zum Erstellen und Widerrufen (Löschen) von Tokens.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-027 | User-Profile Dialog für PAT-Verwaltung |

## L3 Komponenten-Anforderungen

### REQ-L3-RF006-001: Token Liste und UI Controls

Die Komponente MUSS eine Tabelle mit allen aktiven Tokens rendern und Buttons für "Neu" und "Löschen" bereitstellen.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Klick auf "Neu" öffnet ein Modal zur Eingabe eines Namens.
- [ ] Nach API-Erfolg (201 Created) wird das Secret in einer Copy-to-Clipboard-Box angezeigt, begleitet vom Warnhinweis, dass es danach nie wieder angezeigt wird.
- [ ] Löschen triggert eine Bestätigungsabfrage und anschließend einen DELETE Request.
