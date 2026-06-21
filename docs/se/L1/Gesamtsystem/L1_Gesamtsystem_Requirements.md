# L1 Gesamtsystem Requirements

> **Level:** L1 (System-Anforderungen)
> **System:** Gesamtsystem (ReqFlow)
> **Quelle:** docs/KONZEPT.md (final, Runden 1–4), docs/VISION.md
> **Datum:** 2026-06-18
> **Status:** formalisiert

---

## Traceability

- Abgeleitet von: `docs/se/L0/SN_Stakeholder_Needs.md` (REQ-L0-001..015)
- Abgeleitet nach: `docs/se/L1/Gesamtsystem/L2/*System/L2_*System_Requirements.md` (future)

---

## L1 System-Anforderungen (REQ-L1)

### REQ-L1-001: Artefakt-Hierarchie mit beliebiger Tiefe

Das System muss hierarchische Artefakt-Strukturen verwalten, bei denen jeder Knoten
(Artifact) einen optionalen Elternknoten und beliebig viele Kindknoten besitzen kann —
mit vollständigem CRUD — unter der Bedingung, dass Zyklen ausgeschlossen werden.

**Rationale:** Hierarchische Artefaktstruktur ist das strukturelle Fundament für
sowohl Software-Teams (Epic → Story → Task) als auch Systems Engineers
(System → Subsystem → Component).
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Nutzer- oder Agenten-Anfrage (REST / MCP) mit Artefakt-Daten
- Ausgang: Erstelltes / geändertes / gelöschtes Artefakt mit UUID und Hierarchiepfad
**Traceability:** REQ-L0-002, REQ-L0-003

---

### REQ-L1-002: Requirements CRUD mit konfigurierbarem Status-Workflow

Das System muss vollständiges CRUD für Requirements bereitstellen, wobei jedes
Requirement einem konfigurierbaren Workflow-Zustand (WorkflowState) zugeordnet ist
und Status-Übergänge gegen die aktive WorkflowDefinition validiert werden —
unter der Bedingung, dass die Rollen des anfragenden Nutzers geprüft werden.

**Rationale:** Requirements sind die Kernentität; konfigurierbarer Workflow ist die
Grundlage für Configurable Rigor und ersetzt den hartcodierten status-Enum.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: CRUD-Anfrage mit Requirement-Daten, Workflow-State-Übergang, optionalem change_reason
- Ausgang: Requirement mit aktuellem WorkflowState und Audit-History
**Traceability:** REQ-L0-002, REQ-L0-005

---

### REQ-L1-003: Traceability-Engine mit bidirektionalen Links

Das System muss TraceLinks zwischen Requirements, ArchitectureElements und TestCases
verwalten — mit den Link-Typen parent-child, derives-from, satisfies, verifies, implements,
refines — und Upstream/Downstream-Queries in unter 200ms für bis zu 10.000 Items
beantworten.

**Rationale:** Bidirektionale Traceability ist Kernfunktion für Impact-Analysen,
Coverage-Reports und AI-gestützte Konsistenz-Prüfungen.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: TraceLink-Erstellungs- oder Query-Anfrage mit Source/Target-IDs und Link-Type
- Ausgang: TraceLink-Liste oder Upstream/Downstream-Graph mit Typ-Annotation
**Traceability:** REQ-L0-003

---

### REQ-L1-004: ArchitectureElement als eigenständiger, schreibbarer Artefakttyp

Das System muss Architektur-Elemente (Component, Interface, Subsystem, Layer, Module)
als eigenständige, versionierte Entitäten verwalten — mit vollständigem CRUD,
konfigurierbarem Workflow-Zustand und Verknüpfung zu Requirements — unabhängig
vom Artifact-Typ.

**Rationale:** Architektur-Elemente als eigenständiger Typ ermöglicht strukturierte
Architektur-Verwaltung und vollständigen MCP-Zugriff für Architektur-Agenten.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: CRUD-Anfrage mit ArchitectureElement-Daten (element_type, title, description)
- Ausgang: ArchitectureElement mit UUID, WorkflowState, verknüpften TraceLinks
**Traceability:** REQ-L0-003

---

### REQ-L1-005: MCP Server mit vollständigem Read/Write-Zugriff auf alle Artefakttypen

Das System muss einen MCP Server bereitstellen, der alle 20 Tools
(requirement.*, architecture.*, test.*, artifact.*, traceability.*, workspace.*)
mit vollständigem Lese- und Schreibzugriff implementiert — unter der Bedingung,
dass jede schreibende Operation im Audit-Log erfasst wird.

**Rationale:** MCP ist die primäre Schnittstelle für AI-Agenten; vollständiger
Read/Write-Zugriff ist Voraussetzung für alle primären AI-Workflows.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: MCP-Tool-Aufruf mit Tool-Name, Parametern und API-Key
- Ausgang: Strukturierte Tool-Response (JSON); Audit-Log-Eintrag bei Schreiboperationen
**Traceability:** REQ-L0-001, REQ-L0-012

