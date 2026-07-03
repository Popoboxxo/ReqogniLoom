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

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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

**Traceability:** REQ-L1-016
**Rationale:** REQ-L1-016 fordert zweiseitige Benutzeroberfläche; ReactFrontend ist primär verantwortlich.

---

### REQ-L2-RF-002: Dashboard mit Projektübersicht und Offenen Punkten
Das ReactFrontend MUSS ein Dashboard bereitstellen, das eine Übersicht über alle Workspaces des aktuellen Nutzers zeigt, inklusive Anzahl der Requirements pro Workspace, Anzahl offener Punkte (Requirements im Initial-State ohne TraceLink) und aktives Terminologie-Profil.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-017
**Rationale:** REQ-L1-017 fordert Dashboard als Kernkomponente der React-UI.

---

### REQ-L2-RF-003: Requirements-Editor mit Inline-Editing und Markdown
Das ReactFrontend MUSS einen Requirements-Editor bereitstellen, der Inline-Editing für Title, Description und Category eines Requirements unterstützt. Das Description-Feld MUSS Markdown rendern (Vorschau und Edit-Modus). Der Editor MUSS den aktuellen WorkflowState anzeigen und State-Übergänge über ein Dropdown auslösen können.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-017, REQ-L1-002 (mitwirkend)
**Rationale:** REQ-L1-017 fordert Requirements-Editor; REQ-L1-002 erfordert Workflow-State-Verwaltung.

---

### REQ-L2-RF-004: Architecture-Editor
Das ReactFrontend MUSS einen Architecture-Editor bereitstellen, der CRUD-Operationen für ArchitectureElements unterstützt — inkl. Element-Typ-Auswahl (Component, Interface, Subsystem, Layer, Module), Markdown-Description und Anzeige verknüpfter TraceLinks.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-017, REQ-L1-004 (mitwirkend)
**Rationale:** REQ-L1-017 fordert Architecture-Editor; REQ-L1-004 erfordert ArchitectureElement-Verwaltung.

---

### REQ-L2-RF-005: Artefakt-Navigation als Baumstruktur
Das ReactFrontend MUSS eine Artefakt-Navigation in Baumstruktur (Tree-View) bereitstellen, die die hierarchische Artifact-Struktur eines Workspaces darstellt. Der Baum MUSS Lazy-Loading für Kindknoten unterstützen und per Klick ein Artefakt mit seinen Requirements im Editor öffnen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tree-View zeigt die Artefakt-Hierarchie korrekt verschachtelt
- [ ] Klick auf einen Knoten lädt Kindknoten asynchron nach
- [ ] Bei 500 Artefakten beträgt die initiale Ladezeit unter 1 Sekunde (nur Root-Knoten)

**Interfaces:**
- Incoming: IF-RF-EXT-OUT-001 (GET /api/v1/artifacts/tree?parent_id=X)
- Outgoing: IF-RF-EXT-OUT-001 (Tree-Query-Request)

**Traceability:** REQ-L1-017, REQ-L1-001 (mitwirkend)
**Rationale:** REQ-L1-017 fordert Artefakt-Navigation; REQ-L1-001 erfordert hierarchische Darstellung.

---

### REQ-L2-RF-006: Traceability-Anzeige
Das ReactFrontend MUSS eine Traceability-Anzeige bereitstellen, die bidirektionale TraceLinks (Upstream/Downstream) zwischen Requirements, ArchitectureElements und TestCases visualisiert. Die Anzeige MUSS den Link-Typ (parent-child, derives-from, satisfies, verifies, implements, refines) als Label darstellen und per Klick auf ein verknüpftes Artefakt navigieren.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-017, REQ-L1-003 (mitwirkend)
**Rationale:** ARCH-L1-001 Verantwortung umfasst „Traceability-Anzeige"; REQ-L1-003 erfordert bidirektionale Trace-Queries.

---

