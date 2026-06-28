# L2 ReactFrontend Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** ReactFrontendSystem (ARCH-L1-001)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** subsystem (Leaf-AE — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-007 (mitwirkend), REQ-L1-014 (mitwirkend), REQ-L1-016 (primär), REQ-L1-017 (primär), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-RF-EXT-IN-001 | input | user | Browser-Nutzerinteraktion (HTTPS, Mouse, Keyboard) |
| IF-RF-EXT-OUT-001 | output | data | REST-API-Aufrufe an ARCH-L1-002 (RestApiAdapter) via HTTP/JSON + Bearer Token |
| IF-RF-EXT-OUT-002 | output | user | Gerenderte UI-Komponenten (HTML/CSS/JS im Browser) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-RF-001: Frontend-i18n mit react-i18next (DE/EN)

Das ReactFrontend MUSS alle UI-Texte über react-i18next in Deutsch und Englisch bereitstellen. Jeder UI-String MUSS einen Translation-Key in beiden Sprachdateien (de.json, en.json) besitzen. Die Sprache MUSS pro Nutzer-Präferenz umschaltbar sein (Profil-Setting oder Browser-Sprache als Default). Fehlende Translation-Keys MÜSSEN als Build-Fehler behandelt werden (Lint-Regel im CI). Der Sprachwechsel MUSS während der Session ohne Seiten-Reload erfolgen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] UI-Sprache auf Deutsch → alle Labels, Buttons, Platzhalter, Bestätigungstexte in Deutsch
- [ ] UI-Sprache auf Englisch → alle Texte in Englisch
- [ ] CI-Pipeline: Neuer UI-String ohne DE-Translation → Build schlägt fehl
- [ ] Sprachwechsel während der Session → UI aktualisiert ohne Reload

**Interfaces:**
- Incoming: IF-RF-EXT-IN-001 (Nutzer-Sprachpräferenz)
- Outgoing: IF-RF-EXT-OUT-002 (Gerenderte UI in gewählter Sprache)

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-016
**Rationale:** REQ-L1-016 fordert zweiseitige Benutzeroberfläche; ReactFrontend ist primär verantwortlich.

---

### REQ-L2-RF-002: Dashboard mit Projektübersicht und Offenen Punkten

Das ReactFrontend MUSS ein Dashboard bereitstellen, das eine Übersicht über alle Workspaces des aktuellen Nutzers zeigt, inklusive Anzahl der Requirements pro Workspace, Anzahl offener Punkte (Requirements im Initial-State ohne TraceLink) und aktives Terminologie-Profil.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nach Login rendert das Dashboard innerhalb von 2 Sekunden eine Workspace-Kartenliste
- [ ] Jede Karte zeigt Requirementszahl, Anzahl offener Punkte und aktives Terminologie-Profil
- [ ] Ein Workspace ohne offene Punkte zeigt den Zähler „0"
- [ ] Integration-Test: Login → Dashboard sichtbar → Workspace-Karten mit korrekten Zählern

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (REST-API-Antwort mit Workspace-Daten)
- Outgoing: IF-RF-EXT-OUT-001 (GET /api/v1/workspaces/)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017
**Rationale:** REQ-L1-017 fordert Dashboard als Kernkomponente der React-UI.

---

### REQ-L2-RF-003: Requirements-Editor mit Inline-Editing und Markdown

Das ReactFrontend MUSS einen Requirements-Editor bereitstellen, der Inline-Editing für Title, Description und Category eines Requirements unterstützt. Das Description-Feld MUSS Markdown rendern (Vorschau und Edit-Modus). Der Editor MUSS den aktuellen WorkflowState anzeigen und State-Übergänge über ein Dropdown auslösen können.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nutzer kann ein Requirement anklicken und Title/Description inline bearbeiten
- [ ] Markdown-Vorschau togglebar
- [ ] WorkflowState-Dropdown sichtbar und funktional
- [ ] Nach dem Speichern zeigt der Editor den aktualisierten State

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (Requirement-Daten vom Backend)
- Outgoing: IF-RF-EXT-OUT-001 (PATCH /api/v1/requirements/{id})

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017, REQ-L1-002 (mitwirkend)
**Rationale:** REQ-L1-017 fordert Requirements-Editor; REQ-L1-002 erfordert Workflow-State-Verwaltung.

