decomposition_status: terminal

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

**Implementation State:** Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [~] Klick auf "Neu" öffnet ein Modal zur Eingabe eines Namens. → umgesetzt als Inline-Formular (Name-Input + Button) statt Modal-Dialog, funktional äquivalent (`ApiKeysSection.tsx`).
- [x] Nach API-Erfolg (201 Created) wird das Secret in einer Copy-to-Clipboard-Box angezeigt, begleitet vom Warnhinweis, dass es danach nie wieder angezeigt wird. → `api-key-plaintext-box` mit `apiKeys.plaintextWarning` + Copy-Button.
- [x] Löschen triggert eine Bestätigungsabfrage und anschließend einen DELETE Request. → `window.confirm` + `apiKeysApi.revoke()`.

> **Architektur-Entscheidung (2026-07-04):** Implementiert als `UserProfileSettings.tsx` + `ApiKeysSection.tsx` (`frontend/src/components/UserProfileSettings/`), erreichbar über eigene, workspace-unabhängige Route `/profile` (Sidebar-Footer-Button `nav-profile`). Bewusst außerhalb von `WorkspaceSettings` platziert — Tokens sind an den User gebunden, nicht an einen Workspace, und müssen ohne aktiven Workspace generierbar sein. `ApiKeysSection` war zuvor Teil von `WorkspaceSettings.tsx` und wurde herausgelöst. Nutzt den bestehenden `ApiKeyViewSet`/`AuthenticationService`-Backend-Pfad (siehe COMP-RA-007, COMP-AT-006) statt eines neuen Backend-Endpunkts.

---

### REQ-L3-RF006-002: L3 Context Generators Implementation

Derives from REQ-L2-REA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RF006-003: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-REA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