### REQ-L2-RF-007: Preset-basierte UI-Sichtbarkeit
Das ReactFrontend MUSS UI-Elemente, Felder und Funktionen basierend auf dem aktiven Workspace-Preset (Minimal / Standard / Extended) ein- oder ausblenden. Die Sichtbarkeitsregeln MÜSSEN aus der PresetConfigEngine (ARCH-L1-008, via REST-Endpunkt) geladen werden. Beim Wechsel des Presets MUSS sich die UI ohne Seiten-Reload aktualisieren.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-007 (mitwirkend)
**Rationale:** REQ-L1-007 erfordert, dass die UI Preset-Regeln respektiert.

---

### REQ-L2-RF-008: Terminologie-Profil-Rendering (Dev-Modus / SE-Modus)
Das ReactFrontend MUSS das aktive Terminologie-Profil (Dev-Modus / SE-Modus) aus den Workspace-Settings laden und UI-Labels dynamisch entsprechend rendern. Ein Profilwechsel MUSS ausschließlich Labels und UI-Texte ändern — keine API-Aufrufe mit geänderten Entitätsnamen. Die generischen API-Feldnamen MÜSSEN unverändert bleiben.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-014 (mitwirkend)
**Rationale:** REQ-L1-014 erfordert UI-seitige Label-Anpassung; API und MCP nutzen generische Namen.

---

### REQ-L2-RF-009: UI-Performance
Das ReactFrontend MUSS initiale Seitenansichten innerhalb von 2 Sekunden rendern und Nutzerinteraktionen (Editor-Wechsel, Knoten-Expansion, Sprachwechsel) innerhalb von 500 ms verarbeiten — unter der Bedingung von bis zu 10.000 Requirements im aktiven Workspace und einer stabilen Netzwerkverbindung zum Backend.

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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

**Traceability:** REQ-L1-026 (mitwirkend)
**Rationale:** REQ-L1-026 betrifft alle Schnittstellen; ARCH-L1-001 ist explizit mitwirkend.

---

### REQ-L2-RF-010: REST-API-Kommunikation mit Bearer-Token-Authentifizierung
Das ReactFrontend MUSS ausschließlich über die REST API (ARCH-L1-002) mit dem Backend kommunizieren. Jede Anfrage MUSS den Bearer-Token des authentifizierten Nutzers im `Authorization`-Header mitführen. Bei 401-Antworten MUSS das Frontend den Nutzer zur Login-Seite umleiten.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-017, REQ-L1-006 (mitwirkend)
**Rationale:** ARCH-L1-001 spezifiziert: „Kommuniziert ausschließlich über die REST API mit dem Backend."

---

### REQ-L2-RF-011: Fehleranzeige und Backend-Error-Rendering
Das ReactFrontend MUSS Backend-Fehlermeldungen (übersetzt via Accept-Language in DE/EN) in einer nutzerfreundlichen Form anzeigen. Fehler MÜSSEN den übersetzten Text aus dem REST-Response enthalten und dem Nutzer eine Handlungsoption bieten (z.B. „Erneut versuchen", „Zurück").

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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

**Traceability:** REQ-L1-016 (mitwirkend), REQ-L1-017
**Rationale:** REQ-L1-016 fordert übersetzte Backend-Fehlermeldungen; ReactFrontend muss sie rendern.

---

### REQ-L2-RF-012: Workspace-Konfigurations-UI
Das ReactFrontend MUSS eine Workspace-Konfigurationsseite bereitstellen, auf der der Nutzer (mit Admin-Rolle) das aktive Preset (Minimal / Standard / Extended), das Terminologie-Profil (Dev-Modus / SE-Modus) und die Spracheinstellung einsehen und ändern kann. Änderungen MÜSSEN sofort wirksam werden (kein Reload erforderlich).

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-017, REQ-L1-007 (mitwirkend), REQ-L1-014 (mitwirkend)
**Rationale:** ARCH-L1-001 Verantwortung umfasst „Workspace-Profil-Konfiguration".

---

## Erweiterung Phase 3 (se-architect, 2026-06-27)