---

### REQ-L2-RF-004: Architecture-Editor

Das ReactFrontend MUSS einen Architecture-Editor bereitstellen, der CRUD-Operationen für ArchitectureElements unterstützt — inkl. Element-Typ-Auswahl (Component, Interface, Subsystem, Layer, Module), Markdown-Description und Anzeige verknüpfter TraceLinks.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nutzer kann ein ArchitectureElement anlegen und den Element-Typ aus einem Dropdown wählen
- [ ] Description in Markdown editierbar
- [ ] Verknüpfte Requirements in einer Seitenleiste sichtbar
- [ ] Unit-Test: Render ArchitectureEditor mit Mock-ArchitectureElement → alle Felder sichtbar und editierbar

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (ArchitectureElement-Daten vom Backend)
- Outgoing: IF-RF-EXT-OUT-001 (CRUD-Operationen auf /api/v1/architecture-elements/)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017, REQ-L1-004 (mitwirkend)
**Rationale:** REQ-L1-017 fordert Architecture-Editor; REQ-L1-004 erfordert ArchitectureElement-Verwaltung.

---

### REQ-L2-RF-005: Artefakt-Navigation als Baumstruktur

Das ReactFrontend MUSS eine Artefakt-Navigation in Baumstruktur (Tree-View) bereitstellen, die die hierarchische Artifact-Struktur eines Workspaces darstellt. Der Baum MUSS Lazy-Loading für Kindknoten unterstützen und per Klick ein Artefakt mit seinen Requirements im Editor öffnen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tree-View zeigt die Artefakt-Hierarchie korrekt verschachtelt
- [ ] Klick auf einen Knoten lädt Kindknoten asynchron nach
- [ ] Bei 500 Artefakten beträgt die initiale Ladezeit unter 1 Sekunde (nur Root-Knoten)

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (GET /api/v1/artifacts/tree?parent_id=X)
- Outgoing: IF-RF-EXT-OUT-001 (Tree-Query-Request)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017, REQ-L1-001 (mitwirkend)
**Rationale:** REQ-L1-017 fordert Artefakt-Navigation; REQ-L1-001 erfordert hierarchische Darstellung.

---

### REQ-L2-RF-006: Traceability-Anzeige

Das ReactFrontend MUSS eine Traceability-Anzeige bereitstellen, die bidirektionale TraceLinks (Upstream/Downstream) zwischen Requirements, ArchitectureElements und TestCases visualisiert. Die Anzeige MUSS den Link-Typ (parent-child, derives-from, satisfies, verifies, implements, refines) als Label darstellen und per Klick auf ein verknüpftes Artefakt navigieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Detailansicht zeigt alle verknüpften Artefakte gruppiert nach Link-Typ
- [ ] Upstream- und Downstream-Richtung visuell unterscheidbar
- [ ] Klick auf verknüpftes Artefakt navigiert zu dessen Detailansicht
- [ ] Integration-Test: Erstelle TraceLink → UI zeigt Link in beiden betroffenen Artefakten

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (TraceLink-Daten vom Backend)
- Outgoing: IF-RF-EXT-OUT-001 (GET /api/v1/tracelinks/?artifact_id=X)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017, REQ-L1-003 (mitwirkend)
**Rationale:** ARCH-L1-001 Verantwortung umfasst „Traceability-Anzeige"; REQ-L1-003 erfordert bidirektionale Trace-Queries.

---

### REQ-L2-RF-007: Preset-basierte UI-Sichtbarkeit