---

### REQ-L1-006: REST API mit OpenAPI-Spezifikation für alle Entitäten

Das System muss eine vollständige REST API mit CRUD-Unterstützung für alle Entitäten,
Token-basierter Authentifizierung (Bearer Token / API Keys) und auto-generierter
OpenAPI-Spezifikation bereitstellen — mit API-Antwortzeiten unter 200ms für
Standard-Queries bei bis zu 10.000 Requirements.

**Rationale:** REST ist die gleichrangige zweite Schnittstelle neben MCP; OpenAPI
ermöglicht Typ-sichere Client-Generierung und Integration-Tests.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: HTTP-Anfrage mit Bearer Token / API Key, JSON-Body
- Ausgang: JSON-Response, HTTP-Statuscodes, OpenAPI-Spec-Endpunkt
**Traceability:** REQ-L0-001, REQ-L0-012

---

### REQ-L1-007: Configurable-Rigor-Presets (Minimal / Standard / Extended)

Das System muss drei konfigurierbare SE-Tiefe-Presets auf Workspace-Ebene bereitstellen,
die Pflichtfelder, sichtbare Funktionen, Baseline-Scope und Workflow-Konfigurierbarkeit
steuern — ohne Datenmigration beim Wechsel zwischen Presets in aufsteigender Richtung.

**Rationale:** Configurable Rigor ist das zentrale Differenzierungsmerkmal;
ein gemeinsames Datenmodell mit konfigurierter Sichtbarkeit vermeidet
Zielgruppen-spezifische Code-Pfade.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Preset-Konfiguration (JSON) auf Workspace-Ebene via API oder UI
- Ausgang: Workspace mit aktiven Preset-Regeln; UI blendet Funktionen ein/aus
**Traceability:** REQ-L0-002

---

### REQ-L1-008: Multi-Level-Baselines (Dokument / Projekt / Global)

Das System muss unveränderliche, benannte Baselines auf drei Scope-Ebenen erstellen
können — Dokument (ab Standard-Preset), Projekt (ab Standard-Preset),
Global/Instanz (nur Extended-Preset) — wobei jede Baseline einen JSON-Snapshot
aller betroffenen Item-IDs und Versionen enthält.

**Rationale:** Baselines sind Must-Have für die SE-Zielgruppe und die Grundlage
für Compliance-Nachweise; drei Ebenen decken alle Übergabe-Szenarien ab.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Baseline-Erstellungsanfrage mit Scope, Name und optionaler Beschreibung
- Ausgang: Unveränderliche Baseline mit JSON-Snapshot und Erstellungszeitpunkt
**Traceability:** REQ-L0-004

---

### REQ-L1-009: Konfigurierbarer Item-Level-Workflow mit Audit-Trail

Das System muss WorkflowDefinitions pro Item-Typ (Requirement, ArchitectureElement,
TestCase) verwalten, State-Übergänge gegen erlaubte Rollen und change_reason-Pflicht
validieren und jeden Übergang mit User, Zeitstempel und Begründung in der
WorkflowState.history protokollieren.

**Rationale:** Konfigurierbarer Workflow ist die Grundlage für Approval-Gates
im Extended-Preset und für spätere Compliance-Nachweise; Audit-Trail ist
nicht-verhandelbar für regulierte Umgebungen.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Workflow-Transition-Anfrage mit Item-ID, Ziel-State, optionalem change_reason, Nutzer-Kontext
- Ausgang: Aktualisierter WorkflowState mit History-Eintrag; Fehler bei unerlaubter Transition
**Traceability:** REQ-L0-005

---

### REQ-L1-010: Rollenbasierte Zugriffskontrolle (Admin, Editor, Viewer, Approver)

Das System muss vier Rollen (Admin, Editor, Viewer, Approver) auf Workspace-Ebene
verwalten, wobei die Approver-Rolle nur im Extended-Preset aktiv ist und
Workflow-Transitions gegen die Rollen des anfragenden Nutzers geprüft werden.

**Rationale:** RBAC ist Voraussetzung für Approval-Workflows, Compliance-Szenarien
und sichere MCP-Schreibzugriffe.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Authentifizierungstoken (Bearer / API Key) mit Nutzer-Kontext
- Ausgang: Berechtigungsentscheid (allow/deny) pro Operation und Ressource
**Traceability:** REQ-L0-005

---

### REQ-L1-011: Vollständiger Audit-Trail für alle Änderungen

Das System muss alle Änderungen an Requirements, ArchitectureElements, TestCases
und TraceLinks mit created_by, created_at, modified_by, modified_at, version und
change_reason (wo konfiguriert) protokollieren — einschließlich aller MCP-Schreiboperationen
mit Agent-Client-Identität und API-Key.