### REQ-L2-RF-014: Visuelles Artefakt-Diff
Das ReactFrontend MUSS Änderungen an einem einzelnen Artefakt zwischen zwei beliebigen Versionen als visuellen Text-Diff darstellen. Das Diff MUSS mit visueller Hervorhebung angezeigt werden (grün=hinzugefügt, rot=gelöscht, gelb=geändert). Die Diff-Ansicht ist in der Artefakt-Detailansicht integriert und zeigt Feld-Level-Änderungen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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

**Traceability:** REQ-L1-040
**Rationale:** Visueller Diff ist für formale Reviews und Freigabe-Entscheidungen unerlässlich.

---

### REQ-L2-RF-015: Visuelles Baseline-Diff
Das ReactFrontend MUSS den Vergleich zweier benannter Baselines als visuellen Diff darstellen. Die Diff-Ansicht zeigt eine kategorisierte Liste (hinzugefügte, geänderte, gelöschte Artefakte inkl. Versions-Delta) mit Navigation zwischen Kategorien. Vergleich inkompatibler Scopes (document↔document, project↔project) MUSS einen klaren Fehlerhinweis anzeigen.

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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

---

## Erweiterung v2 — REQ-L2-RF-016..017 (aus REQ-L1-048 und REQ-L1-045/046)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L1-048 (Feedback REQ-L1-001), REQ-L1-045, REQ-L1-046

---

### REQ-L2-RF-016: Flat View & Level View (Multi-View-Artefaktansicht)

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

Das Frontend MUSS für alle Artefakttypen (Requirements, Architecture, TestCases, TraceLinks)
zwei Ansichtsmodi bereitstellen, die jederzeit umschaltbar sind:

1. **Flat View:** Alle Artefakte eines Workspaces in einer tabellarischen Liste,
   filter- und sortierbar nach Typ, Status, REQ-ID, Ebene.
2. **Level View:** Hierarchische Baumdarstellung nach Kaskaden-Ebene (L0 → L1 → L2 → Ln),
   kollabierbar pro Ebene, navigierbar.

Ein Toggle-Element MUSS den Wechsel zwischen beiden Modi ermöglichen.
Der gewählte Modus MUSS per Nutzer-Session persistent sein (LocalStorage).

**Akzeptanzkriterien:**
- AC1: Toggle-Button „Flat / Level" sichtbar in der Artefakt-Übersicht
- AC2: Flat View zeigt alle Artefakte in Tabelle mit Filter (Typ, Status, Ebene)
- AC3: Level View zeigt Baumstruktur mit kollabierbaren Ebenen-Knoten
- AC4: Wechsel zwischen Modi zeigt dieselben Artefakte ohne Reload
- AC5: Gewählter Modus bleibt nach Seiten-Refresh erhalten (LocalStorage)
- AC6: Level View zeigt `suspect`-Status (SN-30) und `cross-level`-Marker (SN-35) distinkt

**Verifikationsmethode:** UI-E2E-Test — Toggle-Wechsel, Artefakt-Konsistenz, Filter-Funktionalität
**Verifikiert durch:** L2-RF-Test-016
**Abgeleitet von:** REQ-L1-048
**Übergeordnete REQ-L0:** REQ-L1-001 (Feedback-Erweiterung)

---

### REQ-L2-RF-017: Sandbox-Diff-UI & Baseline-Vergleich

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

Das Frontend MUSS eine dedizierte Diff-Ansicht für zwei Szenarien bereitstellen:

1. **Sandbox-Merge-Diff:** Beim Merge-Vorgang (REQ-L2-BL-010) zeigt die UI einen
   zweispaltigen Diff zwischen Sandbox-Zweig und Hauptstand. Konflikte werden rot markiert.
   Der Nutzer kann Konflikte manuell auflösen (Auswahl: „Sandbox-Version" oder „Hauptstand-Version").

2. **Baseline-Vergleich:** Nutzer können zwei Baselines (oder zwei Versionen desselben
   Artefakts) in einer zweispaltigen Ansicht vergleichen. Changed/Added/Removed-Felder
   werden auf Feld-Ebene farbig hervorgehoben (grün/rot/gelb).