Das ReactFrontend MUSS UI-Elemente, Felder und Funktionen basierend auf dem aktiven Workspace-Preset (Minimal / Standard / Extended) ein- oder ausblenden. Die Sichtbarkeitsregeln MÜSSEN aus der PresetConfigEngine (ARCH-L1-008, via REST-Endpunkt) geladen werden. Beim Wechsel des Presets MUSS sich die UI ohne Seiten-Reload aktualisieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal-Preset: Erweiterte Workflow-Konfiguration, Baseline-Scope „Global" und Approver-bezogene UI-Elemente ausgeblendet
- [ ] Standard-Preset: Baseline-Scope „Global" ausgeblendet; erweiterte Workflow-Konfiguration sichtbar
- [ ] Extended-Preset: Alle UI-Elemente sichtbar
- [ ] Preset-Wechsel → UI aktualisiert sich ohne Reload

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (Preset-Regeln via REST)
- Outgoing: IF-RF-EXT-OUT-001 (GET /api/v1/workspaces/{id}/preset/)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-007 (mitwirkend)
**Rationale:** REQ-L1-007 erfordert, dass die UI Preset-Regeln respektiert.

---

### REQ-L2-RF-008: Terminologie-Profil-Rendering (Dev-Modus / SE-Modus)

Das ReactFrontend MUSS das aktive Terminologie-Profil (Dev-Modus / SE-Modus) aus den Workspace-Settings laden und UI-Labels dynamisch entsprechend rendern. Ein Profilwechsel MUSS ausschließlich Labels und UI-Texte ändern — keine API-Aufrufe mit geänderten Entitätsnamen. Die generischen API-Feldnamen MÜSSEN unverändert bleiben.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Dev-Modus: UI zeigt Labels wie „Epic", „Story", „Task"
- [ ] SE-Modus: UI zeigt Labels wie „System", „Subsystem", „Component"
- [ ] Profilwechsel → alle Labels aktualisieren sich sofort; API-Calls verwenden weiterhin generische Feldnamen
- [ ] Unit-Test: Setze Profil auf SE-Modus → alle Labels entsprechen SE-Terminologie

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (Terminologie-Profil-Konfiguration)
- Outgoing: IF-RF-EXT-OUT-001 (GET /api/v1/workspaces/{id}/settings/)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-014 (mitwirkend)
**Rationale:** REQ-L1-014 erfordert UI-seitige Label-Anpassung; API und MCP nutzen generische Namen.

---

### REQ-L2-RF-009: UI-Performance

Das ReactFrontend MUSS initiale Seitenansichten innerhalb von 2 Sekunden rendern und Nutzerinteraktionen (Editor-Wechsel, Knoten-Expansion, Sprachwechsel) innerhalb von 500 ms verarbeiten — unter der Bedingung von bis zu 10.000 Requirements im aktiven Workspace und einer stabilen Netzwerkverbindung zum Backend.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Dashboard-Render nach Login: < 2 Sekunden
- [ ] Tree-View initiales Laden (500 Artefakte): < 1 Sekunde
- [ ] Editor-Wechsel: < 500 ms
- [ ] Sprachwechsel (DE ↔ EN): < 500 ms ohne Reload
- [ ] Messung: 95. Perzentil unter definierter Last (50 gleichzeitige Nutzer)

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (API-Antworten)
- Outgoing: IF-RF-EXT-OUT-002 (Gerenderte UI)

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-026 (mitwirkend)
**Rationale:** REQ-L1-026 betrifft alle Schnittstellen; ARCH-L1-001 ist explizit mitwirkend.

---

### REQ-L2-RF-010: REST-API-Kommunikation mit Bearer-Token-Authentifizierung

Das ReactFrontend MUSS ausschließlich über die REST API (ARCH-L1-002) mit dem Backend kommunizieren. Jede Anfrage MUSS den Bearer-Token des authentifizierten Nutzers im `Authorization`-Header mitführen. Bei 401-Antworten MUSS das Frontend den Nutzer zur Login-Seite umleiten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle API-Calls enthalten `Authorization: Bearer <token>` Header
- [ ] 401-Response → automatische Umleitung zur Login-Seite
- [ ] Kein direkter Datenbankzugriff oder MCP-Protokollaufruf aus dem Frontend
- [ ] Integration-Test: API-Call ohne Token → 401 → Redirect zu Login

**Interfaces:**
- Outgoing: IF-RF-EXT-OUT-001 (REST-API-Aufrufe mit Bearer Token)
- Incoming: IF-RF-EXT-OUT-001 (REST-API-Antworten)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017, REQ-L1-006 (mitwirkend)
**Rationale:** ARCH-L1-001 spezifiziert: „Kommuniziert ausschließlich über die REST API mit dem Backend."

