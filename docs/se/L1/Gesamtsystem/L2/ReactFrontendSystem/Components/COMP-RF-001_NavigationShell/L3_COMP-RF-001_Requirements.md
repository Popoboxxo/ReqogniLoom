# L3 NavigationShell Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-001 — NavigationShell
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Hauptanwendungs-Layout, Routing zwischen Funktionsmodulen, Authentifizierungs-Gate, Top-Level Error Boundaries, 401-Redirect.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-005 | Artefakt-Navigation als Baumstruktur |
| REQ-L2-RF-007 | Preset-basierte UI-Sichtbarkeit |
| REQ-L2-RF-009 | UI-Performance |
| REQ-L2-RF-010 | REST-API-Kommunikation mit Bearer-Token-Authentifizierung |
| REQ-L2-RF-011 | Fehleranzeige und Backend-Error-Rendering |
| REQ-L2-RF-012 | Workspace-Konfigurations-UI |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RF-INT-001 | ausgehend | COMP-RF-002..005 | Routing-Events, View-Activation, Modul-Ein-/Ausblendung basierend auf Preset |
| IF-RF-INT-003 | ausgehend | COMP-RF-003, COMP-RF-004 | Artefakt-Selektion (`{artifact_id, artifact_type}`) via React Props / State |
| IF-RF-INT-002 | eingehend | COMP-RF-006 | Translation-Keys, Terminologie-Profil-Labels, Locale-Change-Events |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-RF-EXT-IN-001 | eingehend | Browser-Nutzer | user | Nutzerinteraktion via Mouse, Keyboard |
| IF-RF-EXT-OUT-001 | ausgehend | RestApiAdapter | data | REST-API-Aufrufe mit Bearer Token (Auth-Endpoints, Workspace-Settings) |
| IF-RF-EXT-OUT-002 | ausgehend | Browser-Nutzer | user | Gerenderte Shell-UI (Layout, Navigation, Error-Overlays) |

## L3 Komponenten-Anforderungen

### REQ-L3-RF001-001: Authentifizierungs-Gate mit Bearer-Token-Weiterleitung

Die NavigationShell MUSS jeden eingehenden Request auf das Vorhandensein eines gültigen Bearer-Tokens prüfen. Bei fehlendem oder abgelaufenem Token MUSS eine automatische Weiterleitung zur Login-Seite ohne Datenverlust erfolgen. Bei einer 401-Antwort des Backends MUSS dieselbe Weiterleitung ausgelöst werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Unauthenticated route access → redirect to /login without rendering protected content
- [ ] 401 response from any API call → automatic redirect to /login
- [ ] Valid token present → protected routes render without additional authentication prompt

---

### REQ-L3-RF001-002: Preset-gesteuertes Modul-Routing

Die NavigationShell MUSS die sichtbaren Navigationseinträge und aktivierbaren Routen basierend auf dem aktiven Workspace-Preset (Minimal / Standard / Extended) ein- oder ausblenden. Routen, die durch das Preset ausgeblendet sind, MÜSSEN bei direktem URL-Aufruf auf eine Fehlerseite umleiten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal-Preset: Extended-workflow-routes hidden in navigation and blocked on direct URL access
- [ ] Standard-Preset: Advanced workflow configuration visible, global baseline scope hidden
- [ ] Extended-Preset: All navigation entries and routes accessible
- [ ] Direct URL to hidden route → redirect to error page (403 or dashboard)

---

### REQ-L3-RF001-003: Top-Level Error Boundary mit Fehlermeldungs-Rendering

Die NavigationShell MUSS eine React Error Boundary auf Top-Level-Ebene implementieren, die unkontrollierte Laufzeitfehler in Kindkomponenten abfängt und dem Nutzer eine übersetzte Fehlermeldung mit einer Wiederherstellungsoption (Reload oder Zurück zur Startseite) anzeigt, ohne die gesamte Anwendung zu schließen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Runtime error in any child component → Error Boundary catches and renders error UI instead of blank screen
- [ ] Error UI displays translated message matching active locale (DE/EN)
- [ ] User is offered at least one recovery action (reload / return to dashboard)
- [ ] Error is logged to browser console with component stack trace

---

### REQ-L3-RF001-004: Artefakt-Selektion und Editor-Aktivierung

Die NavigationShell MUSS bei Nutzerauswahl eines Artefakts in der Baumnavigation das zugehörige `{artifact_id, artifact_type}`-Tupel als React Props an den zuständigen Editor (RequirementEditors oder ArchitectureEditors) übergeben und die entsprechende Editor-Route aktivieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Selecting an artifact of type `requirement` activates RequirementEditors with correct artifact_id
- [ ] Selecting an artifact of type `architecture_element` activates ArchitectureEditors with correct artifact_id
- [ ] Navigation between artifacts does not trigger full page reload
- [ ] Active artifact is visually highlighted in the tree navigation

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