**Akzeptanzkriterien:**
- AC1: Sandbox-Merge-Diff zeigt alle geänderten Felder zweispaltig (Sandbox | Hauptstand)
- AC2: Konflikte sind rot markiert; nicht-konfliktive Änderungen werden automatisch übernommen
- AC3: Manuelle Konfliktauflösung per Klick (Auswahl der gewünschten Version)
- AC4: Baseline-Vergleich: Dropdown für zwei Baselines → Diff-Darstellung
- AC5: Added/Removed/Changed-Felder sind farbig kodiert (grün/rot/gelb)
- AC6: Diff-Ansicht ist druckbar / exportierbar (PDF/Clipboard)

**Verifikationsmethode:** UI-E2E-Test — Sandbox erstellen, Änderung, Merge-Diff prüfen
**Verifikiert durch:** L2-RF-Test-017
**Abgeleitet von:** REQ-L1-045, REQ-L1-046
**Übergeordnete REQ-L0:** REQ-L0-033, REQ-L0-034

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-RF-016..017 aus REQ-L1-048, REQ-L1-045/046)*

---

## Erweiterung v8 — REQ-L2-RF-018 (Ebenen-Modell)

> **Datum:** 2026-07-02 | **Quelle:** REQ-L1-063

---

### REQ-L2-RF-018: Frontend Level-View (Requirements Hierarchy)

Das ReactFrontendSystem MUSS eine neue Route oder Ansicht `/levels` bereitstellen, die alle Requirements gruppiert nach ihrer abgeleiteten Ebene (Level) darstellt. Das Layout SOLL als Tree-View oder Tabellen-View realisiert sein und die Felder Level, Allocated-to-Owner, Status und Workflow-State anzeigen.

**Akzeptanzkriterien:**
- AC1: Route `/levels` oder dedizierter Tab existiert
- AC2: Ansicht gruppiert und rendert Requirements nach dem Feld `level`
- AC3: Zuweisung (allocated-to-owner) ist als anklickbarer Link dargestellt
- AC4: UI ist responsive (mobile-friendly, scrollbar/collapsible)

**Verifikationsmethode:** UI-Test (Component Rendering & Navigation)
**Abgeleitet von:** REQ-L1-063
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

## Erweiterung v9 — REQ-L2-RF-019..021 (Skalierbare Listen-UIs)

> **Datum:** 2026-07-03 | **Quelle:** UI-Befund für Listen-Skalierbarkeit (REQ-L0-038, REQ-L0-039, REQ-L0-040)

---

### REQ-L2-RF-019: Pagination und API-State in Listen-Komponenten

Das ReactFrontendSystem MUSS in allen primären Listenansichten (`RequirementEditors.tsx`, `ArchitectureEditors.tsx`, etc.) die Paginierung unterstützen. Statt `listAll()` aufzurufen, müssen die Query-Parameter (`page`, `search`, `status`, `ordering`) an die React Query Hooks übergeben werden.

**Akzeptanzkriterien:**
- AC1: API-Client und Query-Hooks akzeptieren Paginierungs- und Filter-Parameter.
- AC2: UI rendert Infinite Scroll oder Paginierungs-Buttons, um weitere Seiten abzurufen.
- AC3: API-Responses vom Format `{"results": [...], "count": N}` werden korrekt verarbeitet.

**Verifikationsmethode:** UI-Test (Network-Traffic: nur eine Seite wird beim Mount geladen)
**Abgeleitet von:** REQ-L1-065
**Implementation State:** Backlog
**Review Findings:** `useRequirementsList` ruft derzeit `listAll()` auf.
**Test Status:** Missing

---

### REQ-L2-RF-020: Wiederverwendbare ListToolbar (Search, Filter, Sort)

Das ReactFrontendSystem MUSS eine isolierte, wiederverwendbare `<ListToolbar />`-Komponente bereitstellen, die die Steuerung von Suche, Filter und Sortierung übernimmt und die Parameter über URL-State oder lokalen State an die Listen-Views weitergibt.