**Rationale:** Vollständige Auditierbarkeit ist explizite Non-Functional-Anforderung;
MCP-Audit-Log ist Voraussetzung für sicheren Agenten-Schreibzugriff.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Jede schreibende Operation (REST / MCP) mit Nutzer- oder Agenten-Kontext
- Ausgang: Audit-Log-Eintrag; Entität mit aktualisierten Audit-Feldern
**Traceability:** REQ-L0-011

---

### REQ-L1-012: Testmanagement mit Coverage-Tracking

Das System muss Testfälle (Unit, Integration, System, Acceptance) anlegen,
mit Requirements verknüpfen, Test-Status verwalten (Passed/Failed/Not Run)
und eine Coverage-Übersicht bereitstellen, die anzeigt, welche Requirements
mindestens einen verknüpften Testfall haben.

**Rationale:** Testmanagement ist Teil des v1-Funktionsumfangs; Coverage-Tracking
ist Grundlage für AI-gestützte Test-Lücken-Analyse.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: TestCase-CRUD-Anfrage; TraceLink-Anfrage (verifies) zwischen TestCase und Requirement
- Ausgang: TestCase mit WorkflowState; Coverage-Report (Requirement → Test-Abdeckung)
**Traceability:** REQ-L0-003

---

### REQ-L1-013: LLM-Capabilities als konfigurierbare, optionale Features

Das System muss LLM-gestützte Capabilities (mindestens: Validierung via requirement.validate,
Zerlegungsunterstützung via requirement.decompose) als optional aktivierbare Features
implementieren, wobei der LLM-Anbieter und API-Key pro Deployment konfigurierbar sind
und das System ohne LLM-Zugang vollständig funktionsfähig bleibt.

**Rationale:** LLM als pluggable Capability ist AI-native Dimension 1; Deployment ohne
LLM-Zugang darf keine Kernfunktionalität verlieren (Self-Hosted-Zielgruppe).
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: LLM-Capability-Aufruf (requirement.validate, requirement.decompose) mit Artefakt-ID
- Ausgang: Strukturiertes LLM-Ergebnis (Score + Vorschläge) oder Fehler "LLM nicht konfiguriert"
**Traceability:** REQ-L0-007

---

### REQ-L1-014: Konfigurierbare Terminologie-Profile (Dev-Modus / SE-Modus)

Das System muss mindestens zwei vordefinierte Terminologie-Profile (Dev-Modus, SE-Modus)
auf Workspace-Ebene unterstützen, wobei ein Profilwechsel ausschließlich Labels und
UI-Texte ändert und keine Datenbank-Schema-Änderung oder Datenmigration erfordert.

**Rationale:** Terminologie-Flexibilität ohne Datenverlust ist das Fundament der
Dual-Zielgruppen-Strategie; API und MCP nutzen immer generische Entitätsnamen.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Profil-Wechsel-Anfrage mit Bestätigung
- Ausgang: Workspace mit neuem aktiven Profil; UI-Labels aktualisiert; API-Response unverändert
**Traceability:** REQ-L0-010

---

### REQ-L1-015: Multi-Tenancy-Vorbereitung mit Row-Level-Isolation

Das System muss alle Entitäten mit einem tenant-Fremdschlüssel versehen und
alle Datenbankabfragen automatisch mit einem tenant_id-Filter via Custom Django Manager
und Middleware ausführen — sodass in v1 genau ein Default-Tenant existiert und
die spätere Aktivierung weiterer Tenants keine Datenmigration erfordert.

**Rationale:** Row-Level-Isolation ist Voraussetzung für den v2-SaaS-Betrieb;
Schema-per-Tenant wurde bewusst abgelehnt wegen zu hohem Overhead.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Jede API-Anfrage mit Authentifizierungstoken (Tenant-Extraktion aus JWT/API-Key)
- Ausgang: Gefilterte Ergebnisse exklusiv für den aktiven Tenant
**Traceability:** REQ-L0-008

---

### REQ-L1-016: Zweisprachige Benutzeroberfläche (Deutsch und Englisch)

Das System muss alle UI-Texte und Backend-Fehlermeldungen in Deutsch und Englisch
bereitstellen, wobei fehlende Translation-Keys als Build-Fehler behandelt werden
(Lint-Regel) und die Sprache pro Nutzer-Präferenz umschaltbar ist.

**Rationale:** Duale Marktausrichtung DE/EN ist eine v1-Entscheidung; nachträgliche
i18n-Integration ist teurer als proaktive Translation-Key-Nutzung.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Nutzer-Sprachpräferenz (Accept-Language Header oder Profil-Setting)
- Ausgang: UI und API-Fehlermeldungen in der gewählten Sprache
**Traceability:** REQ-L0-009

---