---

### REQ-L2-RF-011: Fehleranzeige und Backend-Error-Rendering

Das ReactFrontend MUSS Backend-Fehlermeldungen (übersetzt via Accept-Language in DE/EN) in einer nutzerfreundlichen Form anzeigen. Fehler MÜSSEN den übersetzten Text aus dem REST-Response enthalten und dem Nutzer eine Handlungsoption bieten (z.B. „Erneut versuchen", „Zurück").

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Backend liefert Fehler mit `Accept-Language: de` → Fehlermeldung auf Deutsch angezeigt
- [ ] Backend liefert Fehler mit `Accept-Language: en` → Fehlermeldung auf Englisch angezeigt
- [ ] Fehlermeldung enthält nutzbare Handlungsoption (Retry / Back / Dismiss)
- [ ] Integration-Test: Simuliere 400-Response → übersetzter Fehlertext sichtbar

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (Fehler-Responses vom Backend)
- Outgoing: IF-RF-EXT-OUT-002 (Fehler-UI gerendert)

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-016 (mitwirkend), REQ-L1-017
**Rationale:** REQ-L1-016 fordert übersetzte Backend-Fehlermeldungen; ReactFrontend muss sie rendern.

---

### REQ-L2-RF-012: Workspace-Konfigurations-UI

Das ReactFrontend MUSS eine Workspace-Konfigurationsseite bereitstellen, auf der der Nutzer (mit Admin-Rolle) das aktive Preset (Minimal / Standard / Extended), das Terminologie-Profil (Dev-Modus / SE-Modus) und die Spracheinstellung einsehen und ändern kann. Änderungen MÜSSEN sofort wirksam werden (kein Reload erforderlich).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Admin-Nutzer sieht Preset-Auswahl, Terminologie-Profil-Auswahl und Spracheinstellung
- [ ] Änderung Preset → UI aktualisiert sichtbare Elemente sofort
- [ ] Änderung Terminologie-Profil → Labels aktualisieren sich sofort
- [ ] Nicht-Admin-Nutzer sieht die Konfigurationsseite nicht oder nur lesend

**Interfaces:**
- Outgoing: IF-RF-EXT-OUT-001 (PATCH /api/v1/workspaces/{id}/settings/)
- Incoming: IF-RF-EXT-OUT-001 (Aktualisierte Workspace-Settings)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-017, REQ-L1-007 (mitwirkend), REQ-L1-014 (mitwirkend)
**Rationale:** ARCH-L1-001 Verantwortung umfasst „Workspace-Profil-Konfiguration".

---

## Erweiterung Phase 3 (se-architect, 2026-06-27)

### REQ-L2-RF-014: Visuelles Artefakt-Diff

Das ReactFrontend MUSS Änderungen an einem einzelnen Artefakt zwischen zwei beliebigen Versionen als visuellen Text-Diff darstellen. Das Diff MUSS mit visueller Hervorhebung angezeigt werden (grün=hinzugefügt, rot=gelöscht, gelb=geändert). Die Diff-Ansicht ist in der Artefakt-Detailansicht integriert und zeigt Feld-Level-Änderungen.

**Domain:** software
**Priority:** desired
**arch_impact:** false
**Acceptance Criteria:**
- [ ] GUI zeigt Diff mit visueller Hervorhebung (grün=hinzugefügt, rot=gelöscht, gelb=geändert)
- [ ] Diff-Ansicht ist in der Artefakt-Detailansicht integriert
- [ ] Versionsauswahl (from/to) via UI-Steuerung möglich
- [ ] Markdown-Felder werden als Text-Diff dargestellt
- [ ] Diff wird via REST-API (GET /artifacts/{id}/diff) geladen

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (GET /artifacts/{id}/diff?from=v1&to=v2)
- Outgoing: IF-RF-EXT-OUT-002 (Gerenderte Diff-Ansicht)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-040
**Rationale:** Visueller Diff ist für formale Reviews und Freigabe-Entscheidungen unerlässlich.

---

### REQ-L2-RF-015: Visuelles Baseline-Diff