**Akzeptanzkriterien:**
- AC1: `<ListToolbar />` enthält ein debounced Search-Input.
- AC2: Enthält Dropdowns/Selects für Filterung nach Status/Kategorie und Sortierung (ASC/DESC).
- AC3: Wird einheitlich in Requirements-, Architecture- und TestCase-Views eingesetzt.

**Verifikationsmethode:** UI-Test (Interaktion mit Toolbar ändert Query-Parameter)
**Abgeleitet von:** REQ-L1-064, REQ-L1-066
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

### REQ-L2-RF-021: Hierarchische Darstellung (Tree-View-Modus)

Das ReactFrontendSystem MUSS für Artefakte mit Parent-Child-Beziehungen (Requirements, ArchitectureElements) einen umschaltbaren Hierarchie-Modus in der Liste bereitstellen. Dieser Modus rendert die Datensätze als Baum (Tree) mit visueller Einrückung und Expand/Collapse-Funktionalität.

**Akzeptanzkriterien:**
- AC1: Toggle-Switch in der ListToolbar zwischen "Flat List" und "Tree View".
- AC2: Tree-View rückt Child-Elemente basierend auf `parent_id` oder TraceLinks visuell ein.
- AC3: Parent-Elemente haben ein Chevron-Icon zum Ein-/Ausklappen ihrer Kinder.

**Verifikationsmethode:** UI-Test (DOM-Struktur prüfen)
**Abgeleitet von:** REQ-L1-067
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

## Erweiterung v10 — REQ-L2-RF-022..024 (Adaptive AI-Native SE UI)

> **Datum:** 2026-07-03 | **Quelle:** Adaptive AI-Native SE Plattform

---

### REQ-L2-RF-022: WebGL-basierter Interaktiver Node-Graph

Das ReactFrontendSystem MUSS eine interaktive Netzwerk-Ansicht (Node Graph) bereitstellen, die die Traceability-Beziehungen (DAG) zwischen allen Entitäten visualisiert. Um Performance bei tausenden Knoten zu gewährleisten, MUSS das Rendering auf WebGL/Canvas basieren (z.B. via React Flow, Cytoscape oder Sigma.js).

**Akzeptanzkriterien:**
- AC1: Neue Route `/graph` rendert das Projekt als Node-Graph.
- AC2: Flüssiges Rendering (30 FPS) bei mindestens 5000 Knoten.
- AC3: Knoten sind interaktiv (Klick öffnet Detail-Kontext, Drag & Drop).

**Verifikationsmethode:** Performance-Profil im Browser mit 5000 Mock-Nodes.
**Abgeleitet von:** REQ-L1-070
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

### REQ-L2-RF-023: Traceability Matrix (TRM) Ansicht

Das ReactFrontendSystem MUSS eine Traceability Matrix (Kreuztabelle) implementieren. Diese Ansicht erlaubt es Nutzern, Lücken in der Traceability zwischen zwei Ebenen (z. B. System Requirements vs. Architecture Elements) schnell zu identifizieren.

**Akzeptanzkriterien:**
- AC1: Neue Route `/trm` rendert eine konfigurierbare Matrix.
- AC2: Nutzer kann Zeilen-Typ (z.B. SyReq) und Spalten-Typ (z.B. ArchE) auswählen.
- AC3: Zellen zeigen Trace-Status an (verknüpft, nicht verknüpft, suspect).

**Verifikationsmethode:** UI-Test (Matrix-Konfiguration und Rendering).
**Abgeleitet von:** REQ-L1-071
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

### REQ-L2-RF-024: Split-Screen Context Panel & KI-Chat

Das ReactFrontendSystem MUSS ein Split-Screen-Layout implementieren, das es erlaubt, links primäre Ansichten (Tree, Node Graph) zu navigieren und rechts ein kontext-sensitives Panel offen zu halten. Dieses Panel MUSS die Metadaten des selektierten Elements und einen KI-Chat enthalten, der kontextbewusst auf das selektierte Element reagiert.