### REQ-L1-017: React-UI mit Dashboard, Editor und Navigations-Komponenten

Das System muss eine React-Frontend-Anwendung bereitstellen mit: Dashboard
(Projektübersicht, offene Punkte), Requirements-Editor (Inline-Editing, Markdown),
Architecture-Editor, Artefakt-Navigation (Baumstruktur), Traceability-Anzeige
und Workspace-Profil-Konfiguration.

**Rationale:** UI ist Kernbestandteil von v1; manuelle Benutzer sind gleichwertig
zur MCP-Agenten-Schnittstelle.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Nutzerinteraktion (Browser), API-Responses vom Backend
- Ausgang: Gerenderte UI-Komponenten; REST-API-Aufrufe an Backend
**Traceability:** REQ-L0-012

---

### REQ-L1-018: Docker-Compose-Deployment für Self-Hosted-Betrieb

Das System muss vollständig via Docker Compose deploybar sein — Backend (Django),
Frontend (React), Datenbank (PostgreSQL) — ohne externe Cloud-Abhängigkeiten,
sodass eine Produktionsinstanz mit einem einzigen `docker-compose up` gestartet
werden kann.

**Rationale:** Self-Hosted-only ist die v1-Deployment-Entscheidung; Docker Compose
ist der Standard-Einstieg für die Zielgruppe (Developer-affine Teams).
**Domain:** system
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Docker-Compose-Konfiguration, Umgebungsvariablen (LLM-API-Key, DB-Credentials)
- Ausgang: Laufende ReqFlow-Instanz auf dem Host-System
**Traceability:** REQ-L0-006

---

### REQ-L1-019: Export in JSON und CSV für alle Entitäten

Das System muss Export-Funktionen für Requirements, ArchitectureElements, TestCases
und TraceLinks in JSON und CSV bereitstellen — mit dem aktiven Terminologie-Profil
als Metadatum im Export.

**Rationale:** Export ist explizites Must-Have für v1; ermöglicht Integration mit
externen Tools und ist Voraussetzung für spätere ReqIF-Unterstützung.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Export-Anfrage mit Scope (Workspace / Artefakt), Format (JSON / CSV)
- Ausgang: Datei-Download (JSON oder CSV) mit allen Entitäten und Metadaten
**Traceability:** REQ-L0-012

---

### REQ-L1-020: Volltextsuche über alle Artefakttypen

Das System muss eine artefakttyp-übergreifende Volltextsuche über Requirements,
ArchitectureElements und TestCases bereitstellen — via UI und via MCP-Tool
(artifact.search) — mit Ergebnissen in unter 500ms für bis zu 10.000 Items.

**Rationale:** Volltextsuche ist expliziter v1-Bestandteil; artifact.search als MCP-Tool
deckt den häufigen Agenten-Anwendungsfall ab, wenn der Artefakttyp unbekannt ist.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Suchanfrage (Query-String, optionaler Typ-Filter, Workspace-Filter)
- Ausgang: Gemischte Ergebnisliste mit Artefakttyp-Annotation, sortiert nach Relevanz
**Traceability:** REQ-L0-001

---

### REQ-L1-021: CSV-Bulk-Import für Requirements und Artefakte

Das System MUSS einen CSV-Import für Requirements, ArchitectureElements und TestCases
bereitstellen, der Validierung gegen das Datenmodell durchführt, Fehler mit Zeilennummer
zurückmeldet und erfolgreich importierte Items mit regulären UUIDs versieht — unter der
Bedingung, dass das CSV-Format dem dokumentierten Schema entspricht.

**Rationale:** CSV-Bulk-Import ist ein explizites Must-Have in KONZEPT.md §4.6; ermöglicht
die Migration bestehender Anforderungsdaten ohne manuelle Neueingabe.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: CSV-Datei mit Anforderungen/Artefakten gemäß dokumentiertem Schema
- Ausgang: Import-Ergebnisbericht (erfolgreich importierte Items, Fehler mit Zeilennummer)
**Traceability:** REQ-L0-013

---

### REQ-L1-022: GitHub-Integration für Requirement-Issue/PR-Verknüpfung

Das System SOLL die Verknüpfung von Requirements mit GitHub Issues und Pull Requests
unterstützen — bidirektional abrufbar aus ReqFlow und via GitHub — unter der Bedingung,
dass ein GitHub-Token konfiguriert ist und die Ziel-Repositories zugreifbar sind.

**Rationale:** GitHub-Integration ist ein Should-Have in KONZEPT.md §4.6; die Zielgruppe
(Developer-affine Teams) erwartet native Integration in ihren Entwicklungs-Workflow.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: GitHub-Token-Konfiguration; Verknüpfungsanfrage mit Requirement-ID und GitHub-Issue/PR-URL
- Ausgang: Verknüpfte GitHub-Issues/PRs in der Requirement-Detailansicht; ReqFlow-Referenz in GitHub (via Webhook oder API)
**Traceability:** REQ-L0-014