Das ReactFrontend MUSS den Vergleich zweier benannter Baselines als visuellen Diff darstellen. Die Diff-Ansicht zeigt eine kategorisierte Liste (hinzugefügte, geänderte, gelöschte Artefakte inkl. Versions-Delta) mit Navigation zwischen Kategorien. Vergleich inkompatibler Scopes (document↔project) MUSS einen klaren Fehlerhinweis anzeigen.

**Domain:** software
**Priority:** desired
**arch_impact:** false
**Acceptance Criteria:**
- [ ] GUI zeigt Diff mit kategorisierter Liste (added/modified/deleted)
- [ ] Navigation zwischen Kategorien möglich
- [ ] Modified-Liste zeigt Versions-Delta (Version in Baseline A → Version in Baseline B)
- [ ] Vergleich kompatibler Scopes (document↔document, project↔project) möglich
- [ ] Vergleich inkompatibler Scopes → klarer Fehlerhinweis in UI

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (GET /baselines/{id_a}/diff/{id_b})
- Outgoing: IF-RF-EXT-OUT-002 (Gerenderte Baseline-Diff-Ansicht)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L1-041
**Rationale:** Baseline-Diff ist für formale Reviews und Compliance-Nachweise in regulierten Umgebungen zwingend.

---

## Traceability-Matrix: REQ-L2-RF → REQ-L1

| REQ-L2-RF | Titel | REQ-L1 (primär) | REQ-L1 (mitwirkend) |
|-----------|-------|-----------------|---------------------|
| REQ-L2-RF-001 | Frontend-i18n (DE/EN) | REQ-L1-016 | — |
| REQ-L2-RF-002 | Dashboard | REQ-L1-017 | — |
| REQ-L2-RF-003 | Requirements-Editor | REQ-L1-017 | REQ-L1-002 |
| REQ-L2-RF-004 | Architecture-Editor | REQ-L1-017 | REQ-L1-004 |
| REQ-L2-RF-005 | Artefakt-Navigation | REQ-L1-017 | REQ-L1-001 |
| REQ-L2-RF-006 | Traceability-Anzeige | REQ-L1-017 | REQ-L1-003 |
| REQ-L2-RF-007 | Preset-basierte Sichtbarkeit | REQ-L1-007 | — |
| REQ-L2-RF-008 | Terminologie-Profil-Rendering | REQ-L1-014 | — |
| REQ-L2-RF-009 | UI-Performance | REQ-L1-026 | — |
| REQ-L2-RF-010 | REST-API-Kommunikation | REQ-L1-017 | REQ-L1-006 |
| REQ-L2-RF-011 | Fehleranzeige | REQ-L1-016 | REQ-L1-017 |
| REQ-L2-RF-012 | Workspace-Konfigurations-UI | REQ-L1-017 | REQ-L1-007, REQ-L1-014 |
| REQ-L2-RF-013 | (reserviert) | — | — |
| REQ-L2-RF-014 | Visuelles Artefakt-Diff | REQ-L1-040 | — |
| REQ-L2-RF-015 | Visuelles Baseline-Diff | REQ-L1-041 | — |

---

## REQ-L1-Abdeckung für ARCH-L1-001

| REQ-L1 | Titel | Abgedeckt durch | Status |
|--------|-------|-----------------|--------|
| REQ-L1-007 | Configurable-Rigor-Presets | REQ-L2-RF-007, REQ-L2-RF-012 | ✓ |
| REQ-L1-014 | Terminologie-Profile | REQ-L2-RF-008, REQ-L2-RF-012 | ✓ |
| REQ-L1-016 | i18n DE/EN | REQ-L2-RF-001, REQ-L2-RF-011 | ✓ |
| REQ-L1-017 | React-UI | REQ-L2-RF-002..006, REQ-L2-RF-010, REQ-L2-RF-012 | ✓ |
| REQ-L1-026 | Performance | REQ-L2-RF-009 | ✓ |

**Vollständigkeit:** Alle ARCH-L1-001 zugeordneten REQ-L1 sind durch mindestens eine REQ-L2-RF abgedeckt.

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-React → REQ-L2-RF, Template-Standardisierung*
*Designation: subsystem (Leaf-AE) — decomposition_status: terminal*