**Akzeptanzkriterien:**
- AC1: Rechte Sidebar (Context Panel) lässt sich ein-/ausblenden.
- AC2: Selektion im Graph/Tree ändert automatisch den Kontext im Panel.
- AC3: Chat-Interface im Panel ist direkt mit dem AI Orchestration Layer verbunden.

**Verifikationsmethode:** UI-Test (Selektion synchronisiert Sidebar-Context).
**Abgeleitet von:** REQ-L1-069, REQ-L1-070
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

## Erweiterung v11 — REQ-L2-RF-025..026 (Striktes Datenmodell & Stage-Gating)

> **Datum:** 2026-07-03 | **Quelle:** User-Request "Deep Dive"

---

### REQ-L2-RF-025: Dynamische UI-Masken für Artefakt-Typen

Das ReactFrontendSystem MUSS im Requirements-Editor und Architecture-Editor die Eingabemasken dynamisch an den Artefakt-Typ (StReq, SyReq, ArchE, TC) anpassen und typspezifische Dropdowns / Slider rendern.

**Akzeptanzkriterien:**
- AC1: Ist der Typ `Stakeholder Requirement`, wird ein Dropdown für MoSCoW-Priority gerendert.
- AC2: Ist der Typ `System Requirement`, wird ein Number-Input (oder Slider) für Complexity (Fibonacci) gerendert.
- AC3: Die globale `UID` und `Version` werden in allen Ansichten prominent und schreibgeschützt (read-only) angezeigt.

**Verifikationsmethode:** UI-Test (Editor-Rendering basierend auf Typ).
**Abgeleitet von:** REQ-L1-076, REQ-L1-077
**Implementation State:** Backlog
**Review Findings:** Bisher nur ein generisches Formular.
**Test Status:** Missing

---

### REQ-L2-RF-026: UI-Feedback für Guardrail-Fehler (Stage-Gating)

Wenn das Backend einen Status-Übergang mit HTTP `409 Conflict` (Stage-Gating-Violation) ablehnt, MUSS das Frontend die im Response enthaltene detaillierte Fehlermeldung direkt am WorkflowState-Dropdown (oder in einer Toast-Notification) gut sichtbar darstellen.

**Akzeptanzkriterien:**
- AC1: Fehler vom Typ "Orphan-Rule-Violation" (z.B. "Fehler: Anforderung hängt in der Luft") werden als rotes Alert-Banner oder Tooltip am Status-Feld gezeigt.
- AC2: Der Status im Dropdown springt visuell auf den alten Wert zurück, um den Fehlerzustand aufzulösen.

**Verifikationsmethode:** UI-Test (Mock Backend 409 Response auf PATCH request).
**Abgeleitet von:** REQ-L1-079
**Implementation State:** Backlog
**Test Status:** Missing

---

## Erweiterung v4 — REQ-L2-RF-028 (System Announcement Banner)

> **Datum:** 2026-07-04 | **Quelle:** REQ-L1-082

---

### REQ-L2-RF-028: Globales System Announcement Banner

Das ReactFrontendSystem MUSS das Announcement Banner global (z.B. oberhalb der Hauptnavigation) anzeigen, wenn über die API ein aktiver Status-Text gemeldet wird. Für Administratoren MUSS es im Einstellungsbereich eine Möglichkeit geben, diesen Text zu ändern und das Banner zu aktivieren/deaktivieren.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Das Banner ist auf allen Seiten sichtbar (Sticky) und kann von normalen Nutzern nicht weggklickt werden.
- [ ] Admin-Einstellungen: Textarea für den Inhalt und ein Toggle (An/Aus).
- [ ] Das Banner pollt nicht, sondern wird beim initialen App-Load (`/api/v1/system/announcement`) geladen oder via SSE aktualisiert.

**Verifikationsmethode:** UI-Test (Admin schaltet Banner ein, User sieht es).
**Verifikiert durch:** L2-RF-Test-028
**Abgeleitet von:** REQ-L1-082

---

*Erstellt durch se-requirements-Agent (L2) | ReqFlow SE-Kaskade | 2026-07-04*