---

### REQ-L1-023: PDF-Report-Export für Anforderungsdokumente und Traceability-Matrizen

Das System SOLL Anforderungsdokumente und Traceability-Matrizen als PDF-Berichte exportieren
können — inklusive Metadaten (Version, Baseline-Referenz, Workflow-State, Audit-History) —
sodass Teams in regulierten Umgebungen audit-dokumentierbare Übergaben erzeugen können.

**Rationale:** PDF-Reports sind ein Should-Have in KONZEPT.md §4.6; die SE-Zielgruppe
benötigt dokumentierbare Übergaben für Reviews und Compliance-Nachweise (§8.1).
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: Report-Anfrage mit Scope (Workspace/Artefakt/Baseline), Report-Typ (Anforderungsdokument/Traceability-Matrix), Format (PDF)
- Ausgang: PDF-Datei mit formatiertem Bericht, Metadaten und Traceability-Matrix
**Traceability:** REQ-L0-015

---

### REQ-L1-024: Webhook-Support für Anforderungsänderungen

Das System SOLL konfigurierbare Webhooks für Ereignis-Typen (Requirement erstellt, geändert,
Status-Übergang, Baseline erstellt) bereitstellen, die bei Eintreten des Ereignisses einen
HTTP-POST-Request an eine konfigurierte URL mit JSON-Payload senden — unter der Bedingung,
dass die Ziel-URL erreichbar ist und der Webhook aktiviert ist.

**Rationale:** Webhook-Support ist ein Should-Have in KONZEPT.md §4.3; ermöglicht externe
Systemen (CI/CD, Slack, Notification-Services) auf Anforderungsänderungen zu reagieren.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: Webhook-Konfiguration (URL, Ereignis-Typ, Secret); auslösendes Systemereignis
- Ausgang: HTTP-POST-Request an konfigurierte URL mit JSON-Payload (Ereignis-Typ, betroffene Entity-ID, Timestamp)
**Traceability:** REQ-L0-012, REQ-L0-014

---

### REQ-L1-025: Transaktionale Konsistenz (ACID)

Das System MUSS Datenänderungen atomar und konsistent persistieren; bei Fehlern dürfen
keine partiellen Schreibvorgänge zurückbleiben (ACID).

**Rationale:** Datenkonsistenz ist eine fundamentale Non-Functional-Anforderung;
partielle Schreibvorgänge können zu inkonsistenten Artefakt-Hierarchien,
TraceLinks und Workflow-States führen.
**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Jede schreibende Operation (REST / MCP) auf Entitäten oder TraceLinks
- Ausgang: Atomar persistierte Änderung oder vollständiges Rollback bei Fehler

---

### REQ-L1-026: Übergreifende Performance-Anforderung

Das System MUSS unter normaler Last (bis zu 50 gleichzeitige Nutzer, 10.000 Requirements)
für 95 % der API-Standard-Requests eine Antwortzeit von < 200 ms und für Volltextsuchen
< 500 ms garantieren.

**Rationale:** Performance ist eine übergreifende Non-Functional-Anforderung, die
alle Schnittstellen (REST, MCP, UI) betrifft und für die Zielgruppe
(Developer-affine Teams, SE-Teams) entscheidend für die Akzeptanz ist.
**Domain:** system
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: API-Requests (REST / MCP) unter definierter Last (50 gleichzeitige Nutzer, 10.000 Requirements)
- Ausgang: Responses innerhalb der definierten Latenz-SLAs (95. Perzentil)

---

## Erste L2-Verfeinerung (Subsystem-Ebene)

> Nur für Bereiche, wo aus dem Konzept klare Subsystem-Grenzen ableitbar sind.
> Keine vollständige L3-Zerlegung.

---

### L2: MCP Server — Subsystem-Anforderungen

#### L2-MCP-01: Requirements-Tool-Gruppe (6 Tools)

Das MCP-Subsystem muss die Tools requirement.get, requirement.query,
requirement.create, requirement.update, requirement.decompose und
requirement.validate implementieren, wobei requirement.validate nur bei
aktiviertem LLM-Provider ausführbar ist und graceful einen Fehler zurückgibt,
falls kein LLM konfiguriert ist.

**Rationale:** Die sechs Requirements-Tools decken den primären AI-Workflow
"Context-Aware Code Generation" ab.

#### L2-MCP-02: Architecture-Tool-Gruppe (5 Tools)

Das MCP-Subsystem muss die Tools architecture.get, architecture.query,
architecture.create, architecture.update und architecture.link implementieren,
mit vollständigem Audit-Log für jede schreibende Operation.

**Rationale:** Architektur-Tools sind neu in Runde 4 und die Grundlage für
Architecture-Requirements-Alignment-Workflows.

#### L2-MCP-03: Test-Tool-Gruppe (5 Tools)

Das MCP-Subsystem muss die Tools test.get, test.query, test.create,
test.update und test.link implementieren, sodass Test-Agenten Coverage-Analysen
durchführen und Test-Status nach Ausführung schreiben können.

**Rationale:** Test-Tools ermöglichen automatisierte Coverage-Analyse als AI-Workflow.

#### L2-MCP-04: Übergreifende Tools (4 Tools)

Das MCP-Subsystem muss traceability.query, artifact.search, artifact.get_tree
und workspace.get_context implementieren, wobei workspace.get_context als
primärer Orientierungspunkt für AI-Agenten beim Sitzungsstart dient.

**Rationale:** Übergreifende Tools vermeiden redundante Einzel-Calls und sind
der Einstiegspunkt für Agenten ohne Vorwissen über den Workspace-Zustand.

---

### L2: WorkflowEngine — Subsystem-Anforderungen

#### L2-WF-01: WorkflowDefinition-Verwaltung

Das WorkflowEngine-Subsystem muss WorkflowDefinitions pro Item-Typ und Workspace
verwalten, vordefinierte Default-Workflows für alle drei Presets bereitstellen
und Workflow-Änderungen gegen laufende WorkflowState-Instanzen validieren.

**Rationale:** WorkflowEngine ist das Herzstück von Configurable Rigor auf Item-Ebene.

#### L2-WF-02: Transition-Validierung mit Rollen-Check

Das WorkflowEngine-Subsystem muss bei jedem State-Übergang prüfen, ob die Rolle
des anfragenden Nutzers in den allowed_roles der Transition enthalten ist und
ob change_reason erforderlich und vorhanden ist — mit sofortigem Fehler
bei Regelverletzung.

**Rationale:** Rollen-gebundene Übergänge sind die Grundlage für formale
Approval-Gates im Extended-Preset.

---

### L2: Baseline-Engine — Subsystem-Anforderungen

#### L2-BL-01: Scope-Auflösung und Snapshot-Erstellung

Das Baseline-Subsystem muss beim Erstellen einer Baseline alle betroffenen
Item-IDs und Versionen für den angeforderten Scope (document / project / global)
ermitteln und atomar als JSON-Snapshot persistieren — unveränderlich nach Erstellung.

**Rationale:** Atomare, unveränderliche Snapshots sind die Voraussetzung für
reproduzierbare Anforderungsstände.

#### L2-BL-02: Baseline-Vergleich

Das Baseline-Subsystem muss den Vergleich zweier Baselines desselben oder
kompatiblen Scopes unterstützen und eine Diff-Darstellung liefern (hinzugefügte,
geänderte, gelöschte Items mit Versions-Delta).

**Rationale:** Baseline-Vergleiche sind das operative Werkzeug für
Requirements-Reviews und Change-Management.

---

### L2: Tenant-Isolation — Subsystem-Anforderungen

#### L2-TI-01: Automatischer Tenant-Filter via Custom Django Manager

Das Tenant-Isolation-Subsystem muss sicherstellen, dass jede Datenbankabfrage
automatisch mit einem tenant_id-Filter versehen wird — erzwungen durch einen
Custom Django Manager auf allen Entitäten — sodass eine vergessene manuelle
Filterung keine Tenant-Datenleck-Lücke erzeugt.

**Rationale:** Row-Level-Isolation via Custom Manager ist robuster als manuelle
Filter-Disziplin; Grundlage für spätere Multi-Tenancy-Aktivierung.

---

## Offene Punkte (aus KONZEPT.md Abschnitt 11.1 — Klärungsbedarf)

> Diese Punkte beeinflussen Datenmodell und API und müssen vor der Architektur-Zerlegung
> entschieden werden.

**OP-01 — LLM-Capabilities-Scope:**
Welche der vier LLM-Capabilities (Generierung, Validierung, Decomposition,
Test-Ableitung/Konsistenz-Checks) werden in v1 operativ implementiert?
Empfehlung aus KONZEPT.md: Validierung + Decomposition.
*Status: Pending Stakeholder-Entscheidung*
*Auswirkung auf: REQ-L1-013, L2-MCP-01*

**OP-02 — Preset-Downgrade-Verhalten:**
Was passiert mit Baselines, Approved-Items und Workflows beim Wechsel auf eine
niedrigere SE-Stufe (z.B. Extended → Standard)?
*Status: Undefined — kein Verhalten spezifiziert*
*Auswirkung auf: REQ-L1-007, REQ-L1-008, L2-BL-01*

**OP-03 — Multi-Tenancy-Isolation:**
Wie wird die Tenant-Isolation bei aktiviertem Multi-Tenancy durchgesetzt
(Application-Level vs. Database-Level)? Welche Isolation-Strenge ist erforderlich?
*Status: Pending Decision*
*Auswirkung auf: REQ-L1-015, L2-TI-01*

---

## Traceability-Abschnitt: REQ-L1 → REQ-L0

| REQ-L1 | Abgedeckte REQ-L0 |
|---------|--------------|
| REQ-L1-001 | REQ-L0-002, REQ-L0-003 |
| REQ-L1-002 | REQ-L0-002, REQ-L0-005 |
| REQ-L1-003 | REQ-L0-003 |
| REQ-L1-004 | REQ-L0-003 |
| REQ-L1-005 | REQ-L0-001, REQ-L0-012 |
| REQ-L1-006 | REQ-L0-001, REQ-L0-012 |
| REQ-L1-007 | REQ-L0-002 |
| REQ-L1-008 | REQ-L0-004 |
| REQ-L1-009 | REQ-L0-005 |
| REQ-L1-010 | REQ-L0-005 |
| REQ-L1-011 | REQ-L0-011 |
| REQ-L1-012 | REQ-L0-003 |
| REQ-L1-013 | REQ-L0-007 |
| REQ-L1-014 | REQ-L0-010 |
| REQ-L1-015 | REQ-L0-008 |
| REQ-L1-016 | REQ-L0-009 |
| REQ-L1-017 | REQ-L0-012 |
| REQ-L1-018 | REQ-L0-006 |
| REQ-L1-019 | REQ-L0-012 |
| REQ-L1-020 | REQ-L0-001 |
| REQ-L1-021 | REQ-L0-013 |
| REQ-L1-022 | REQ-L0-014 |
| REQ-L1-023 | REQ-L0-015 |
| REQ-L1-024 | REQ-L0-012, REQ-L0-014 |
| REQ-L1-025 | REQ-L0-002 |
| REQ-L1-026 | REQ-L0-002 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade | 2026-06-18*
*Nächster Schritt: L2-Anforderungen in docs/se/L1/Gesamtsystem/L2/*System/L2_*System_Requirements.md*

---

## Offene L1-Ableitungen (REQ-L0-016..021)

> **Quelle:** se-requirements-Agent | HOFF-20260621-002 | 2026-06-21
>
> Diese Anforderungen sind neu und noch nicht in die L2-Zerlegung eingegangen.
> Sie müssen durch den se-architect formalisiert und auf L2-Subsysteme heruntergebrochen werden.
> Status: **OFFEN — ausstehende Architektur-Zerlegung**

---

### REQ-L1-027: Integrierte Diagramm- und Grafik-Verwaltung

Das System muss Diagramme (mindestens 3 Typen: Blockdiagramm, Flussdiagramm,
Kontextdiagramm) als eigenständige, versionierte Artefakte verwalten, die direkt
mit Requirements oder ArchitectureElements verknüpft werden können — abrufbar via
UI und MCP (artifact.get) — wobei jede Diagramm-Änderung eine neue Version erzeugt.

**Rationale:** Integrierte Diagramme eliminieren Medienbrüche zu externen Zeichenprogrammen
und stellen Traceability zwischen grafischen Modellen und textuellen Anforderungen her.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: Diagramm-CRUD-Anfrage mit Typ, Inhalt (strukturierter Payload), optionaler Verknüpfung zu Artefakt-ID
- Ausgang: Versioniertes Diagramm mit UUID, TraceLinks zu verknüpften Artefakten; renderbare Darstellung in UI
**Traceability:** REQ-L0-016

---

### REQ-L1-028: ICD-Verwaltung mit Versionierung und Design-by-Contract

Das System muss Schnittstellen zwischen ArchitectureElements als versionierte
Interface Control Documents (ICDs) verwalten können — mit Feldern für Richtung,
Typ, semantische Beschreibung, Vorbedingungen, Nachbedingungen und Invarianten —
wobei jede ICD-Version unveränderlich ist und inkompatible Änderungen erkannt
und als Breaking-Change-Warnung gemeldet werden.

**Rationale:** ICDs sind in der SE-Praxis bindende Verträge zwischen Subsystemen.
Versionierung und Kompatibilitätsprüfung sind Voraussetzung für inkrementelle
Integration und formale Übergaben.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: ICD-CRUD-Anfrage mit Schnittstellenparametern, source-ArchitectureElement-ID, target-ArchitectureElement-ID
- Ausgang: Versionierter ICD-Eintrag; Breaking-Change-Warnung bei inkompatiblen Änderungen; Baseline-fähig
**Traceability:** REQ-L0-017

---

### REQ-L1-029: ADR-, Risiko- und Issue-Verwaltung mit Artefakt-Verknüpfung

Das System muss Architekturentscheidungen (ADRs), Risiken und Issues als eigenständige
Artefakttypen mit konfigurierbaren Workflow-Zuständen verwalten und vollständig
mit Requirements, ArchitectureElements und TestCases verknüpfen können — via REST
und MCP mit vollständigem CRUD.

**Rationale:** ADRs, Risiken und Issues sind integrale SE-Artefakte. Ohne Verknüpfung
mit Anforderungen und Architektur fehlen Kontext, Rückverfolgbarkeit und
die Grundlage für Safety-Cases und Compliance-Audits.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: CRUD-Anfrage für ADR (Kontext, Entscheidung, Konsequenzen, Status) / Risiko (Wahrscheinlichkeit, Auswirkung, Mitigation) / Issue (Typ, Priorität)
- Ausgang: Artefakt mit UUID, WorkflowState, TraceLinks zu verknüpften Anforderungen/Architekturelementen
**Traceability:** REQ-L0-018

---

### REQ-L1-030: Projektübergreifende Traceability (Cross-Projekt-Links)

Das System muss TraceLinks zwischen Artefakten aus verschiedenen Projekten innerhalb
derselben Tenant-Instanz unterstützen — mit vollständiger Auflösung in
Upstream/Downstream-Queries und Impact-Analysen — unter der Bedingung, dass
Cross-Tenant-Links ausgeschlossen bleiben.

**Rationale:** Rekursive SE-Zerlegung über mehrere Projekte erfordert projektübergreifende
Traceability. Ohne sie endet die Zerlegungskette an der Projektgrenze und die
systemische Kontinuität von SN bis Test ist nicht nachweisbar.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: TraceLink-Erstellungsanfrage mit Source-Artefakt-ID (Projekt A) und Target-Artefakt-ID (Projekt B), Link-Typ
- Ausgang: Cross-Projekt-TraceLink; erweiterte Upstream/Downstream-Graph-Antwort mit Cross-Projekt-Annotation
**Traceability:** REQ-L0-019

---

### REQ-L1-031: SE-Prozess-Metrikmodul

Das System muss SE-Prozessmetriken berechnen und bereitstellen — mindestens:
Requirements Volatility (Änderungsrate je Anforderung in konfigurierbarem Zeitraum),
Traceability Coverage (Anteil verknüpfter Requirements), Workflow-Lücken (Items
ohne vollständige Workflow-Historie) und offene Risiken nach Schweregrad —
abrufbar via Dashboard und REST-API-Endpunkt.

**Rationale:** Metrikenbasiertes Steuern ist ein explizites SE-Prinzip. Ohne Metriken
fehlt die Datengrundlage für Prozesssteuerung und Qualitätsnachweise.
**Domain:** software
**Priorität:** desired
**Externe Interfaces:**
- Eingang: Metrikanfrage mit Workspace-ID, Zeitraum, optionalem Scope-Filter via GET /metrics/workspace/{id}
- Ausgang: Strukturierter JSON-Metrikbericht; Dashboard-Darstellung in UI; konfigurierbare Schwellwert-Warnungen
**Traceability:** REQ-L0-020

---

### REQ-L1-032: Resilienz-Anforderung — Asynchrone Entkopplung und Graceful Degradation

Das System muss sicherstellen, dass alle optionalen Subsystem-Aufrufe (LLM-Adapter,
Webhook-Dispatcher, GitHub-Integration) über asynchrone Mechanismen mit konfigurierbarem
Timeout und mindestens einem Retry ausgeführt werden — und dass der Kern
(CRUD, Traceability, Baselines) bei Ausfall optionaler Subsysteme mit einer
Kernverfügbarkeit von > 99,5 % erhalten bleibt.

**Rationale:** Resilienz durch zeitliche Entkopplung ist ein übergreifendes Systemprinzip.
Ohne Graceful Degradation verlieren synchron-koppelnde Systeme bei jedem Teilausfall
vollständig ihre Verfügbarkeit — inakzeptabel für Produktionsumgebungen.
**Domain:** system
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Systemereignis, der ein optionales Subsystem triggert (LLM-Aufruf, Webhook, GitHub-Sync)
- Ausgang: Ergebnis des optionalen Subsystems bei Erfolg; Graceful-Degradation-Response + Audit-Log-Eintrag bei Fehler
**Traceability:** REQ-L0-021

---

## Erweiterter Traceability-Abschnitt: REQ-L1-027..032 → REQ-L0

| REQ-L1 | Abgeleitet von REQ-L0 |
|---------|----------------------|
| REQ-L1-027 | REQ-L0-016 |
| REQ-L1-028 | REQ-L0-017 |
| REQ-L1-029 | REQ-L0-018 |
| REQ-L1-030 | REQ-L0-019 |
| REQ-L1-031 | REQ-L0-020 |
| REQ-L1-032 | REQ-L0-021 |

---

*Erweiterung durch se-requirements-Agent | HOFF-20260621-002 | 2026-06-21*
