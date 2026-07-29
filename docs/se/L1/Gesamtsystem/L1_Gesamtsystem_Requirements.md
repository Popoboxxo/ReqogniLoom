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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Auswahl des synchronen API-Protokolls"
**Externe Interfaces:**
- Eingang: Nutzer- oder Agenten-Anfrage (synchrone Web-API / MCP) mit Artefakt-Daten
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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** MCP Server unterstützt jetzt vollständigen asynchronen Standard (SSE via Redis PubSub) und exportiert alle Tools dynamisch.
**Test Status:** Covered
**Remarks:** GenericCrudToolGroup deckt alle UI-Paritätslücken (Issue, Risk, etc.) ab.

**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: MCP-Tool-Aufruf mit Tool-Name, Parametern und API-Key
- Ausgang: Strukturierte Tool-Response (JSON); Audit-Log-Eintrag bei Schreiboperationen

**Traceability:** REQ-L0-001, REQ-L0-012

---

### REQ-L1-006: Synchrone maschinenlesbare API mit Spezifikation für alle Entitäten

Das System muss eine vollständige synchrone Web-API mit CRUD-Unterstützung für alle Entitäten,
Token-basierter Authentifizierung und auto-generierter,
maschinenlesbarer Schnittstellenspezifikation bereitstellen — mit API-Antwortzeiten unter 200ms für
Standard-Queries bei bis zu 10.000 Requirements.

**Rationale:** Die synchrone Web-API ist die gleichrangige zweite Schnittstelle neben MCP; eine Spezifikation
ermöglicht Typ-sichere Client-Generierung und Integration-Tests.
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** software
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Technologieauswahl für die synchrone Web-API und deren Spezifikationsformat"
**Externe Interfaces:**
- Eingang: API-Anfrage (synchrones Netzwerkprotokoll) mit Token, strukturiertem Payload
- Ausgang: Strukturierte Response, Status-Indikator, Metadaten-Endpunkt für API-Spezifikation

**Traceability:** REQ-L0-001, REQ-L0-012

---

### REQ-L1-007: Configurable-Rigor-Presets (Minimal / Standard / Extended)

Das System muss drei konfigurierbare SE-Tiefe-Presets auf Workspace-Ebene bereitstellen,
die Pflichtfelder, sichtbare Funktionen, Baseline-Scope und Workflow-Konfigurierbarkeit
steuern — ohne Datenmigration beim Wechsel zwischen Presets in aufsteigender Richtung.

**Rationale:** Configurable Rigor ist das zentrale Differenzierungsmerkmal;
ein gemeinsames Datenmodell mit konfigurierter Sichtbarkeit vermeidet
Zielgruppen-spezifische Code-Pfade.
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** software
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Auswahl des synchronen API-Protokolls"
**Externe Interfaces:**
- Eingang: Jede schreibende Operation (synchrone Web-API / MCP) mit Nutzer- oder Agenten-Kontext
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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Profil-Wechsel-Anfrage mit Bestätigung
- Ausgang: Workspace mit neuem aktiven Profil; UI-Labels aktualisiert; API-Response unverändert

**Traceability:** REQ-L0-010

---

### REQ-L1-015: Mandantenfähigkeit ohne spätere Datenmigration

Das System muss Daten mandantenfähig isolieren, sodass Datenabfragen zwingend
auf den Tenant des anfragenden Nutzers beschränkt bleiben. Für v1 muss ein Default-Tenant 
existieren, und die spätere Aktivierung echter Mandantenfähigkeit darf keine 
Datenmigration der Bestandsdaten erfordern.

**Rationale:** Isolation ist Voraussetzung für den v2-SaaS-Betrieb; die konkrete
technische Umsetzung der Datenisolation ist eine Architektur-Entscheidung.
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** system
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Mandantenfähigkeit mit strikter Datenisolation ohne spätere Datenmigration"
**Externe Interfaces:**
- Eingang: Jede Anfrage mit Authentifizierungskontext, aus dem der Tenant ableitbar ist
- Ausgang: Gefilterte Ergebnisse exklusiv für den aktiven Tenant

**Traceability:** REQ-L0-008

---

### REQ-L1-016: Zweisprachige Benutzeroberfläche (Deutsch und Englisch)

Das System muss alle UI-Texte und Backend-Fehlermeldungen in Deutsch und Englisch
bereitstellen, wobei fehlende Translation-Keys als Build-Fehler behandelt werden
(Lint-Regel) und die Sprache pro Nutzer-Präferenz umschaltbar ist.

**Rationale:** Duale Marktausrichtung DE/EN ist eine v1-Entscheidung; nachträgliche
i18n-Integration ist teurer als proaktive Translation-Key-Nutzung.
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** software
**Priorität:** mandatory
**Externe Interfaces:**
- Eingang: Nutzer-Sprachpräferenz (Accept-Language Header oder Profil-Setting)
- Ausgang: UI und API-Fehlermeldungen in der gewählten Sprache

**Traceability:** REQ-L0-009

---

### REQ-L1-017: Grafische Benutzeroberfläche (GUI) für manuelle Workflows

Das System muss eine webbasierte grafische Benutzeroberfläche bereitstellen mit: 
Dashboard (Projektübersicht, offene Punkte), Requirements-Editor (Inline-Editing, Markdown),
Architecture-Editor, Artefakt-Navigation (Baumstruktur), Traceability-Anzeige
und Workspace-Profil-Konfiguration.

**Rationale:** GUI ist Kernbestandteil von v1; manuelle Benutzer sind gleichwertig
zur MCP-Agenten-Schnittstelle. Die Wahl der Frontend-Technologie ist eine Architektur-Entscheidung.
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** software
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Webbasierte GUI für Interaktion mit Systemschnittstellen"
**Externe Interfaces:**
- Eingang: Nutzerinteraktion im Browser
- Ausgang: Visuelle Darstellung von Systemzuständen und Artefakten

**Traceability:** REQ-L0-012

---

### REQ-L1-018: Eigenständiges Deployment für Self-Hosted-Betrieb

Das System muss als self-hosted Anwendung ohne externe Cloud-Abhängigkeiten bereitstellbar
sein. Das Deployment muss über ein standardisiertes, leichtgewichtiges Verfahren
erfolgen, sodass eine Produktionsinstanz durch einen einzigen konsolidierten Startbefehl
hochgefahren werden kann.

**Rationale:** Self-Hosted-only ist die v1-Deployment-Entscheidung; das Deployment
muss für die Zielgruppe (Developer-affine Teams) niederschwellig sein. Die Auswahl 
der Laufzeitumgebung und Bereitstellungstechnologie ist Teil der Architektur.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** system
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Einfaches, lokales Deployment ohne externe Abhängigkeiten"
**Externe Interfaces:**
- Eingang: Konfigurationsdateien, Umgebungsvariablen (LLM-Zugang, DB-Credentials)
- Ausgang: Lauffähige Gesamtsystem-Instanz auf dem Host-System

**Traceability:** REQ-L0-006

---

### REQ-L1-019: Export in JSON und CSV für alle Entitäten

Das System muss Export-Funktionen für Requirements, ArchitectureElements, TestCases
und TraceLinks in JSON und CSV bereitstellen — mit dem aktiven Terminologie-Profil
als Metadatum im Export.

**Rationale:** Export ist explizites Must-Have für v1; ermöglicht Integration mit
externen Tools und ist Voraussetzung für spätere ReqIF-Unterstützung.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** software
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Auswahl des synchronen API-Protokolls"
**Externe Interfaces:**
- Eingang: Jede schreibende Operation (synchrone Web-API / MCP) auf Entitäten oder TraceLinks
- Ausgang: Atomar persistierte Änderung oder vollständiges Rollback bei Fehler

---

### REQ-L1-026: Übergreifende Performance-Anforderung

Das System MUSS unter normaler Last (bis zu 50 gleichzeitige Nutzer, 10.000 Requirements)
für 95 % der API-Standard-Requests eine Antwortzeit von < 200 ms und für Volltextsuchen
< 500 ms garantieren.

**Rationale:** Performance ist eine übergreifende Non-Functional-Anforderung, die
alle Schnittstellen betrifft und für die Zielgruppe
(Developer-affine Teams, SE-Teams) entscheidend für die Akzeptanz ist.
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Domain:** system
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Auswahl des synchronen API-Protokolls"
**Externe Interfaces:**
- Eingang: API-Requests (synchrone Web-API / MCP) unter definierter Last (50 gleichzeitige Nutzer, 10.000 Requirements)
- Ausgang: Responses innerhalb der definierten Latenz-SLAs (95. Perzentil)

---

## Erste L2-Verfeinerung (Subsystem-Ebene)

> Nur für Bereiche, wo aus dem Konzept klare Subsystem-Grenzen ableitbar sind.
> Keine vollständige L3-Zerlegung.

---

### L2: MCP Server — Subsystem-Anforderungen

#### L2-MCP-01: Requirements-Tool-Gruppe (6 Tools)

Das MCP-Subsystem muss die Tools requirement.get, requirement.query,
requirement.create, requirement.update, requirement.decompose, requirement.validate
und requirement.derive bereitstellen. Die Tool-Schaltstellen müssen den MCP
Standard-Methoden (tools/list, tools/call) entsprechen.
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
**Implementation State:** Implemented

#### L2-MCP-03: Test-Tool-Gruppe (5 Tools)

Das MCP-Subsystem muss die Tools test.get, test.query, test.create,
test.update und test.link implementieren, sodass Test-Agenten Coverage-Analysen
durchführen und Test-Status nach Ausführung schreiben können.

**Rationale:** Test-Tools ermöglichen automatisierte Coverage-Analyse als AI-Workflow.
**Implementation State:** Implemented

#### L2-MCP-04: Übergreifende Tools (4 Tools)

Das MCP-Subsystem muss traceability.query, artifact.search, artifact.get_tree
und system.info bereitstellen.

#### L2-MCP-05: GenericCrud-Tool-Gruppe (UI-Parität)

Das MCP-Subsystem muss dynamisch CRUD-Tools für ADRs, Risks, Issues und das Glossary bereitstellen,
um vollständige Parität mit der REST-API zu gewährleisten. Dies erfolgt standardkonform via `tools/call`.

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

#### L2-TI-01: Automatischer Tenant-Filter auf Datenzugriffsebene

Das Tenant-Isolation-Subsystem muss sicherstellen, dass jede Datenabfrage
automatisch mit einem tenant_id-Filter versehen wird — erzwungen durch eine
zentrale Datenzugriffsschicht auf allen Entitäten — sodass eine vergessene manuelle
Filterung keine Tenant-Datenleck-Lücke erzeugt.

**Rationale:** Automatische Isolation auf Datensatz-Ebene in der Datenzugriffsebene ist robuster als manuelle
Filter-Disziplin; Grundlage für spätere Multi-Tenancy-Aktivierung. Die konkrete Technologie wählt der Architekt.

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

## Erweiterung v4 — REQ-L1-081 (PAT Management)

> **Datum:** 2026-07-03 | **Quelle:** REQ-L0-050

---

### REQ-L1-081: Personal Access Token (PAT) Management

Das System MUSS registrierten Benutzern ermöglichen, persönliche Zugriffs-Token (PATs) zu generieren, aufzulisten und zu widerrufen (Revoke). Diese Tokens MÜSSEN für API- und MCP-Zugriffe verwendet werden und MÜSSEN den gleichen Berechtigungsprüfungen (RBAC) unterliegen wie die interaktive Web-Session des zugehörigen Benutzers.

**Implementation State:** Erfüllt durch bestehende Komponenten (COMP-AT-001, ApiKeyViewSet, UserProfileSettings)
**Review Findings:** Deckt sich funktional vollständig mit dem bereits produktiven `ApiKey`-System (REQ-L2-AT-002, REQ-L2-AT-009) — siehe Architektur-Entscheidungen in COMP-AT-006, COMP-RA-007, COMP-RF-006. Kein separater PAT-Mechanismus implementiert, um konkurrierende Bearer-Auth-Pfade zu vermeiden.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [x] UI-Bereich zur Verwaltung der Tokens existiert. → `/profile` (`UserProfileSettings.tsx` + `ApiKeysSection.tsx`), workspace-unabhängig erreichbar über Sidebar-Footer.
- [x] REST API validiert `Authorization: Bearer <Token>` Header. → `AuthenticationService` / `AuthTenancyAuthentication` (COMP-AT-001).
- [x] Zurückgezogene Tokens werden sofort ungültig. → `ApiKey.revoked_at` / `is_active`-Property, geprüft bei jeder Validierung.
- [x] Tokens werden kryptografisch sicher gehasht in der Datenbank gespeichert (kein Klartext-Speicher). → `ApiKey.key_hash` (`sha256:<hex>`), Klartext nur einmalig im Response-Body.

**Verifikationsmethode:** Integrationstest — Token generieren, API-Call ausführen, Revoke, erneuter API-Call (sollte fehlschlagen).
**Verifikiert durch:** L1-SystemAcceptanceTest-081
**Abgeleitet von:** REQ-L0-050 (SN-50)

## Erweiterung v5 — REQ-L1-082 (System Announcement)

> **Datum:** 2026-07-04 | **Quelle:** REQ-L0-051

---

### REQ-L1-082: Global System Announcement

Das System MUSS eine Konfigurationsmöglichkeit bieten, um einen systemweiten Status-Text (Announcement) zu persistieren. Wenn ein Announcement existiert und als "aktiv" markiert ist, MUSS es allen interagierenden Clients zugänglich gemacht werden (Web-UI, REST-API, MCP-Protokoll).

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Globale Persistenz des Status-Textes (z.B. Singleton in der DB).
- [ ] Berechtigung: Nur Administratoren dürfen den Text setzen/aktivieren/deaktivieren.
- [ ] Lesezugriff ist für alle authentifizierten Nutzer und Agenten gestattet.
- [ ] Die UI blendet das Announcement prominent ein, wenn es aktiv ist (Sticky, nicht dismissable).

**Verifikationsmethode:** End-to-End Test — Admin setzt Text, Nutzer sieht Text in UI, Agent liest Text via MCP.
**Verifikiert durch:** L1-SystemAcceptanceTest-082
**Abgeleitet von:** REQ-L0-051 (SN-51)

## Erweiterung v6 — REQ-L1-083 bis 085 (UI/UX Migration)

> **Datum:** 2026-07-04 | **Quelle:** REQ-L0-052 bis 054

---

### REQ-L1-083: Navigation in hierarchischer Baumstruktur

Das System MUSS eine visuelle Navigationskomponente (Tree-View) im Frontend bereitstellen, welche die Artefakte anhand ihrer Traceability-Links (`parent_id`) hierarchisch darstellt.

**Implementation State:** Not Implemented
**Review Findings:** Migration.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Hierarchische Darstellung der Artefakte in der UI.
- [ ] Knoten können durch den Anwender auf- und zugeklappt werden.

**Verifikationsmethode:** UI-Test der Navigation.
**Verifikiert durch:** L1-SystemAcceptanceTest-083
**Abgeleitet von:** REQ-L0-052 (SN-52)

---

### REQ-L1-084: Konsistente Split-View-Maskenarchitektur

Die Web-UI MUSS eine standardisierte Zwei-Spalten-Ansicht (Listen-Ansicht links, Detail-Ansicht rechts) für die Verwaltung aller Artefakttypen verwenden. Der Trenner MUSS verschiebbar (resizable) sein.

**Implementation State:** Not Implemented
**Review Findings:** Migration.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Split-View wird als generisches Container-Muster für alle Module genutzt.
- [ ] Breite des rechten/linken Panels ist via Drag&Drop anpassbar.

**Verifikationsmethode:** UI-Test des Layouts.
**Verifikiert durch:** L1-SystemAcceptanceTest-084
**Abgeleitet von:** REQ-L0-053 (SN-53)

---

### REQ-L1-085: Erweiterte Listenoperationen

Die Listen-Ansichten der Web-UI MÜSSEN mit einer global konsistenten Toolbar ausgestattet sein, die Textsuche, Filtern nach Attributen (z.B. Status) und Sortierung ermöglicht, um die Navigation bei großen Datenmengen zu unterstützen.

**Implementation State:** Not Implemented
**Review Findings:** Migration.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Toolbar über Listen bietet Suchfeld.
- [ ] Toolbar bietet Dropdowns für Filter (z.B. Workflow State).
- [ ] Sortier-Controls für die Listenansicht.
- [ ] API-Pagination wird durch das Frontend nahtlos unterstützt (Nachladen oder Seiten).

**Verifikationsmethode:** End-to-End Test (Filtern und Suchen via UI triggert korrekte API-Requests).
**Verifikiert durch:** L1-SystemAcceptanceTest-085
**Abgeleitet von:** REQ-L0-054 (SN-54)

---

*Erstellt durch se-requirements-Agent (L1) | ReqFlow SE-Kaskade | 2026-07-04*
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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

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
mit Requirements, ArchitectureElements und TestCases verknüpfen können — via synchroner Web-API
und MCP mit vollständigem CRUD.

**Rationale:** ADRs, Risiken und Issues sind integrale SE-Artefakte. Ohne Verknüpfung
mit Anforderungen und Architektur fehlen Kontext, Rückverfolgbarkeit und
die Grundlage für Safety-Cases und Compliance-Audits.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priorität:** desired
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Auswahl des synchronen API-Protokolls"
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
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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
maschinenlesbar abrufbar und visuell aufbereitet im Dashboard.

**Rationale:** Metrikenbasiertes Steuern ist ein explizites SE-Prinzip. Ohne Metriken
fehlt die Datengrundlage für Prozesssteuerung und Qualitätsnachweise.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priorität:** desired
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Bereitstellung aggregierter Metriken (maschinenlesbar und für GUI)"
**Externe Interfaces:**
- Eingang: Metrikanfrage mit Workspace-Kontext, Zeitraum und Scope-Filter
- Ausgang: Strukturierte Metrikdaten; konfigurierbare Schwellwert-Warnungen

**Traceability:** REQ-L0-020

---

### REQ-L1-032: Resilienz-Anforderung — Fehlertoleranz und Graceful Degradation

Das System muss bei Ausfall, Verzögerung oder Nichterreichbarkeit optionaler 
Subsysteme und externer Schnittstellen (z.B. LLM-Anbieter, Webhooks, GitHub)
die Funktionalität der Kern-Systeme (CRUD, Traceability, Baselines) mit einer
Verfügbarkeit von > 99,5 % aufrechterhalten. Ausfälle in Randbereichen dürfen 
nicht kaskadieren.

**Rationale:** Fehlertoleranz ist ein übergreifendes Systemprinzip.
Ausfälle externer Abhängigkeiten dürfen nicht zum Gesamtausfall führen.
Wie diese Entkopplung architektonisch umgesetzt wird, ist eine Design-Entscheidung.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** system
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Entkopplung optionaler/externer Schnittstellen zur Vermeidung von Kaskadenfehlern"
**Externe Interfaces:**
- Eingang: Anfragen, die optionale Subsysteme involvieren
- Ausgang: Erfolgreiche Antwort der Kernfunktionen trotz Ausfall der optionalen Erweiterungen (inkl. Fehlerprotokoll)

**Traceability:** REQ-L0-021

---

### REQ-L1-033: Credential-basierte Authentifizierung mit Token-Ausgabe

Das System muss einen öffentlich erreichbaren Login-Endpunkt bereitstellen, der
Benutzername und Passwort entgegennimmt, die Anmeldedaten gegen das gespeicherte
Passwort-Hash (PBKDF2 oder gleichwertig) prüft und bei erfolgreicher Prüfung einen
gültigen Bearer-Token zurückgibt — wobei dieser Token mit der bestehenden
`BearerTokenAuthentication`-Schicht (REQ-L1-010) vollständig kompatibel ist und
Tenant-Kontext sowie Rollen enthält. Zusätzlich muss ein geschützter Endpunkt die
Identität des aktuell angemeldeten Nutzers zurückgeben (Session-Bootstrap).

**Rationale:** Bearer-Token und API Keys (STRATEGY.md §3, KONZEPT.md §9) setzen voraus, dass ein
Token existiert. Ohne Credential-basierten Login gibt es keinen niedrigschwelligen
Einstiegspunkt für interaktive Nutzer (Frontend) und Agenten. SN-22 schließt diese
Lücke für v1. SSO (SAML/OIDC) bleibt explizit v2 (STRATEGY.md §6 Out-of-Scope).
**Implementation State:** Not Implemented
**Review Findings:** Nur Tests gefunden, aber keine Implementierung.
**Test Status:** Covered
**Remarks:** Implementierung prüfen.

**Domain:** software
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Credential-basierter Login erfordert einen unauthentifizierten Einstiegspunkt für interaktive Nutzer und Agenten sowie sicheres Passwort-Hashing; Token-Ausgabe und -Format müssen mit der bestehenden Token-basierten Authentifizierungsschicht kompatibel sein."
**Externe Interfaces:**
- Eingang (Login): Öffentlicher POST-Endpunkt mit `{username, password}` (kein Auth-Header erforderlich)
- Ausgang (Login): `{token, user, tenant_id, roles}` bei Erfolg; HTTP 401 bei falschen oder inaktiven Credentials
- Eingang (Identitäts-Abfrage): GET-Endpunkt mit Bearer-Token im Authorization-Header
- Ausgang (Identitäts-Abfrage): Nutzeridentität `{username, roles, tenant_id}` für Session-Bootstrap
**Akzeptanzkriterien:**
- AC1: `POST /auth/login/` mit gültigem `{username, password}` gibt HTTP 200 mit einem Bearer-Token zurück, der an allen geschützten Endpunkten akzeptiert wird.
- AC2: `POST /auth/login/` mit falschem Passwort oder unbekanntem Benutzernamen gibt HTTP 401 zurück; keine Unterscheidung zwischen „Nutzer unbekannt" und „Passwort falsch" in der Response.
- AC3: `POST /auth/login/` für ein inaktives Konto gibt HTTP 401 zurück.
- AC4: Passwörter sind ausschließlich als Hash (PBKDF2 oder gleichwertig) in der Datenbank gespeichert; Klartext erscheint nie in API-Responses, Logs oder Audit-Einträgen (prüfbar per Schema-Inspektion und Log-Review).
- AC5: Der ausgestellte Token ist round-trip-fähig: er wird von `BearerTokenAuthentication` (REQ-L1-010) akzeptiert und liefert den korrekten Rollen- und Tenant-Kontext für RBAC-Entscheidungen.
- AC6: `GET /auth/me/` mit gültigem Bearer-Token gibt Nutzeridentität `{username, roles, tenant_id}` zurück; ohne Token oder mit ungültigem Token HTTP 401.
**Abgrenzung:**
- SSO (SAML/OIDC) ist explizit NOT in Scope für v1 (STRATEGY.md §6 Out-of-Scope; v2-Roadmap).
- Passwort-Reset-Flow und E-Mail-Verifikation sind nicht Teil dieser Anforderung.

**Traceability:** REQ-L0-022

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
| REQ-L1-033 | REQ-L0-022 |

---

*Erweiterung durch se-requirements-Agent | HOFF-20260621-002 | 2026-06-21*
*Erweiterung durch se-requirements-Agent | 2026-06-25 (REQ-L1-033 Credential-Login)*

---

## Offene L1-Ableitungen (REQ-L0-023..028)

> **Quelle:** se-requirements-Agent | HOFF-20260626-001 | 2026-06-26
>
> Abgeleitet von SN-23..SN-28 aus `docs/se/L0/SN_Stakeholder_Needs_Backlog.md`.
> Version-Tags: `v1.1` = near-term feasible; `v2.0` = längerfristig / infrastrukturaufwändig.
> Status: **OFFEN — ausstehende Architektur-Zerlegung**

---

### REQ-L1-034: ReqIF-Import und -Export für MBSE-Datenaustausch

Das System muss Anforderungsstrukturen inklusive hierarchischer Beziehungen, Attributen
und TraceLinks verlustfrei im ReqIF-Format (Requirements Interchange Format, aktuelle
Spezifikation) importieren und exportieren können — unter der Bedingung, dass ein
ReqIF-Dokument mindestens SpecObjects, SpecRelations und SpecHierarchies vollständig
abbildet und Validierungsfehler mit Elementreferenz zurückgemeldet werden.

**Rationale:** CSV-Export (REQ-L1-019) reicht für hierarchische MBSE-Strukturen mit
Trace-Links nicht aus. ReqIF ist in regulierten Industrien (Automotive, Avionik) zwingend
erforderlich für den Austausch mit DOORS, Polarion und ähnlichen Werkzeugen.
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Domain:** software
**Priorität:** desired
**Version:** v2.0
**Externe Interfaces:**
- Eingang: ReqIF-Datei-Upload (.reqif) oder Export-Anfrage mit Scope (Workspace/Projekt)
- Ausgang: Importierte Artefakte mit UUID und Hierarchie; .reqif-Datei-Download mit vollständiger Struktur

**Traceability:** REQ-L0-023

---

### REQ-L1-035: Test-Run-Protokollierung mit Ausführungsstatus

Das System muss Testläufe (Test Runs) als eigenständige Entitäten verwalten, die
einer definierten Menge von TestCases zugeordnet sind, wobei jeder Testlauf
Ausführungsstatus (Passed / Failed / Blocked / Not Run) pro TestCase aufzeichnet
und Gesamtlauf-Ergebnis, Zeitstempel sowie ausführende Instanz protokolliert —
mit vollständigem CRUD via synchroner Web-API und MCP.

**Rationale:** REQ-L1-012 definiert Testfälle und deren Coverage. Ohne Test-Run-Protokollierung
fehlt der Ausführungsnachweis auf der rechten Seite des V-Modells (Verification & Validation).
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priorität:** desired
**Version:** v1.1
**Externe Interfaces:**
- Eingang: Test-Run-Erstellungsanfrage mit TestCase-IDs und optionalem Zeitplan; Status-Update-Anfrage pro TestCase
- Ausgang: Test-Run-Entität mit aggregiertem Ergebnis (Passed/Failed/Partial), Coverage-Delta, Zeitstempel

**Traceability:** REQ-L0-024

---

### REQ-L1-036: Automatisierte Test-Ergebnis-Einspeisung via API und MCP

Das System muss automatisierten Pipelines und CI/CD-Systemen ermöglichen, Testergebnisse
direkt als Test-Run-Ergebniseinträge über die synchrone Web-API und den MCP-Server
(test.record_result) einzuspeisen — unter der Bedingung, dass die aufrufende Instanz
mit einem gültigen API-Key authentifiziert ist und jede Einspeisung im Audit-Log
mit Agent-Client-Identität erfasst wird.

**Rationale:** Manuelle Einspeisung von CI/CD-Ergebnissen erzeugt Medienbrüche und unterbricht
die Traceability-Kette. Automatisierte Einspeisung schließt den V-Modell-Kreislauf ohne
manuelle Intervention.
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Domain:** software
**Priorität:** desired
**Version:** v1.1
**Externe Interfaces:**
- Eingang: API-Key-authentifizierter POST-Aufruf (API oder MCP test.record_result) mit TestCase-ID, Ergebnisstatus, Ausgabe-Payload
- Ausgang: Audit-Log-Eintrag mit Agent-Identität; aktualisierter Test-Run-Status; HTTP 200 bei Erfolg

**Traceability:** REQ-L0-024

---

### REQ-L1-037: Kontextbezogene Kommentar-Threads mit Mention-Benachrichtigung

Das System muss pro Artefakt (Requirement, ArchitectureElement, TestCase) threaded
Kommentare ermöglichen — mit @Mention-Syntax für registrierte Nutzer, Zeitstempel,
Autor-Angabe und vollständigem Kommentar-History-Protokoll — wobei erwähnte Nutzer
eine In-App-Benachrichtigung erhalten und alle Kommentare im Audit-Trail erfasst werden.

**Rationale:** Ohne integrierte Kommunikation finden Abstimmungen in externen Tools statt,
wodurch der Entscheidungskontext für AI-Agenten und zukünftige Reviews verloren geht.
Kommentar-Threads ermöglichen die kontextgebundene Dokumentation von Klärungen direkt
am betroffenen Artefakt.
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Domain:** software
**Priorität:** optional
**Version:** v2.0
**Externe Interfaces:**
- Eingang: Kommentar-Erstellungsanfrage mit Artefakt-ID, Text (inkl. @Mention-Syntax), Autor-Kontext
- Ausgang: Kommentar-Thread mit UUID, Zeitstempel, Autor; In-App-Benachrichtigung an erwähnte Nutzer

**Traceability:** REQ-L0-025

---

### REQ-L1-038: Semantische Vektorsuche über alle Artefakttypen (RAG)

Das System muss eine semantische, vektorbasierte Suche über alle Artefakttypen
bereitstellen, die inhaltlich ähnliche Anforderungen, Duplikate und fehlende
Verknüpfungen identifiziert — abfragbar via UI und MCP (artifact.semantic_search)
— wobei Embeddings bei Artefakt-Erstellung und -Änderung automatisch aktualisiert
und im selben Deployment persistiert werden.

**Rationale:** Volltextsuche (REQ-L1-020) skaliert bei tausenden Anforderungen semantisch nicht.
Vektorbasierte Suche ist Grundlage für AI-gestützte Konsistenz- und Lückenanalysen.
Infrastrukturaufwand (Embedding-Modell, Vektordatenbank) macht dies zu einem v2-Feature.
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Domain:** software
**Priorität:** optional
**Version:** v2.0
**Externe Interfaces:**
- Eingang: Semantische Suchanfrage (natürlichsprachlicher Query oder Artefakt-ID für Ähnlichkeitssuche)
- Ausgang: Gerankte Trefferliste mit Ähnlichkeits-Score; Duplikat-Warnungen; vorgeschlagene TraceLinks

**Traceability:** REQ-L0-026

---

### REQ-L1-039: Granulare Item-Level-Zugriffskontrolle

Das System muss Projekt-Administratoren ermöglichen, Sichtbarkeits- und Bearbeitungsrechte
auf Subsystem- oder Artefakt-Ebene zu konfigurieren — sodass externe Partner oder
Zulieferer Lesezugriff auf definierte Teilmengen eines Projekts erhalten, ohne den
gesamten Systemkontext einzusehen — unter der Bedingung, dass Item-Level-Regeln
die Workspace-RBAC (REQ-L1-010) verfeinern und niemals überschreiben.

**Rationale:** Workspace-RBAC (REQ-L1-010) und Mandantenfähigkeit (REQ-L1-015) trennen
Kunden vollständig. In großen Projekten müssen externe Partner am selben Projekt
mitarbeiten, ohne den gesamten Systemkontext zu sehen — eine Anforderung, die
feingranulare Zugriffslisten erfordert.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priorität:** optional
**Version:** v2.0
**Externe Interfaces:**
- Eingang: Zugriffsregel-Konfiguration mit Artefakt-ID oder Subsystem-ID, Nutzer/Gruppe, Berechtigungstyp (read/write)
- Ausgang: Gefilterte API-Antworten gemäß Item-Level-Regeln; HTTP 403 bei Regelverstoß

**Traceability:** REQ-L0-027

---

### REQ-L1-040: Visuelles Artefakt-Diff zwischen Versionen

Das System muss Änderungen an einem einzelnen Artefakt (Requirement, ArchitectureElement,
TestCase) zwischen zwei beliebigen Versionen als visuellen Text-Diff darstellen —
mit Hervorhebung von hinzugefügten, geänderten und gelöschten Feldinhalten —
abrufbar in der Artefakt-Detailansicht der GUI und via synchroner Web-API.

**Rationale:** Das Audit-Log (REQ-L1-011) speichert alle Änderungen, ist aber für
Menschen schwer lesbar. Ein visueller Diff pro Artefakt ist für formale Reviews
und Freigabe-Entscheidungen unerlässlich.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priorität:** desired
**Version:** v1.1
**Externe Interfaces:**
- Eingang: Diff-Anfrage mit Artefakt-ID und zwei Versions-Referenzen (version_a, version_b)
- Ausgang: Strukturiertes Diff-Objekt mit Feld-Level-Änderungen; UI-Darstellung mit Syntaxhervorhebung

**Traceability:** REQ-L0-028

---

### REQ-L1-041: Visuelles Baseline-Diff zwischen zwei Baselines

Das System muss den Vergleich zweier benannter Baselines desselben oder kompatiblen
Scopes als visuellen Diff darstellen — mit kategorisierten Änderungslisten
(hinzugefügte, geänderte, gelöschte Artefakte inkl. Versions-Delta) — abrufbar
in der GUI und als maschinenlesbarer API-Response.

**Rationale:** L2-BL-02 definiert den Baseline-Vergleich auf Datenebene. Diese Anforderung
ergänzt die menschlesbare Darstellung, die für formale Reviews und Freigabe-Entscheidungen
in regulierten Umgebungen zwingend erforderlich ist.
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Domain:** software
**Priorität:** desired
**Version:** v1.1
**Externe Interfaces:**
- Eingang: Baseline-Diff-Anfrage mit baseline_id_a und baseline_id_b
- Ausgang: Diff-Report mit kategorisierten Artefakt-Änderungslisten (added/modified/deleted); GUI-Darstellung und maschinenlesbarer JSON-Response

**Traceability:** REQ-L0-028

---

### REQ-L1-042: Workspace-Lifecycle-Operationen mit RBAC

Das System MUSS Workspace-Lifecycle-Operationen (close, reactivate, delete) auf
REST- und UI-Ebene bereitstellen, wobei nur Nutzer mit der Rolle `admin` im
Workspace diese Operationen ausführen dürfen. Close setzt einen Soft-Delete-Flag
(`is_active=false, closed_at=now, closed_by=user.id`). Delete erfordert eine
Captcha-Bestätigung (Eingabe des Workspace-Namens) und führt eine transaktionale
Kaskaden-Löschung aller Workspace-Daten (Requirements, ArchitectureElements,
TestCases, TraceLinks, Baselines, AuditLog-Einträge) aus. Reactivate setzt
einen geschlossenen Workspace zurück (`is_active=true, closed_at=null,
closed_by=null`). Jede Lifecycle-Operation erzeugt einen AuditLog-Eintrag mit
Operationstyp, Actor, Workspace-ID und Zeitstempel.

**Rationale:** Schließt eine Lücke zwischen RBAC (REQ-L1-010) und
Multi-Tenancy (REQ-L1-015) — ohne expliziten Lifecycle gibt es keine saubere
Trennung zwischen "aktiv" und "historisch". Workspaces könnten nur über direkten
DB-Zugriff entfernt werden.
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** system
**Priorität:** mandatory
**Architektur-Impact:**
- `arch_impact`: false
- `arch_trigger`: "Kein neues Architekturmuster erforderlich — Lifecycle-Operationen ergänzen bestehenden WorkspaceService + WorkspaceViewSet um neue Endpunkte und Service-Methoden."
**Externe Interfaces:**
- Eingang: POST /api/v1/workspaces/{id}/close/ (kein Body) — Admin-Rolle erforderlich
- Eingang: POST /api/v1/workspaces/{id}/reactivate/ (kein Body) — Admin-Rolle erforderlich
- Eingang: POST /api/v1/workspaces/{id}/delete/ (Body: `{"confirmation": "<workspace_name>"}`) — Admin-Rolle erforderlich
- Ausgang: HTTP 200 mit aktualisiertem Workspace; 403 bei fehlender Admin-Rolle; 409 bei Captcha-Mismatch; 404 bei unbekanntem Workspace
**Akzeptanzkriterien:**
- AC1: Close setzt `is_active=false, closed_at=now, closed_by=user.id` in Workspace
- AC2: Reactivate setzt `is_active=true, closed_at=null, closed_by=null`
- AC3: Delete mit korrektem Workspace-Namen im confirmation-Feld → HTTP 200, Workspace + alle abhängigen Daten gelöscht
- AC4: Delete mit falschem Workspace-Namen → HTTP 409 `{"error": "confirmation_mismatch"}`
- AC5: Nicht-Admin erhält HTTP 403 auf allen drei Lifecycle-Endpunkten
- AC6: AuditLog-Eintrag mit operation=close|reactivate|delete, actor=user_id, workspace_id, timestamp
- AC7: Geschlossener Workspace ist via GET /api/v1/workspaces/ weiterhin sichtbar (read-only)
- AC8: Gelöschter Workspace ist via GET /api/v1/workspaces/ nicht mehr sichtbar
**Abgrenzung:**
- Kein neues Subsystem erforderlich — Lifecycle-Methoden erweitern bestehenden WorkspaceService
- WorkspacePresetConfig wird im selben CASCADE gelöscht (gehört zum Workspace)
- Tenant-Isolation (REQ-L1-015) bleibt gewahrt: Lifecycle-Operationen sind tenant-scoped

**Traceability:** REQ-L0-029, REQ-L1-010 (RBAC), REQ-L1-015 (Mandantenfähigkeit), REQ-L1-011 (Audit)

---

## Erweiterter Traceability-Abschnitt: REQ-L1-034..042 → REQ-L0

| REQ-L1 | Abgeleitet von REQ-L0 |
|---------|----------------------|
| REQ-L1-034 | REQ-L0-023 |
| REQ-L1-035 | REQ-L0-024 |
| REQ-L1-036 | REQ-L0-024 |
| REQ-L1-037 | REQ-L0-025 |
| REQ-L1-038 | REQ-L0-026 |
| REQ-L1-039 | REQ-L0-027 |
| REQ-L1-040 | REQ-L0-028 |
| REQ-L1-041 | REQ-L0-028 |
| REQ-L1-042 | REQ-L0-029 |

---

*Erweiterung durch se-requirements-Agent | HOFF-20260626-001 | 2026-06-26 (REQ-L1-034..041 aus SN-23..SN-28)*
*Erweiterung durch se-requirements-Agent | 2026-06-27 (REQ-L1-042 aus SN-29 — Gap-Analyse Workspace-Lifecycle)*

---

## Erweiterung v6 — REQ-L1-043 bis REQ-L1-048 (aus SN-30, SN-32 bis SN-35 & Feedback)

> **Quelle:** REQ-L0-030, REQ-L0-032 bis REQ-L0-035 (formalisiert 2026-06-28) + User-Feedback zu reqflow_ontology_analysis.md
> **Datum:** 2026-06-28

---

### REQ-L1-043: Suspect-Link-Engine (Automatische Änderungsmarkierung)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

Das System MUSS bei jeder inhaltlichen Änderung an einem Requirement automatisch
alle direkt und transitiv davon abhängigen Artefakte (Requirements, TestCases,
Architecture Elements) als `suspect` markieren. Die Markierung bleibt aktiv, bis
ein autorisierter Nutzer die Konsistenz explizit bestätigt.

**Verifikationsmethode:** Systemtest — Änderung an REQ → Prüfung aller Nachfolger auf `suspect`-Flag
**Verifikiert durch:** L1-SystemAcceptanceTest-043
**Abgeleitet von:** REQ-L0-030
**Ableitet L2:** TraceabilityEngineSystem — REQ-L2-TRACE-xxx (Suspect-Link-Propagation)

---

### REQ-L1-044: Semantisches Projekt-Glossar (Data Dictionary)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

Das System MUSS pro Projekt ein maschinenlesbares Glossar mit Begriffsdefinitionen,
Synonymen und Abkürzungen bereitstellen. AI-Agenten MÜSSEN das Glossar über die API
abrufen können. Das System SOLL bei Anforderungsbearbeitung vor Begriffen warnen,
die nicht im Glossar enthalten oder zu bestehenden Definitionen inkonsistent sind.
Glossar-Einträge MÜSSEN versioniert und in Baselines enthalten sein.

**Verifikationsmethode:** API-Test + UI-Integrationstest
**Verifikiert durch:** L1-SystemAcceptanceTest-044
**Abgeleitet von:** REQ-L0-032
**Ableitet L2:** ApplicationServiceSystem — REQ-L2-APP-xxx (Glossar-CRUD), RestApiAdapterSystem — REQ-L2-API-xxx (Glossar-Endpunkt)

---

### REQ-L1-045: Artefakt-Branching & Merging (Isolierte Sandboxes)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

Das System MUSS es ermöglichen, einen isolierten Arbeitszweig (Sandbox) aus dem
aktuellen Zustand eines definierten Scopes (Workspace, Subsystem, Artefakt-Unterbaum)
zu erzeugen. Änderungen in einem Sandbox-Zweig MÜSSEN für andere Nutzer unsichtbar
sein, bis ein expliziter Merge-Schritt ausgeführt wird. Der Merge-Vorgang MUSS
einen visuellen Diff anzeigen und Konflikte erkennen. Bestehende Baselines DÜRFEN
durch Sandbox-Aktivitäten nicht verändert werden.

> **Lösungsneutralität:** Diese Anforderung schreibt keinen Implementierungsansatz vor.
> Die Architekturreferenz (ADR) entscheidet über Git-Mechanismus, Event-Sourcing oder
> Copy-on-Write. Zulässige Ansätze sind in REQ-L0-033 (Implementation Hint) dokumentiert.

**Verifikationsmethode:** Systemtest — Parallele Änderungen in Sandbox + Hauptzweig, Merge + Konfliktauflösung
**Verifikiert durch:** L1-SystemAcceptanceTest-045
**Abgeleitet von:** REQ-L0-033
**Ableitet L2:** BaselineServiceSystem — REQ-L2-BASE-xxx (Branch/Merge-Logik), ReactFrontendSystem — REQ-L2-FE-xxx (Diff-UI)

---

### REQ-L1-046: Instanz-Backup, Disaster Recovery & Baseline-Restore

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

Das System MUSS vollständige, automatisierbare Instanz-Snapshots (Backup) aller
Daten (Projekte, Requirements, Architecture, TestCases, TraceLinks, Baselines,
AuditLog, Nutzer ohne Passwort-Klartexte, Konfigurationen) ermöglichen. Ein Backup
MUSS auf einer leeren Instanz wiederherstellbar sein (Full Restore). Reviewer MÜSSEN
zwei Baselines oder Artefaktversionen als visuellen Diff vergleichen können. Eine
Baseline MUSS in einen Sandbox-Zweig (REQ-L1-045) zurückgespielt werden können
(Soft-Restore). Ein Hard-Restore auf den Hauptstand MUSS Admin-Berechtigung und
Captcha-Bestätigung erfordern.

**Verifikationsmethode:** Systemtest — Backup-Dump erstellen, Restore auf leerer Instanz, Datenintegrität prüfen
**Verifikiert durch:** L1-SystemAcceptanceTest-046
**Abgeleitet von:** REQ-L0-034
**Ableitet L2:** PersistenceLayerSystem — REQ-L2-PERS-xxx (Backup/Restore), ResilienceOrchestratorSystem — REQ-L2-RES-xxx (DR-Koordination), ReactFrontendSystem — REQ-L2-FE-xxx (Baseline-Diff-UI)

---

### REQ-L1-047: Cross-Level-TraceLink-Konzept (Kontrollierte Ebenensprünge)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

Das System MUSS TraceLinks mit dem Typ `cross-level` unterstützen, die Artefakte
über mehr als eine Kaskaden-Ebene direkt verbinden. Cross-Level-Links MÜSSEN eine
Pflichtbegründung (min. 20 Zeichen) enthalten. Sie MÜSSEN in der Traceability-Matrix
und im TraceLink-Graphen visuell distinkt markiert sein. AI-Agenten MÜSSEN Cross-Level-Links
in ihren Analysen gesondert ausweisen können. Die Standardnorm (stufenweise Kaskade)
MUSS die empfohlene Route bleiben; Cross-Level-Links sind eine dokumentierte Ausnahme.

**Verifikationsmethode:** API-Test — Cross-Level-Link anlegen, Begründung fehlt → Fehler; mit Begründung → Erfolg + visuelles Marking prüfen
**Verifikiert durch:** L1-SystemAcceptanceTest-047
**Abgeleitet von:** REQ-L0-035
**Ableitet L2:** TraceabilityEngineSystem — REQ-L2-TRACE-xxx (Cross-Level-Link-Typ + Validierung)

---

### REQ-L1-048: Flache und Ebenenbasierte Artefaktansicht (Multi-View)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

Das System MUSS für alle Artefakttypen (Requirements, Architecture, TestCases,
TraceLinks) zwei Ansichtsmodi bereitstellen:
1. **Flache Ansicht (Flat View):** Alle Artefakte eines Workspaces auf einer Ebene,
   filterbar und sortierbar.
2. **Ebenenansicht (Level View):** Hierarchische Darstellung gemäß Kaskaden-Ebene
   (L0 → L1 → L2 → Ln), navigierbar und kollabierbar.

Beide Ansichten MÜSSEN in einem Workspace verfügbar und umschaltbar sein.

**Verifikationsmethode:** UI-Integrationstest — Wechsel zwischen Flat View und Level View, Konsistenz der dargestellten Artefakte
**Verifikiert durch:** L1-SystemAcceptanceTest-048
**Abgeleitet von:** REQ-L1-001 (Erweiterung) + User-Feedback reqflow_ontology_analysis.md
**Ableitet L2:** ReactFrontendSystem — REQ-L2-FE-xxx (Level-View-Komponente)

---

## Erweiterter Traceability-Abschnitt: REQ-L1-034..048 → REQ-L0

| REQ-L1 | Abgeleitet von REQ-L0 |
|---------|----------------------|
| REQ-L1-034 | REQ-L0-023 |
| REQ-L1-035 | REQ-L0-024 |
| REQ-L1-036 | REQ-L0-024 |
| REQ-L1-037 | REQ-L0-025 |
| REQ-L1-038 | REQ-L0-026 |
| REQ-L1-039 | REQ-L0-027 |
| REQ-L1-040 | REQ-L0-028 |
| REQ-L1-041 | REQ-L0-028 |
| REQ-L1-042 | REQ-L0-029 |
| REQ-L1-043 | REQ-L0-030 |
| REQ-L1-044 | REQ-L0-032 |
| REQ-L1-045 | REQ-L0-033 |
| REQ-L1-046 | REQ-L0-034 |
| REQ-L1-047 | REQ-L0-035 |
| REQ-L1-048 | REQ-L1-001 (Feedback-Erweiterung) |

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L1-043..048 aus SN-30, SN-32..35 & User-Feedback)*

---

## Erweiterung v7 — REQ-L1-056 und REQ-L1-057 (aus SN-36, SN-37)

> **Quelle:** REQ-L0-036, REQ-L0-037 (formalisiert 2026-06-30)
> **Datum:** 2026-06-30
> **Entscheidung:** Neue REQ-L1-IDs statt Erweiterung REQ-L1-027, da REQ-L1-027 bereits "Implemented" ist und Canvas/Mermaid-Live-Preview distinkte Paradigmen mit eigenen Payload-Formaten sind.

---

### REQ-L1-056: Free-Hand Canvas Drawing

Das System muss eine freie Zeichenfläche (Canvas) bereitstellen, auf der Nutzer Diagramme
mit Pen/Stift, geometrischen Grundformen (Rechteck, Kreis, Linie, Polygon), Text-Notizen
und Pfeilen/Verbindern frei zeichnen können. Gezeichnete Elemente müssen nachträglich
auswählbar, verschiebbar, skalierbar und löschbar sein. Verbinder müssen mit verbundenen
Formen assoziiert bleiben (folgen bei Bewegung). Das gezeichnete Diagramm muss als
Artefakt mit JSON-Stroke-Daten als Primärformat (versioniert, diff-bar) und SVG als
abgeleitetes Export-Format persistiert werden. Canvas-Diagramme müssen via TraceLink
(Typ `documents`) mit Requirements, ArchitectureElements und TestCases verknüpfbar und
via MCP (artifact.get) abrufbar sein. Auto-Save mit konfigurierbarem Intervall (max. 5s)
muss Datenverlust bei Browser-Crash begrenzen. Das Canvas muss flüssig (≥30fps) bei bis
zu 500 Stroke-Elementen und 100 Formen rendern.

**Rationale:** Strukturierte Diagramm-Typen (REQ-L1-027) decken formale Modellierung ab,
aber nicht das schnelle, informelle Skizzieren. Free-Hand Canvas schließt die Lücke
zwischen Whiteboard-Skizze und formalem Diagramm ohne Medienbruch zu externen Tools.
**Domain:** software
**Priorität:** desired
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Canvas-basierte Zeichen-Engine benötigt neues Payload-Format (JSON-Stroke-Daten) und Frontend-Komponente außerhalb des bestehenden strukturierten Diagramm-Schemas; Auto-Save-Mechanismus und Performance-Budget (≥30fps bei 500 Elementen) erforderlich"
**Externe Interfaces:**
- Eingang: Canvas-Zeichenoperationen (Pen, Shapes, Text, Connectors) via Maus/Touch im Browser
- Ausgang: Persistierte Canvas-Diagramm-Artefakte (JSON-Stroke-Daten + SVG-Export) als versionierte Artefakte
- Ausgang: TraceLink-Einträge (Typ `documents`) an TraceabilityEngine
- Ausgang: Export-Datei (SVG/PNG) an Nutzer-Download
- Ausgang: MCP artifact.get Response mit strukturiertem Canvas-Payload (JSON-Stroke-Daten)
**Akzeptanzkriterien:**
- AC1: Canvas unterstützt Pen/Stift, Rechteck, Kreis, Linie, Text-Notiz, Pfeil/Verbinder
- AC2: Gezeichnete Elemente sind nachträglich auswählbar, verschiebbar, skalierbar und löschbar
- AC3: Verbinder bleiben assoziiert (folgen verbundenen Formen bei Bewegung)
- AC4: Persistierung als JSON-Stroke-Daten (Primärformat, versioniert, diff-bar) + SVG (Export)
- AC5: TraceLink (Typ `documents`) mit Requirements, ArchitectureElements, TestCases
- AC6: Canvas-Diagramme via MCP (artifact.get) abrufbar
- AC7: Export als SVG/PNG möglich
- AC8: Auto-Save (max. 5s Intervall) — bei Browser-Crash gehen höchstens 5s an Eingaben verloren
- AC9: ≥30fps bei 500 Stroke-Elementen und 100 Formen
**Implementation State:** Implemented
**Review Findings:** Implementierung (CanvasEditor) und Tests (Playwright + Vitest) im Code vorhanden.
**Test Status:** Covered
**Remarks:** Erfolgreich in v1.1.1 (Erweiterung) integriert.

**Traceability:** REQ-L0-036

---

### REQ-L1-057: Mermaid Live Preview

Das System muss einen Mermaid-Code-Editor mit Live-Preview bereitstellen, bei dem der
Nutzer Mermaid-Diagrammcode eingibt und das gerenderte Diagramm grafisch im Browser
als Live-Preview sieht (500ms Debounce). Unterstützt werden MÜSSEN mindestens 5
Mermaid-Typen: flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram.
Der Mermaid-Quellcode muss als versioniertes Artefakt persistiert werden. Das gerenderte
Diagramm muss zoombar (Mausrad, Pinch, Buttons) und exportierbar als PNG und SVG sein.
Bei Syntaxfehlern muss eine aussagekräftige Fehlermeldung (mit Zeilennummer) angezeigt
werden; die zuletzt erfolgreich gerenderte Darstellung bleibt als Fossil sichtbar.
Fällt der Renderer aus, muss der Quellcode lesbar als Fallback angezeigt werden.
Das Live-Rendering muss in <2s für Diagramme mit bis zu 100 Knoten/Kanten abschließen.
Der Mermaid-Quellcode muss via TraceLink (Typ `documents`) verknüpfbar und via MCP
(artifact.get) abrufbar sein.

**Rationale:** Mermaid ist De-facto-Standard für Code-basierte Diagramme. Die Live-Preview
senkt die kognitive Last beim Editieren erheblich und ermöglicht die Wiederverwendung
bestehenden Mermaid-Codes ohne manuelle Übersetzung in strukturierte Formate.
**Domain:** software
**Priorität:** desired
**Architektur-Impact:**
- `arch_impact`: true
- `arch_trigger`: "Mermaid-Live-Rendering erfordert clientseitiges Rendering (mermaid.js im Browser) für Performance (keine Roundtrips bei 500ms Debounce) und Self-Hosted-First (kein zusätzlicher Server-Prozess); Fallback-Strategie bei Renderer-Ausfall erforderlich"
**Externe Interfaces:**
- Eingang: Mermaid-Quellcode-Eingabe via Texteditor im Browser
- Ausgang: Gerendertes Diagramm (SVG/Canvas) im Browser als Live-Preview
- Ausgang: Persistierte Mermaid-Quellcode-Artefakte (versioniert)
- Ausgang: TraceLink-Einträge (Typ `documents`) an TraceabilityEngine
- Ausgang: Export-Datei (PNG/SVG) an Nutzer-Download
- Ausgang: MCP artifact.get Response mit Mermaid-Quellcode + Render-Hinweisen
**Akzeptanzkriterien:**
- AC1: Mermaid-Editor mit Live-Preview (500ms Debounce) im selben Bildschirmbereich
- AC2: Mermaid-Quellcode als versioniertes Artefakt persistiert
- AC3: Unterstützung für flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram
- AC4: Gerendertes Diagramm ist zoombar (Mausrad, Pinch, Buttons)
- AC5: Export als PNG und SVG möglich
- AC6: TraceLink (Typ `documents`) mit Requirements, ArchitectureElements, TestCases
- AC7: Bei Syntaxfehlern: Fehlermeldung mit Zeilennummer; Fossil der letzten erfolgreichen Darstellung
- AC8: Abrufbar via MCP (artifact.get) als strukturierter Payload
- AC9: Fallback bei Renderer-Ausfall: Quellcode lesbar angezeigt, editierbar und speicherbar
- AC10: Live-Rendering <2s für Diagramme mit bis zu 100 Knoten/Kanten
**Implementation State:** Implemented
**Review Findings:** Implementierung (MermaidEditor) und Tests (Playwright + Vitest) im Code vorhanden.
**Test Status:** Covered
**Remarks:** Erfolgreich in v1.1.1 (Erweiterung) integriert.

**Traceability:** REQ-L0-037

---

## Erweiterter Traceability-Abschnitt: REQ-L1-056..057 → REQ-L0

| REQ-L1 | Abgeleitet von REQ-L0 |
|---------|----------------------|
| REQ-L1-056 | REQ-L0-036 |
| REQ-L1-057 | REQ-L0-037 |

---

*Erweiterung durch se-architect-Agent | 2026-06-30 (REQ-L1-056..057 aus SN-36, SN-37 - Canvas Free-Hand Drawing + Mermaid Live Preview)*

---

## Erweiterung v8 - REQ-L1-058 bis REQ-L1-063 (Ebenen-Modell)

> **Quelle:** REQ-L0-003, REQ-L0-017 (formalisiert aus REQUIREMENTS.md)
> **Datum:** 2026-07-02

---

### REQ-L1-058: SE Masks Unification (13 Entity Types)

Standardisiere SE-Masken für alle 13 Entitätstypen zur Gewährleistung konsistenter Level-Ableitung, Parent-ID-Handling und Allocation-Tracking. Einheitliches Datenmodell für hierarchische Ebenen (L0-Ln), mit Level als abgeleitetes (nicht manuell gesetztes) Feld über Recursive CTE. Umfasst Backend-Invarianten (I1-I4), Frontend Level-View und Allocation-Coverage-Reporting.

**Rationale:** Basis für konsistente Architekturmodellierung.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: SE-Masken für 13 Entitätstypen standardisiert
- AC2: Parent-ID-Ableitung via Recursive CTE auf Query-Zeit implementiert
- AC3: Allocation-Tracking via TraceLink.allocated-to eingeführt
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-003, REQ-L0-017

---

### REQ-L1-059: ArchitectureElement parent_id + Level-Derivation

Implementiere parent_id-Feld auf ArchitectureElement zur Abbildung der Hierarchie (L1 → L2 → L3). Level wird über Recursive CTE aus Baumtiefe abgeleitet.

**Rationale:** Architekturbaum benötigt saubere Vater-Kind-Beziehungen.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: ArchitectureElement.parent_id existiert
- AC2: Recursive CTE-Query liefert level-Ableitung
- AC3: Serializer liefert read-only level-Feld
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-017

---

### REQ-L1-060: TraceLink allocated-to + Allocation-Coverage Reporter

Führe neuen TraceLink-Typ `allocated-to` ein (Requirement → ArchitectureElement). API und Report zeigen Allocation-Status pro Level.

**Rationale:** Zuweisung von Requirements zu Systemkomponenten.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: TraceLink.link_type = 'allocated-to'
- AC2: API GET /requirements/{id}/allocation
- AC3: Coverage Report pro Level
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-003

---

### REQ-L1-061: RequirementService.decompose() Extension mit target_elements

Erweitere decompose() um optionalen target_elements-Parameter. Erstellt allocated-to Links von Sub-Reqs zu angegebenen ArchEl.

**Rationale:** Effiziente Zerlegung und Zuweisung in einem Schritt.
**Domain:** software
**Priority:** desired
**Akzeptanzkriterien:**
- AC1: decompose(req_id, subs, target_elements=[]) Signatur
- AC2: Transaktion Sub-Req-Create + Allocation-Create
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-003

---

### REQ-L1-062: Invarianten-Validator (I1-I4) rigor-gated

Implementiere 4 Invarianten zur Sicherung der Ebenen-Konsistenz. Rigor-abhängig: Minimal=skip, Standard=Warnings, Extended=Hard Errors.

**Rationale:** Vermeidung ungültiger Allokationen und Zyklen.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: I1 (Req.level == Arch.level + 1)
- AC2: I2 (Kein Req an höhere Ebene als Parent)
- AC3: I3 (Keine Zirkulären Allokationen)
- AC4: I4 (Sub-Reqs müssen allociert sein)
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-003, REQ-L0-017

---

### REQ-L1-063: Frontend Level-View (Requirements Hierarchy)

Implementiere neue Route/Tab `/levels` mit Tree-View gruppiert nach abgeleiteter Ebene.

**Rationale:** Visualisierung der Requirement-Hierarchien.
**Domain:** software
**Priority:** desired
**Akzeptanzkriterien:**
- AC1: Route `/levels` existiert
- AC2: Tree rendert Requirements nach Level
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-003

---

### REQ-L1-064: Einheitliche, skalierbare Listen-Komponente (UI)

Das System muss eine einheitliche, skalierbare Listen-Komponente für alle primären Artefakte (Requirements, Architecture, Issues, Risks, Testcases, ADRs) bereitstellen.

**Rationale:** Vermeidung von redundantem Code und einheitliche User Experience über alle Artefakt-Ansichten hinweg.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Es existiert eine gemeinsame Listen-Komponente für alle Artefakttypen.
- AC2: Die Komponente kann beliebige Felder der jeweiligen Typen rendern.
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert (aktuell nur flache unstrukturierte Listen).
**Test Status:** Missing

**Traceability:** REQ-L0-038

---

### REQ-L1-065: Lazy Loading / Server-Side Pagination

Die Datenladung für Artefakt-Listen muss zwingend paginiert (Lazy Loading / Server-Side) erfolgen, anstatt initiale `listAll()`-Aufrufe durchzuführen.

**Rationale:** Verbesserung der UI-Performance und Skalierbarkeit bei großen Projekten.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: DRF ViewSets unterstützen Pagination.
- AC2: UI-Listen rufen die Daten seitenweise ab (z.B. Infinite Scroll oder Pages).
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-040

---

### REQ-L1-066: Serverseitige Such-, Filter- und Sortierfunktionen

Das System muss serverseitige Such-, Filter- (z. B. Status, Kategorie) und Sortierfunktionen unterstützen und über eine zugängliche UI (ListToolbar) anbieten.

**Rationale:** Essentiell zum Finden von spezifischen Elementen in Projekten mit hunderten von Anforderungen.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: DRF ViewSets implementieren SearchFilter, DjangoFilterBackend und OrderingFilter.
- AC2: Die UI bietet eine ListToolbar mit Inputs für Suche, Filter und Sortierung.
- AC3: Parameter werden per Query-String an das Backend gesendet.
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-038

---

### REQ-L1-067: Hierarchische Darstellung in Primärlisten

Das System muss eine optionale hierarchische Einrückung (Tree-View-Modus) direkt in der primären Listenansicht für Artefakte mit Parent-Child-Strukturen anbieten.

**Rationale:** Erhalt des Kontexts (Systemebenen-Orientierung) in der Hauptansicht.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Toggle für "Tree View" in der Listen-Ansicht.
- AC2: Wenn aktiviert, rücken Kindelemente visuell ein.
- AC3: Parent-Knoten können eingeklappt werden.
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-039

---

### REQ-L1-068: Graph-Datenbank als Backend-Kern

Das System muss auf einer Graphen-Datenbank (z. B. Neo4j oder ArangoDB) basieren, um tief verschachtelte DAG-Strukturen performant aufzulösen.

**Rationale:** Relationale DBs sind ineffizient für unbegrenzt tiefe Traceability-Abfragen.
**Domain:** software
**Priority:** deferred
**Akzeptanzkriterien:**
- AC1: Die primäre Persistenzschicht ist eine Graph-Datenbank.
- AC2: Rekursive Traceability-Abfragen über den gesamten Baum dauern < 500ms.
**Implementation State:** Deferred
**Review Findings:** Architektur-Wechsel von SQL auf Graph-DB durch Projektleitung zurückgestellt. Wir behalten die relationale Architektur bei.
**Test Status:** Missing

**Traceability:** REQ-L0-041

---

### REQ-L1-069: AI Orchestration Layer & Semantic Router

Das System muss einen Router besitzen, der komplexe Aufgaben (RAG, Herunterbrechen) an leistungsstarke Cloud-LLMs routet und hochfrequente/datenschutzkritische Aufgaben an lokale LLMs (z. B. Ollama) delegiert.

**Rationale:** Kostenoptimierung, Datenschutz und Latenz-Reduzierung durch Hybrid-AI.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Der AI Orchestration Layer kann Cloud- und Local-LLMs ansteuern.
- AC2: Routing-Entscheidungen basieren auf Datenschutz-Tags und Modell-Fähigkeiten.
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-046

---

### REQ-L1-070: WebGL / Canvas Graph Rendering

Das Frontend muss WebGL/Canvas-Technologien einsetzen, um interaktive Node-Graphen mit tausenden Knoten flüssig zu rendern.

**Rationale:** DOM-basierte Graph-Renderer (SVG) skalieren nicht für große System-Architekturen.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Netzwerk-Ansicht rendert bis zu 5000 Knoten mit 30 FPS.
- AC2: Rendering basiert auf Canvas oder WebGL (z.B. React Flow / Cytoscape).
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-043

---

### REQ-L1-071: Spezifische Traceability-Ontologie

Die Trace-Engine muss die Kanten-Semantik streng validieren (z. B. `StReq --derives to--> SyReq`, `CoReq --allocated to--> ArchE`).

**Rationale:** Semantisches Routing und KI-Analyse erfordern eine deterministische Graphenstruktur.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Erstellung von Kanten, die gegen die Ontologie verstoßen, wird abgelehnt.
- AC2: Kanten-Typen sind klar definiert (`derives to`, `allocated to`, `refines`, etc.).
**Implementation State:** Backlog
**Review Findings:** Aktuell unstrukturiertes `link_type` Attribut ohne Validierung.
**Test Status:** Missing

**Traceability:** REQ-L0-042

---

### REQ-L1-072: Statische vs. Dynamische TraceLinks

TraceLinks müssen ein Attribut `pin_version` unterstützen. Ist dies gesetzt, verweist der Link auf eine unveränderliche Version des Zielelements (Statisch/Pinned). Ohne ist er Dynamisch (Latest).

**Rationale:** Notwendig für formale Releases, um nachträgliche, unsichtbare Änderungen zu verhindern.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: TraceLinks können an eine spezifische Version gepinnt werden.
- AC2: UI visualisiert den Unterschied zwischen "Latest" und "Pinned".
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-044

---

### REQ-L1-073: Rules Engine für Anti-Patterns

Eine Rules-Engine prüft den DAG kontinuierlich auf Orphans (kein Upstream), Barren Nodes (kein Downstream) und Cycles (Zyklen) und meldet diese via UI und API.

**Rationale:** Automatische Qualitätssicherung für komplexe Traceability.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Dashboard zeigt Liste der Anti-Patterns.
- AC2: Graphen-DB-Abfragen identifizieren Zyklen und isolierte Knoten.
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-045

---

### REQ-L1-074: Semantic Trace Healing Engine

Ein KI-Service horcht auf Suspect-Status-Änderungen, analysiert das inhaltliche Delta und generiert proaktiv Patch-Vorschläge für Downstream-Artefakte.

**Rationale:** Reduzierung manueller Review-Aufwände bei kleinen Änderungen in großen Systemen.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Event-Listener erkennt, wenn ein Trace-Link auf "Suspect" geht.
- AC2: KI generiert einen Text- oder Code-Vorschlag für das abhängige Element.
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

**Traceability:** REQ-L0-046

---

### REQ-L1-075: GraphQL & REST Parität

Neben der REST-API muss eine vollständige GraphQL-API bereitgestellt werden, die tief verschachtelte Graph-Queries für externe Agenten und Clients effizient macht.

**Rationale:** N+1 Query Probleme beim Traversieren des Graphen durch externe API-Clients vermeiden.
**Domain:** software
**Priority:** deferred
**Akzeptanzkriterien:**
- AC1: Ein `/graphql` Endpoint existiert.
- AC2: Die GraphQL-Schema-Abdeckung entspricht 100% der Entitäten der REST-API.
**Implementation State:** Deferred
**Review Findings:** Zurückgestellt. Es erfolgen vorerst keine Architekturänderungen an der API-Schicht.
**Test Status:** Missing

**Traceability:** REQ-L0-041

---

### REQ-L1-076: Global Entity Metadata

Jedes Artefakt im System (Requirement, ArchitectureElement, TestCase, etc.) MUSS zwingend ein Set von systemgemanagten Meta-Attributen aufweisen. Diese Felder dürfen nicht durch Nutzer überschrieben werden (außer ggf. Tags).

**Rationale:** Revisionssicherheit, Eindeutige Referenzierung in Dokumenten und API.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: `uid`: Ein im Workspace eindeutiger Auto-String (z.B. REQ-1042).
- AC2: `version`: Float oder SemVer (z.B. 1.2), das bei Änderungen hochgezählt wird.
- AC3: `created_by` / `created_at` sowie `last_modified_by` / `last_modified_at`.
- AC4: `tags`: Array von Strings für flexible Zuordnung.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-047

---

### REQ-L1-077: Artifact-Specific Schema

Das Datenmodell MUSS typspezifische Pflicht- und Optionsfelder erzwingen.
- **Stakeholder Requirement:** MoSCoW-Priority, Origin/Source, Business Value (1-10).
- **System Requirement:** Req. Type (Functional, Non-Functional, Interface, Constraint), Complexity/Points (Fibonacci), Verification Method (Test, Inspection, Analysis, Demonstration).
- **Architecture Element:** Arch. Level (System, Subsystem, Component, Unit), Make-or-Buy (Make, Buy, Reuse), Criticality (ASIL/SIL Level).
- **Test Case:** Test Type (Unit, Integration, System, E2E), Pre-Conditions (Text), Expected Result (Text).

**Rationale:** Normkonformität nach INCOSE / ASPICE erfordert spezifische Metriken je Typ.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Das Datenbank-Schema und die REST-Serializer validieren diese spezifischen Felder zwingend.
- AC2: Unpassende Felder (z.B. ASIL an einem StReq) werden von der API abgelehnt.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-047

---

### REQ-L1-078: State Machine & Workflow

Alle Hauptartefakte MÜSSEN den folgenden industriestandard-nahen Workflow-Status (State Machine) unterstützen:
`Draft` (Entwurf) ➔ `In Review` (In Prüfung) ➔ `Approved` (Freigegeben) ➔ `In Implementation` (Nur ArchE) ➔ `Verified` (Verifiziert).
Zusätzlich: `Rejected` und `Obsolete`.

**Rationale:** Abbildung von Freigabeprozessen und Reifegrad-Messung.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Jedes Artefakt hat ein Feld `workflow_state`.
- AC2: Neue Artefakte starten zwingend im Status `Draft`.
- AC3: Übergänge sind nur nach der definierten State Machine (z.B. Draft ➔ Review, nicht Draft ➔ Verified) erlaubt.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-048

---

### REQ-L1-079: Stage-Gating Engine (Guardrails)

Das System MUSS serverseitige Stage-Gating-Regeln anwenden, die Statusübergänge blockieren, wenn die Struktur nicht konsistent ist.
Regeln:
1. **Top-Down Zwang:** Ein SyReq darf nur `Approved` werden, wenn sein referenziertes StReq ebenfalls `Approved` ist.
2. **No-Orphan Rule:** Ein SyReq darf nicht `In Review` gehen, wenn kein Upstream-Trace zu einem StReq oder einer übergeordneten Komponente existiert.
3. **Allocation Gate:** Eine ArchE-Komponente darf erst `Approved` werden, wenn alle ihr zugewiesenen SyReqs `Approved` sind. Allocation auf ArchEs ist erst ab Status `Draft` (existierend) erlaubt.
4. **Baseline Lock:** Eine Baseline (Snapshot) darf nur erzeugt werden, wenn alle inkludierten Artefakte `Approved` sind und keine `Suspect`-Links existieren.

**Rationale:** Erzwingen von sauberer Traceability (Guardrails gegen Schlampigkeit).
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Die REST-API lehnt PATCH-Requests für Statusänderungen mit `409 Conflict` (inkl. Detail-Message) ab, wenn ein Gate verletzt wird.
- AC2: Baseline-Generierung blockiert bei unfertigen Dokumenten.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-049

---

### REQ-L1-080: Event-Driven AI Automation

Status-Übergänge (Events) MÜSSEN konfigurierbare KI-Aktionen im AI Orchestration Layer triggern:
- Beim Übergang `Draft ➔ In Review`: AI Quality Gate prüft das Requirement (z.B. auf Messbarkeit, INCOSE-Regeln) und kann den Wechsel mit einer Begründung ablehnen.
- Beim manuellen Trigger auf einem StReq (`Draft`): AI Decomposition generiert einen Entwurf von SyReqs.
- Wenn ein SyReq auf `Approved` springt: AI Verification Agent entwirft passend zur Verification Method erste Test Cases (TC) im Status `Draft`.

**Rationale:** Nutzung der harten Schema-Struktur als Hebel für verlässliche KI-Automatisierung.
**Domain:** software
**Priority:** desired
**Akzeptanzkriterien:**
- AC1: Status-Transitions feuern Events in das System.
- AC2: KI-Agenten lauschen auf diese Events und führen die entsprechenden Use-Cases aus.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-049, REQ-L0-046

---

## Erweiterung v10 — REQ-L1-086 (Glossary Mentions & Persistence)

> **Datum:** 2026-07-05 | **Quelle:** REQ-L0-055

---

### REQ-L1-086: Glossary Mentions & Persistence

Das System MUSS es ermöglichen, definierte Glossar-Einträge direkt im Freitext (Beschreibungen von Anforderungen, Testfällen etc.) über eine `@Begriff`-Syntax zu referenzieren.
Glossar-Begriffe MÜSSEN auch über die API abrufbar sein, um programmgesteuert kontextbezogene Erklärungen zu liefern.
Beim Löschen eines Workspaces DÜRFEN Glossar-Begriffe nicht gelöscht werden (kein CASCADE Delete), sondern bleiben mit `null`-Workspace global oder verwaist erhalten, damit die Definitionen über Projekte hinweg nutzbar oder zumindest historisch gesichert bleiben.

**Rationale:** Fachtexte enthalten oft domänenspezifische Begriffe. Durch eine einfache `@`-Erwähnung und Auto-Erkennung im Text können Nutzer sofort beim Lesen Tooltips mit den Definitionen abrufen, was Missverständnisse reduziert. Die Persistenz über Workspace-Grenzen hinweg sichert mühsam erarbeitete Begriffsklärungen.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Die Markdown-Vorschau erkennt `@Begriff` und macht daraus ein UI-Element (z.B. Link oder Tooltip).
- AC2: Tooltips zeigen die Definition des Begriffs.
- AC3: Das Löschen eines Workspaces löscht nicht das Glossar, sondern setzt die Workspace-ID auf `null` (`on_delete=SET_NULL`).
- AC4: REST-API unterstützt den Abruf von Glossarbegriffen.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-055

---

## Erweiterung v11 — REQ-L1-087 (Workspace Admin & User Preferences Separation)

> **Datum:** 2026-07-05 | **Quelle:** User Feedback

---

### REQ-L1-087: Strikte Trennung von Workspace Administration und User Preferences

Das System MUSS administrative Workspace-Einstellungen (Name, Preset, Terminology, Language, Decomposition Link, Attribute Visibility, Permissions, Backup, Lifecycle) strikt von benutzerspezifischen Einstellungen (Personal Access Tokens, UI-Sichtbarkeiten/Overrides) in zwei getrennten UI-Dialogen trennen.
Der `Workspace Admin Dialog` DARF NUR für Workspace-Admins zugänglich sein und MUSS robuster gestaltet werden, sodass keine Berechtigungsfehler bei regulären Benutzern auftreten. Die benutzerspezifischen Einstellungen MÜSSEN im `User Preferences` (Profile) Dialog untergebracht sein.

**Rationale:** Die Vermischung von administrativen und benutzerspezifischen Einstellungen führt zu Verwirrung und Fehlern in der Berechtigungsprüfung. Benutzerspezifische Einstellungen wie die Ausblendung optionaler Artefakte ("Sichtbarkeit") gelten nur pro Benutzer und sollten in dessen Profil verwaltet werden.
**Domain:** software
**Priority:** mandatory
**Akzeptanzkriterien:**
- AC1: Die Sektion "Sichtbarkeit" ist nicht mehr im WorkspaceSettings Dialog, sondern im UserProfileSettings Dialog.
- AC2: Reguläre Benutzer erhalten keine unschönen Fehler beim Zugriff auf Einstellungen, die ihre eigenen Präferenzen betreffen.
**Implementation State:** In Progress
**Review Findings:** Geplant und als Implementation Plan genehmigt.
**Test Status:** Missing

**Traceability:** N/A

---

## Erweiterung v12 — REQ-L1-088 (Configurable AI Prompts)

> **Datum:** 2026-07-05 | **Quelle:** REQ-L0-056

---

### REQ-L1-088: Konfigurierbare KI-Ableitungs-Prompts

Das System MUSS es Administratoren ermöglichen, die von KI-Agenten genutzten System-Prompts für domänenspezifische Aufgaben (z.B. Requirement-Ableitung, Test-Generierung, Code-Review) auf Workspace-Ebene zu konfigurieren.
Wenn für einen Workspace kein spezifischer Prompt konfiguriert ist, MUSS das System auf einen systemweiten Default-Prompt zurückfallen.

**Rationale:** Hardcodierte Prompts decken nicht die projektspezifischen Dokumentationsstandards und Nomenklaturen (z.B. ISO 26262 vs. Agile) ab. Administratoren müssen die KI-Anweisungen an die Workspace-Gegebenheiten anpassen können.
**Domain:** software
**Priority:** desired
**Akzeptanzkriterien:**
- AC1: Die REST-API bietet Endpunkte für CRUD-Operationen von AI-Prompts auf Workspace-Ebene (`/api/v1/workspaces/{id}/prompts`).
- AC2: Der AI Orchestration Layer verwendet vor jeder Prompt-Ausführung den vom Workspace konfigurierten Prompt.
- AC3: Existiert im Workspace keine Konfiguration, wird der Default-Prompt verwendet.
- AC4: Änderungen an Prompts schreiben einen AuditLog-Eintrag.
**Implementation State:** Backlog
**Review Findings:** Neu.
**Test Status:** Missing

**Traceability:** REQ-L0-056

### REQ-L1-085: Unified TraceLink Panel
Das System muss eine global wiederverwendbare UI-Komponente (TraceLink Panel) bereitstellen, die f�r Requirements, Needs und Architektur exakt identisch funktioniert. Sie muss Downstream/Upstream unterscheiden und Aktionen wie "Ableiten" anbieten.
**Domain:** software
**Priorit�t:** mandatory
**Traceability:** REQ-L0-060

### REQ-L1-086: Universal Version Badge
Das System muss den Versions-Badge der ICDs auf alle anderen Entit�ts-Header �bertragen und eine History-Ansicht als Toggle bereitstellen.
**Domain:** software
**Priorit�t:** mandatory
**Traceability:** REQ-L0-060

### REQ-L1-087: Interactive Canvas und Diagramm-Traces
Die Diagramm-Ansicht muss freies Zeichnen (Canvas) unterst�tzen und die Zuweisung von Architektur-Elementen ("describes/helps") fehlerfrei persistieren.
**Domain:** software
**Priorit�t:** mandatory
**Traceability:** REQ-L0-061

---

## Erweiterung v13 — REQ-L1-089..095 (Unified ArtifactInspector / Right Sidebar)

> **Datum:** 2026-07-06 | **Quelle:** REQ-L0-062 (User-Request "UI Unification of the Right Sidebar")

---

### REQ-L1-089: Unified ArtifactInspector (RightSidebar) Shell

The system MUST provide a single, shared right-sidebar component — the **ArtifactInspector** — that is rendered on every artifact detail page. The shell MUST host a fixed, ordered set of panel slots (VersionPanel, DiffPanel, TracePanel) and MUST support the user actions **collapse** (hide all panels, restoring the full detail area) and **pin** (keep the inspector open while the user navigates between artifacts). The collapse/pin state MUST be persisted per user session.

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified. The existing inline `bidirektionale Traceability-Seitenleiste` (REQ-L3-RF003-003) and `verknuepfte Requirements in Seitenleiste` (REQ-L3-RF004-003) are the only page-local predecessors and are superseded by this requirement.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] Right-sidebar shell rendered on all 10 artifact detail pages (ICD, Diagram, ADR, Risk, Issue, Glossary, Stakeholder Need, Requirement, Architecture, TestCase).
- [ ] Shell exposes three panel slots in fixed order: VersionPanel, DiffPanel, TracePanel.
- [ ] User can collapse and pin the sidebar; state persists per user session (LocalStorage).
- [ ] Inline sidebars of RequirementEditor and ArchitectureEditor are removed and replaced by the unified shell.

**Traceability:** REQ-L0-062, REQ-L0-009 (i18n), REQ-L0-017 (ICD), REQ-L0-018 (ADR/Risk/Issue)
**Derived L2:** REQ-L2-RF-034

---

### REQ-L1-090: VersionPanel inside ArtifactInspector

The system MUST render a **VersionPanel** as the first slot of the ArtifactInspector on every artifact detail page. The VersionPanel MUST list all available versions of the active artifact (newest first), allow the user to switch the displayed version, and display a **baseline indicator** for the currently selected version (e.g. "Part of baseline `BL-PROJ-2026-07-01` (Project, 2026-07-01)").

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] VersionPanel lists all versions of the active artifact, newest first, with version label, author, and timestamp.
- [ ] User can select a version; the detail view re-renders against the selected version.
- [ ] When the selected version is contained in one or more baselines, a baseline indicator is shown (baseline name, scope, date).
- [ ] When no baseline contains the selected version, the indicator shows a neutral "Not in any active baseline" state.
- [ ] VersionPanel degrades gracefully for artifact types without versioning (shows "Single version" state).

**Traceability:** REQ-L0-062, REQ-L0-004 (Baselines), REQ-L0-017 (ICDs)
**Derived L2:** REQ-L2-RF-035

---

### REQ-L1-091: DiffPanel inside ArtifactInspector (field-level diff)

The system MUST render a **DiffPanel** as the second slot of the ArtifactInspector on every artifact detail page. The DiffPanel MUST allow the user to pick any two versions of the active artifact and render a **field-level diff** (added / changed / removed per field) for the artifact payload. For ICDs the diff MUST include semantic fields (precondition, postcondition, invariant) in addition to the structural fields.

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified. The existing `Visuelles Artefakt-Diff` (REQ-L1-040) and `Visuelles Baseline-Diff` (REQ-L1-041) are global views; the DiffPanel is the inline, per-artifact companion.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] DiffPanel exposes two version pickers (from / to) sourced from the VersionPanel.
- [ ] DiffPanel renders a field-level diff grouped by field name, with per-field status (added / changed / removed) and old/new values.
- [ ] For ICDs, semantic fields (precondition, postcondition, invariant) are diffed in addition to structural fields.
- [ ] Empty diff (versions identical) is shown as an explicit "no differences" state, not a blank panel.
- [ ] DiffPanel loading and error states are rendered consistently with the other panels.

**Traceability:** REQ-L0-062, REQ-L0-028 (Visual Diffing), REQ-L0-017 (ICDs)
**Derived L2:** REQ-L2-RF-036

---

### REQ-L1-092: TracePanel inside ArtifactInspector (inbound/outbound links, type filter)

The system MUST render a **TracePanel** as the third slot of the ArtifactInspector on every artifact detail page. The TracePanel MUST display all **inbound** (other artifacts linking to this artifact) and **outbound** (this artifact linking to other artifacts) TraceLinks of the active artifact, grouped by direction and **filterable by TraceLink type** via a multi-select control. Each link entry MUST show: source/target artifact ID, type, direction, and `suspect` flag (per REQ-L0-030 / REQ-L1-043) when applicable.

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified. The existing `Traceability-Anzeige` (REQ-L2-RF-006) and the inline sidebars of RequirementEditor / ArchitectureEditor are predecessors; the TracePanel is the unified successor.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] TracePanel shows two groups: inbound and outbound, each grouped by TraceLink type.
- [ ] A multi-select filter lets the user restrict both groups to one or more TraceLink types.
- [ ] Each link entry shows source/target artifact ID, type, direction, and `suspect` flag when applicable.
- [ ] Clicking a link entry navigates to the linked artifact's detail view (preserving the inspector state).
- [ ] Empty groups are shown with an explicit "No inbound links" / "No outbound links" placeholder, not a blank panel.

**Traceability:** REQ-L0-062, REQ-L0-003 (Traceability), REQ-L0-030 (Suspect), REQ-L0-035 (Cross-Level)
**Derived L2:** REQ-L2-RF-037

---

### REQ-L1-093: Accessibility baseline for ArtifactInspector

The system MUST implement an accessibility baseline for the ArtifactInspector (shell + VersionPanel + DiffPanel + TracePanel) covering: full keyboard navigation with visible focus, focus management when switching artifacts, ARIA roles for landmark/region/tab structures, and screen-reader announcements for state changes (collapse, pin, panel switching, version switching). The accessibility baseline MUST be met in both German and English.

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] Tab order: shell toggle → panel headers (in order) → panel content controls; focus is always visible.
- [ ] Focus is moved to the ArtifactInspector header when the user navigates to a new artifact.
- [ ] ARIA roles: shell = `complementary`; each panel = `region` with `aria-labelledby` referencing its header; collapse/expand = `button` with `aria-expanded`.
- [ ] State changes (collapse, pin, panel switching, version switching) are announced via `aria-live="polite"` regions in the active language.
- [ ] Color contrast meets WCAG 2.1 AA for the diff states (added/changed/removed).

**Traceability:** REQ-L0-062, REQ-L0-009 (i18n)
**Derived L2:** REQ-L2-RF-034 (in scope of the shell), REQ-L2-RF-035..037 (in scope of the panels)

---

### REQ-L1-094: i18n key naming convention for ArtifactInspector (DE/EN)

The system MUST define and use a single i18n key naming convention for the ArtifactInspector and its panels, fully translated for both `de` and `en`. The convention MUST be:

- `sidebar.inspector.*` — shell-level strings (title, collapse, pin, locale-aware labels)
- `sidebar.version.*` — VersionPanel strings
- `sidebar.diff.*` — DiffPanel strings
- `sidebar.trace.*` — TracePanel strings

All user-visible strings of the ArtifactInspector MUST be sourced from this key tree; no hard-coded UI strings are permitted in the shell or any of the three panels.

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] Key tree `sidebar.inspector.*`, `sidebar.version.*`, `sidebar.diff.*`, `sidebar.trace.*` is registered in the i18n catalog.
- [ ] All shell strings and all three panel strings are sourced exclusively from this key tree.
- [ ] Each key has a German (`de`) and an English (`en`) translation; missing translations fail the build.
- [ ] The terminology profile (dev_mode / se_mode, per REQ-L1-014) does not change the key tree; it only changes term labels in payloads.

**Traceability:** REQ-L0-062, REQ-L0-009 (i18n), REQ-L1-016
**Derived L2:** REQ-L2-RF-001 (withwirkend), REQ-L2-RF-034..037

---

### REQ-L1-095: Adoption of ArtifactInspector on all 10 artifact types

The system MUST render the unified ArtifactInspector (REQ-L1-089) on the detail page of every supported artifact type: **ICD, Diagram, ADR, Risk, Issue, Glossary, Stakeholder Need, Requirement, Architecture, TestCase**. For artifact types whose payload is naturally empty for a given panel (e.g. a Glossary entry has no TraceLinks of its own), the corresponding panel MUST show an explicit "Not applicable for this artifact type" state instead of a blank or hidden panel.

**Domain:** software
**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Newly identified.
**Test Status:** Missing
**Acceptance Criteria:**
- [ ] Artifact detail page of each of the 10 artifact types renders the unified ArtifactInspector.
- [ ] Each of the three panels (VersionPanel, DiffPanel, TracePanel) is rendered in every detail page; no panel is silently hidden.
- [ ] When a panel has no meaningful content for a given artifact type, the panel renders an explicit "Not applicable for this artifact type" state in the active language.
- [ ] Adoption covers: ICD (COMP-ICD-001), Diagram (COMP-DS-001), ADR (COMP-AS-013), Risk (COMP-AS-014), Issue (COMP-AS-015), Glossary (L1-032 area), Stakeholder Need (L0 cascade), Requirement (COMP-AS-002), Architecture (COMP-AS-003), TestCase (COMP-AS-004).

**Traceability:** REQ-L0-062, REQ-L0-017 (ICDs), REQ-L0-018 (ADRs/Risks/Issues), REQ-L0-042 (Ontology variety)
**Derived L2:** REQ-L2-RF-034..037 (each panel is the unit of adoption)

### REQ-L1-096: API Security & Secret Management

Das System muss sicherstellen, dass API-Keys und Secrets niemals im Klartext geloggt werden und nicht über URL-Parameter (wie bei SSE) übertragen werden. Mutierende Zugriffe (inkl. MCP-Tools und REST-Endpoints) müssen strikte RBAC- und Ownership-Checks aufweisen.

**Rationale:** Vermeidung von Secret-Leaks und unautorisierten Zugriffen.
**Implementation State:** Planned
**Review Findings:** Abgeleitet aus SYSTEM_AUDIT.md (P-01, P-02, P-03, A-01, S-03).
**Test Status:** Untested
**Domain:** security
**Priorität:** mandatory

---

### REQ-L1-097: Transactional Integrity & Concurrency

Das System muss kritische Hintergrundverarbeitungen, insbesondere den Event-Bus und Dead-Letter-Queues, durch atomare Transaktionsklammern und Row-Locks (z. B. `select_for_update`) absichern.

**Rationale:** Vermeidung von Race-Conditions und Datenverlusten bei parallelen Workern.
**Implementation State:** Planned
**Review Findings:** Abgeleitet aus SYSTEM_AUDIT.md (S-01, S-02, P-07).
**Test Status:** Untested
**Domain:** software
**Priorität:** mandatory

---

### REQ-L1-098: Data Integrity & Tenant Isolation

Das System muss über alle Persistenzmodelle hinweg durchgehende Tenant-Isolation erzwingen (Row-Level-Security). Die Nutzung dynamischer DDL-Befehle (wie das Abschalten von DB-Triggern) in Request-Handlern ist untersagt.

**Rationale:** Gewährleistung der Mandanten-Trennung und Verhinderung von Seiteneffekten durch Request-getriebene DDLs.
**Implementation State:** Planned
**Review Findings:** Abgeleitet aus SYSTEM_AUDIT.md (M-01, A-03).
**Test Status:** Untested
**Domain:** architecture
**Priorität:** mandatory

---

### REQ-L1-099: System Performance & Constraints

Das System muss alle Listen- und Such-Endpoints gegen Ressourcenerschöpfung absichern. Dies beinhaltet das Erzwingen von Max-Limits für Rückgabemengen, Datenbank-seitige Pagination und N+1-Query-Optimierungen durch konsequentes Prefetching.

**Rationale:** Prävention von Denial-of-Service und Sicherstellung gleichbleibender Latenz bei wachsenden Datenmengen.
**Implementation State:** Planned
**Review Findings:** Abgeleitet aus SYSTEM_AUDIT.md (A-04, P-09, P-11, M-03).
**Test Status:** Untested
**Domain:** performance
**Priorität:** mandatory

---

## Master Traceability Matrix

| REQ-L1 | Abgeleitet von REQ-L0 |
|---------|----------------------|
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
| REQ-L1-027 | REQ-L0-016 |
| REQ-L1-028 | REQ-L0-017 |
| REQ-L1-029 | REQ-L0-018 |
| REQ-L1-030 | REQ-L0-019 |
| REQ-L1-031 | REQ-L0-020 |
| REQ-L1-032 | REQ-L0-021 |
| REQ-L1-033 | REQ-L0-022 |
| REQ-L1-034 | REQ-L0-023 |
| REQ-L1-035 | REQ-L0-024 |
| REQ-L1-036 | REQ-L0-024 |
| REQ-L1-037 | REQ-L0-025 |
| REQ-L1-038 | REQ-L0-026 |
| REQ-L1-039 | REQ-L0-027 |
| REQ-L1-040 | REQ-L0-028 |
| REQ-L1-041 | REQ-L0-028 |
| REQ-L1-042 | REQ-L0-029 |
| REQ-L1-056 | REQ-L0-036 |
| REQ-L1-057 | REQ-L0-037 |
| REQ-L1-058 | REQ-L0-003, REQ-L0-017 |
| REQ-L1-059 | REQ-L0-017 |
| REQ-L1-060 | REQ-L0-003 |
| REQ-L1-061 | REQ-L0-003 |
| REQ-L1-062 | REQ-L0-003, REQ-L0-017 |
| REQ-L1-063 | REQ-L0-003 |
| REQ-L1-064 | REQ-L0-038 |
| REQ-L1-065 | REQ-L0-040 |
| REQ-L1-066 | REQ-L0-038 |
| REQ-L1-067 | REQ-L0-039 |
| REQ-L1-068 | REQ-L0-041 |
| REQ-L1-069 | REQ-L0-046 |
| REQ-L1-070 | REQ-L0-043 |
| REQ-L1-071 | REQ-L0-042 |
| REQ-L1-072 | REQ-L0-044 |
| REQ-L1-073 | REQ-L0-045 |
| REQ-L1-074 | REQ-L0-046 |
| REQ-L1-075 | REQ-L0-041 |
| REQ-L1-076 | REQ-L0-047 |
| REQ-L1-077 | REQ-L0-047 |
| REQ-L1-078 | REQ-L0-048 |
| REQ-L1-079 | REQ-L0-049 |
| REQ-L1-080 | REQ-L0-049, REQ-L0-046 |
| REQ-L1-086 | REQ-L0-055 |
| REQ-L1-088 | REQ-L0-056 |
| REQ-L1-085 | REQ-L0-060 |
| REQ-L1-086 | REQ-L0-060 |
| REQ-L1-087 | REQ-L0-061 |
| REQ-L1-089 | REQ-L0-062, REQ-L0-009 (i18n), REQ-L0-017 (ICD), REQ-L0-018 (ADR/Risk/Issue) |
| REQ-L1-090 | REQ-L0-062, REQ-L0-004 (Baselines), REQ-L0-017 (ICDs) |
| REQ-L1-091 | REQ-L0-062, REQ-L0-028 (Visual Diffing), REQ-L0-017 (ICDs) |
| REQ-L1-092 | REQ-L0-062, REQ-L0-003 (Traceability), REQ-L0-030 (Suspect), REQ-L0-035 (Cross-Level) |
| REQ-L1-093 | REQ-L0-062, REQ-L0-009 (i18n) |
| REQ-L1-094 | REQ-L0-062, REQ-L0-009 (i18n) |
| REQ-L1-095 | REQ-L0-062, REQ-L0-017 (ICDs), REQ-L0-018 (ADRs/Risks/Issues), REQ-L0-042 (Ontology variety) |


### REQ-L1-100: i18n-Leak beheben

Rohe Translation-Keys dürfen nicht in der UI angezeigt werden. Bestätigte Fälle: editor.status (ADRs, Risiken, Testfälle), workspace.create.submit (Neuer-Workspace-Button). Alle vergleichbaren Fälle beheben.

**Rationale:** Migration from REQUIREMENTS.md (REQ-004)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-004.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-063

---

### REQ-L1-101: Link-Erstellen-Dialog vereinheitlichen

Ein gemeinsamer CreateTraceLinkDialog wird in Architektur, Impact-Analyse (TraceabilityView) und ADRs verwendet. Enthält Suchfeld, Elementtyp-Filter und zeigt Titel (nicht nur IDs). Öffnet als Modal (kein Layout-Shift).

**Rationale:** Migration from REQUIREMENTS.md (REQ-005)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-005.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-064

---

### REQ-L1-102: Soft-Delete-Statusmodell

Architektur-Elemente, ADRs und Glossar-Einträge können nicht mehr von normalen Nutzern physisch gelöscht werden. Stattdessen: Status outdated/deprecated/deleted (lifecycle_status bei ArchitectureElement/GlossaryTerm; Adr.Status.DELETED). Gelöschte Elemente werden in Normalansicht ausgeblendet (?include_deleted=true für Admin-Zugriff). Hartes Löschen nur via Django Admin. TODO: Requirements/StakeholderNeeds haben unvalidiertes status-Feld — Soft-Delete dort in separatem Ticket nachziehen.

**Rationale:** Migration from REQUIREMENTS.md (REQ-006)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-006.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-065

---

### REQ-L1-103: Splitter-Fix und Badge-Kürzel

Splitter-Hitbox auf min. 8px verbreitern (Anforderungen, Diagramme). Element-Typ-Badges auf Kürzel reduzieren (SysRec→SR, Component→C etc.) in Baum-Ansichten.

**Rationale:** Migration from REQUIREMENTS.md (REQ-007)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-007.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-066

---

### REQ-L1-104: KI-Ableitungs-Button

KI-Ableitungs-Button in Bedarfe muss Ergebnis anzeigen (kein stilles Versagen): Fehler rot mit role="alert", Erfolg in normaler Textfarbe. Anforderungen-View erhält den gleichen AI-Derivation-Button wie Bedarfe (✨ Ableiten via decompose-next-level).

**Rationale:** Migration from REQUIREMENTS.md (REQ-008)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-008.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-067

---

### REQ-L1-105: Validation-Fehlermeldungen

Beim Speichern in Anforderungen werden alle Validierungsfehler mit Feldname und Beschreibung angezeigt, nicht nur "validation failed".

**Rationale:** Migration from REQUIREMENTS.md (REQ-009)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-009.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-068

---

### REQ-L1-106: Tags-Implementierung (Probleme)

Tags in der Probleme-Ansicht müssen funktionsfähig sein: hinzufügen (Enter/Komma), entfernen (X-Klick), speichern und nach Reload anzeigen.

**Rationale:** Migration from REQUIREMENTS.md (REQ-010)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-010.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-069

---

### REQ-L1-107: Testlauf abschließen

Der "Confirm/Abschließen"-Button in Testläufen muss den Testlauf sichtbar abschließen: TestRuns ohne Testergebnisse müssen einen terminalen Status ("closed") erhalten statt bei "in_progress" zu verharren; nach dem Abschließen zeigt die Detailansicht eine Erfolgsmeldung statt kommentarlos zu schließen; Fehler werden sichtbar angezeigt.

**Rationale:** Migration from REQUIREMENTS.md (REQ-012)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-012.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-070

---

### REQ-L1-108: Lifecycle-Status für Requirements und Stakeholder-Needs

Requirements und StakeholderNeeds erhalten lifecycle_status-Feld (active/deprecated/archived). Soft-Delete statt physisches Löschen implementieren — gelöschte Elemente in UI ausgeblendet, nur für Admin sichtbar via ?include_deleted=true.

**Rationale:** Migration from REQUIREMENTS.md (REQ-013)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-013.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-071

---

### REQ-L1-109: Item-Permissions User-Picker

Must — Ein neuer GET-Endpoint (z.B. /api/v1/workspaces/{id}/members/) liefert die Workspace-Mitgliederliste mit mind. user_id, Anzeigename und E-Mail-Adresse. PermissionsSection.tsx ersetzt das fehleranfällige UUID-Freitext-Eingabefeld durch ein Dropdown oder Autocomplete-Feld, das Workspace-Mitglieder nach Name oder E-Mail durchsuchbar macht und die user_id automatisch befüllt. Akzeptanzkriterien: 1. Der neue Endpoint ist nur für authentifizierte Workspace-Mitglieder erreichbar. 2. Das bestehende ItemPermission-Datenmodell (permission_level: read/write/none) sowie das RBAC-Rollenmodell (admin/editor/viewer/approver) bleiben semantisch unverändert. 3. Vorhandene Item-Permissions funktionieren nach dem Update weiterhin korrekt. 4. Das Workflows-Redesign (WorkflowsSection.tsx) ist explizit nicht Teil dieser Anforderung.

**Rationale:** Migration from REQUIREMENTS.md (REQ-014)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-014.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-072

---

### REQ-L1-110: Workspace-Einstellungen Redesign

Die Workspace-Einstellungen-Ansicht wird von einer vertikalen Liste inkonsistenter Karten zu einer klaren Sektions-/Tab-Struktur umgebaut. Einheitliches Karten-/Formular-Layout (gemeinsamer Card-Style analog ApiKeysSection) über alle Panels; Gruppierung der Einstellungen in Tabs (Allgemein, Traceability, Sichtbarkeit, LLM & Prompts, Workflows & Berechtigungen, Administration). Bestehende Funktionalität und Feature-Flags (Baselines/Backup-Restore) bleiben erhalten. Reines Frontend-Redesign ohne funktionale Änderungen an den Subkomponenten.

**Rationale:** Migration from REQUIREMENTS.md (REQ-015)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-015.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-073

---

### REQ-L1-111: Custom Fields workspace-weit

Workspace-Administratoren können für einen Workspace benutzerdefinierte Felder (Custom Fields) mit Name, Typ (Text, Zahl oder Dropdown mit vordefinierten Optionen) und Pflichtfeld-Kennzeichen definieren. Die Felddefinitionen gelten workspace-weit und stehen an allen Artefakten (Requirements, Architecture Elements, Testfälle etc.) als zusätzliche Eingabefelder zur Verfügung. Eingetragene Werte werden je Artefakt-Instanz persistiert und sind nach Reload abrufbar. Die Verwaltung der Felddefinitionen erfolgt über die Workspace-Einstellungen.

**Rationale:** Migration from REQUIREMENTS.md (REQ-016)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-016.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-074

---

### REQ-L1-112: API-Key-Klartext-Logging entfernen

API-Keys dürfen nicht im Klartext in Logs protokolliert werden. Debug-Log-Zeilen in mcp_server/views.py:59-62 entfernen; nur maskierte Präfixe (rfk_…xxxx) auf DEBUG-Level erlaubt. (SYSTEM_AUDIT P-01)

**Rationale:** Migration from REQUIREMENTS.md (REQ-017)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-017.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-075

---

### REQ-L1-113: API-Key aus SSE-Endpoint-URL entfernen

API-Key darf nicht als Query-Parameter in SSE-Endpoint-URLs übergeben werden. Session-Binding erfolgt serverseitig via Session-Token statt Key in URL (mcp_server/views.py:219). (SYSTEM_AUDIT P-02)

**Rationale:** Migration from REQUIREMENTS.md (REQ-018)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-018.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-076

---

### REQ-L1-114: IDOR-Fix ApiKeyViewSet.destroy

ApiKeyViewSet.destroy muss Ownership-Check durchführen. Fremde API-Keys werden mit HTTP 404 abgelehnt, nicht 403 (backend/rest_api/api_key_views.py). (SYSTEM_AUDIT A-01)

**Rationale:** Migration from REQUIREMENTS.md (REQ-019)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-019.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-077

---

### REQ-L1-115: Event-Bus Race-Condition: atomare Claims

DomainEventBus.poll_and_dispatch() nutzt atomare Row-Locks (select_for_update(skip_locked=True) in transaction.atomic()) um Race-Conditions und Event-Doppelverarbeitung bei mehreren Celery-Workern auszuschließen. (SYSTEM_AUDIT S-01)

**Rationale:** Migration from REQUIREMENTS.md (REQ-020)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-020.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-078

---

### REQ-L1-116: DLQ-Move atomar durchführen

DomainEventBus DLQ-Move erfolgt atomar: DLQ-Insert und Outbox-Update in einer transaction.atomic()-Klammer, um Datenverlust/Doppelverarbeitung bei Ausfällen auszuschließen. (SYSTEM_AUDIT S-02)

**Rationale:** Migration from REQUIREMENTS.md (REQ-021)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-021.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-079

---

### REQ-L1-117: StakeholderNeedService RBAC-Gate

StakeholderNeedService.create() implementiert RBAC-Gate: Permission-Check (Rolle + Workspace-Berechtigung) am Service-Eingang vor Erzeugung (backend/application/stakeholder_need_service.py). (SYSTEM_AUDIT S-03)

**Rationale:** Migration from REQUIREMENTS.md (REQ-022)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-022.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-080

---

### REQ-L1-118: WorkspaceService.clone_workspace() Hierarchie-Fix

WorkspaceService.clone_workspace() nutzt old_id→new_instance-Map zur korrekten Parent-Child-Hierarchie in geklonten Workspaces. Regressionstest mit ≥2 Ebenen Tiefe erforderlich. (SYSTEM_AUDIT S-04)

**Rationale:** Migration from REQUIREMENTS.md (REQ-023)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-023.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-081

---

### REQ-L1-119: Frontend Prod-Build reparieren

Frontend Dockerfile kopiert package-lock.json nicht (Zeile 8) und nutzt `npm ci --only=production` (Zeile 24) — Build-Toolchain (tsc/vite) fehlt im Image, Prod-Build schlägt hart fehl. Fix: package-lock.json COPY ergänzen, --only=production entfernen. Zusätzlich VITE_* als Build-Args durchreichen (docker-compose.yml:150-153). Referenz: DEEP_SYSTEM_ANALYSIS.md FE-1/INF-1

**Rationale:** Migration from REQUIREMENTS.md (REQ-024)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-024.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-082

---

### REQ-L1-120: eslint-plugin-react-hooks aktivieren

eslint-plugin-react-hooks ist nicht installiert — keinerlei Hook-Prüfung (rules-of-hooks, exhaustive-deps) im Projekt. Plugin in package.json ergänzen und in eslint.config.js aktivieren. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-2

**Rationale:** Migration from REQUIREMENTS.md (REQ-025)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-025.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-083

---

### REQ-L1-121: CI-Pipeline für pytest, Vitest und Lint

Einziger CI-Workflow ist playwright.yml (E2E). Kein CI für die 1042 Backend-pytest-Tests, kein Vitest, kein ESLint/mypy. GitHub Actions Workflow anlegen: backend-pytest-Job, frontend-vitest-Job, lint-Job. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-2

**Rationale:** Migration from REQUIREMENTS.md (REQ-026)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-026.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-084

---

### REQ-L1-122: Backend runserver durch gunicorn/uvicorn ersetzen

backend/Dockerfile:32 und docker-compose.yml:100-102 nutzen Django-Dev-Server (runserver) als Prod-Kommando — single-threaded, nicht produktionsgeeignet. Ersetzen durch gunicorn oder uvicorn, collectstatic aktivieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-3

**Rationale:** Migration from REQUIREMENTS.md (REQ-027)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-027.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-085

---

### REQ-L1-123: Source-Bind-Mounts aus Production-Compose entfernen

docker-compose.yml:91-92 und :128-129 mounten ./backend:/app und ./frontend:/app als Volumes in die als "Production-Ready" bezeichnete Compose — Source-Code-Mounts gehören in docker-compose.override.yml. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-4

**Rationale:** Migration from REQUIREMENTS.md (REQ-028)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-028.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-086

---

### REQ-L1-124: Postgres/Redis Host-Ports nicht publishen

docker-compose.yml:39-40 (Postgres 5432) und :54-55 (Redis 6379) publishen Ports auf den Host — widerspricht dem eigenen Security-Kommentar in Zeile 24. Ports aus der Production-Compose entfernen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-5

**Rationale:** Migration from REQUIREMENTS.md (REQ-029)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-029.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-087

---

### REQ-L1-125: Celery-Beat-Service in docker-compose ergänzen

docker-compose.yml enthält keinen celery-beat-Service — periodische Tasks (inkl. Outbox-Consumer BE-1) können nie feuern. Dedizierter beat-Service mit korrektem Command und depends_on ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-6

**Rationale:** Migration from REQUIREMENTS.md (REQ-030)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-030.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-088

---

### REQ-L1-126: nginx SPA-Routing (History-API-Fallback)

frontend/Dockerfile:35-36 hat TODO für nginx.conf — Deep-Links in der React-SPA liefern 404, da nginx keine try_files-Regel für index.html hat. nginx.conf mit SPA-Fallback ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-7

**Rationale:** Migration from REQUIREMENTS.md (REQ-031)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-031.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-089

---

### REQ-L1-127: Outbox-Consumer als Celery-Beat-Task registrieren

backend/application/event_bus.py:242 definiert poll_and_dispatch(), wird aber von keinem Celery-Task, keinem Beat-Schedule und keinem Management-Command aufgerufen — Outbox füllt sich, Events werden nie dispatcht. Als periodischen Beat-Task registrieren (z.B. alle 5 s). Referenz: DEEP_SYSTEM_ANALYSIS.md BE-1

**Rationale:** Migration from REQUIREMENTS.md (REQ-032)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-032.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-090

---

### REQ-L1-128: Django CACHES auf Redis konfigurieren

backend/reqflow/settings.py enthält keine CACHES-Konfiguration — Django fällt auf LocMemCache (pro-Prozess, unsynchronisiert) zurück. Root-Cause für alle 4 In-Process-Caches. Redis-Cache-Backend konfigurieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-2

**Rationale:** Migration from REQUIREMENTS.md (REQ-033)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-033.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-091

---

### REQ-L1-129: _paginate auf QuerySet-Slicing umstellen

BaseEntityViewSet._paginate (backend/rest_api/views.py:160) materialisiert vollständige Listen vor der Paginierung — alle 16 ViewSet-List-Endpoints sind O(N) in Speicher und Zeit. Auf DRF-Paginator mit QuerySet-Slicing umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-3

**Rationale:** Migration from REQUIREMENTS.md (REQ-034)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-034.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-092

---

### REQ-L1-130: SSE-PubSub Redis-Connection-Pool

backend/mcp_server/sse_pubsub.py:31-49 öffnet pro Publish-Call eine neue Redis-Connection statt einen Connection-Pool zu verwenden. Auf redis.ConnectionPool umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-4

**Rationale:** Migration from REQUIREMENTS.md (REQ-035)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-035.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-093

---

### REQ-L1-131: API-Key in Redis mit Django-Signing absichern

backend/mcp_server/sse_pubsub.py:33 speichert den Roh-API-Key als Redis-Value — schwächt den REQ-018-Fix. Reversible Verschlüsselung (Django-Signing) statt Klartext speichern und Vergleich entsprechend anpassen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-5

**Rationale:** Migration from REQUIREMENTS.md (REQ-036)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-036.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-094

---

### REQ-L1-132: pytest auf dedizierte Test-Settings umstellen

backend/pyproject.toml konfiguriert pytest gegen Prod-Settings — Tests erben Prod-Cache-, Celery- und LLM-Einstellungen. Dedizierte backend/reqflow/settings_test.py anlegen und in pyproject.toml referenzieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-6

**Rationale:** Migration from REQUIREMENTS.md (REQ-037)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-037.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-095

---

### REQ-L1-133: Cache-Invalidierungsstrategie implementieren

Die 4 In-Process-Caches haben keine Invalidierungsstrategie — Schreiboperationen eines Workers sind für andere unsichtbar. Nach BE-2/REQ-033: Signal-basierte Invalidierung (post_save/post_delete) oder TTL-Strategie für alle django.core.cache-Nutzungen definieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-7

**Rationale:** Migration from REQUIREMENTS.md (REQ-038)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-038.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-096

---

### REQ-L1-134: Composite-Indexes für dominante Filterkombinationen

backend/persistence/models.py fehlen Composite-Indexes für die häufigsten Filterkombinationen (tenant_id+workspace+type, tenant_id+status) — Row-Level-Security filtert immer auf tenant_id, ListEndpoints zusätzlich auf workspace/type/status. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-8

**Rationale:** Migration from REQUIREMENTS.md (REQ-039)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-039.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-097

---

### REQ-L1-135: Multi-Worker-Konsistenz Deployment-Constraint dokumentieren

Bis BE-2/REQ-033 und BE-7/REQ-038 vollständig umgesetzt sind, machen In-Process-Caches + fehlende Invalidierung jedes Deployment mit >1 Worker inkonsistent. Constraint explizit in settings.py und Deployment-Docs dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-9

**Rationale:** Migration from REQUIREMENTS.md (REQ-040)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-040.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-098

---

### REQ-L1-136: derive_requirements in Anthropic/Ollama/Azure implementieren

llm_adapter/interface.py:136 deklariert derive_requirements als @abstractmethod. Nur MockLlmProvider und OpenAiProvider implementieren es — Anthropic (providers.py:366), Ollama (providers.py:640) und Azure (providers.py:736) werfen beim Instanziieren TypeError. Alle drei Provider implementieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F2.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-041)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-041.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-099

---

### REQ-L1-137: Async-LLM-Pfad reparieren

dispatcher.py:66-97 instanziiert ad-hoc eine neue Celery-App im Web-Prozess und sendet llm_adapter.run_capability — ein Task-Name, den der Worker (reqflow/celery.py) nie registriert hat. Broker nimmt Message an, Worker verwirft sie, Status bleibt ewig PENDING. Task korrekt im Worker registrieren und Dispatcher anpassen. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-042)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-042.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-100

---

### REQ-L1-138: RBAC-Bypass: fehlende MCP-Tool-Prefixes ergänzen

mcp_server/tool_registry.py:52-77 klassifiziert Schreib-Tools per Prefix-Liste — needs.*, adr.*, risk.*, issue.*, glossary.*, prompt_template.* fehlen. Ein API-Key mit Viewer-Rolle kann darüber Daten schreiben; prompt_template.*-Write ermöglicht persistente Prompt-Injection. Alle fehlenden Prefixes in _WRITE_TOOL_PREFIXES aufnehmen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-043)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-043.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-101

---

### REQ-L1-139: SSE-GET-Crash und Handshake-Auth beheben

mcp_server/views.py:62-78 kombiniert synchrones CorsMixin.dispatch mit async def get → TypeError bei jedem GET /mcp/sse/. Zusätzlich fehlt API-Key-Check beim Handshake (DoS-Vektor). Sync/Async-Konflikt auflösen und Auth beim Handshake ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.2

**Rationale:** Migration from REQUIREMENTS.md (REQ-044)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-044.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-102

---

### REQ-L1-140: requirement.validate TypeError beheben

mcp_server/tools/requirements.py:425 ruft validate_artifact(str(req_id), ctx=auth_context) auf — die Facade akzeptiert nur artifact_id (kein ctx-Parameter). Jeder Aufruf endet im TypeError. Signatur-Mismatch korrigieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F1.2

**Rationale:** Migration from REQUIREMENTS.md (REQ-045)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-045.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-103

---

### REQ-L1-141: Artefakt-Inhalt in LLM-Provider-Prompts aufnehmen

Provider-Prompt-Builder (providers.py:431,541,621,717,810) interpolieren nur Artefakt-UUIDs, nie den Artefakt-Inhalt. LLM halluziniert bei decompose/validate/check_consistency zwangsläufig. Artefakt-Inhalt aus dem Repository laden und in Prompt einbetten. Referenz: DEEP_SYSTEM_ANALYSIS.md F3.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-046)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-046.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-104

---

### REQ-L1-142: JSON-RPC-Error-Format auf Spec bringen

mcp_server/protocol_handler.py:154-165 gibt Fehler als {"error_code": "...", "message": "..."} zurück statt {"code": <int>, "message": <str>} gemäß JSON-RPC 2.0 Spec — Standard-MCP-Clients sind inkompatibel. Format korrigieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F8.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-047)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-047.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-105

---

### REQ-L1-143: LLM-Interface-Vertrag vervollständigen

complete() existiert auf Providern aber nicht im Interface (kein statischer Vertrag). OpenAI-derive_requirements greift auf nicht existentes self._model zu, verletzt Layer-Grenzen durch direkten Persistence-Zugriff und nutzt print statt logger. Interface vervollständigen und OpenAI-Implementierung bereinigen. Referenz: DEEP_SYSTEM_ANALYSIS.md F2.2/F2.3

**Rationale:** Migration from REQUIREMENTS.md (REQ-048)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-048.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-106

---

### REQ-L1-144: React-Query-Migration (State Management)

Handgerollte use*Data-Hooks (useAdrData, useRiskData, useIssueData, useNeedData, useArchitectureData) auf @tanstack/react-query migrieren — behebt gleichzeitig fehlendes AbortController-Cleanup (FE-6), klebenden Error-State (FE-7) und Fünffach-Duplikation (FE-4). React Query ist bereits installiert und in 4 Dateien genutzt. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-3/FE-4/FE-6/FE-7

**Rationale:** Migration from REQUIREMENTS.md (REQ-049)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-049.
**Test Status:** Missing
**Remarks:** Architektur

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-107

---

### REQ-L1-145: Monster-Komponenten zerlegen

5 Komponenten >= 1000 Zeilen (CanvasEditor.tsx 1605, IcdView.tsx 1483, BaselinesView.tsx 1461, DiagramView.tsx 1036, TestRunsList.tsx 1000) mischen Datenladen, UI-State, Formular-Logik und Rendering. Container/Presenter-Trennung + Fetch-Logik in Query-Hooks auslagern. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-5

**Rationale:** Migration from REQUIREMENTS.md (REQ-050)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-050.
**Test Status:** Missing
**Remarks:** Architektur

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-108

---

### REQ-L1-146: 401/403-Unterscheidung im API-Client

frontend/src/api/client.ts:64-74 behandelt 401 und 403 identisch — 403 (Berechtigungsfehler) loggt den User aus statt "keine Berechtigung" anzuzeigen. Separate Handler für 401 (Logout) und 403 (Fehlermeldung ohne Logout). Referenz: DEEP_SYSTEM_ANALYSIS.md FE-8

**Rationale:** Migration from REQUIREMENTS.md (REQ-051)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-051.
**Test Status:** Missing
**Remarks:** UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-109

---

### REQ-L1-147: Auth-Token aus sessionStorage entfernen

frontend/src/context/AuthContext.tsx:93,149 speichert Auth-Token in sessionStorage — XSS-lesbar. Auf httpOnly-Cookie (bevorzugt) oder In-Memory-Storage + Refresh-Token-Rotation umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-9. Umgesetzt: httpOnly-Cookie `reqflow_access` (SameSite=Lax, Secure außer DEBUG), Dual-Read (Header+Cookie), CSRF-Enforcement für Cookie-Pfad, POST /auth/logout/, /auth/me/-Bootstrap; sessionStorage-Token/-User entfernt.

**Rationale:** Migration from REQUIREMENTS.md (REQ-052)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-052.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-110

---

### REQ-L1-148: Frontend-Testabdeckung große Views

Die 5 größten, ungetesteten Views (IcdView, DiagramView, BaselinesView, ArtifactDiff, TraceabilityView) sowie alle use*Data-Hooks sind nicht getestet. Tests ergänzen — mindestens Smoke-Tests für Render und Hauptinteraktionen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-10

**Rationale:** Migration from REQUIREMENTS.md (REQ-053)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-053.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-111

---

### REQ-L1-149: Code-Splitting via React.lazy

mermaid (~2 MB) und fabric landen im monolithischen Haupt-Bundle. React.lazy + Suspense für DiagramView.tsx und CanvasEditor.tsx einführen. frontend/src/App.tsx anpassen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-11

**Rationale:** Migration from REQUIREMENTS.md (REQ-054)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-054.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-112

---

### REQ-L1-150: i18n konsequent ausrollen

i18next/react-i18next ist in 71 Frontend-Dateien aktiv genutzt (useTranslation); die ursprüngliche Analyse-Prämisse "nur 3 Dateien" war falsch. Die Dependency soll bleiben. Offene Aufgaben: fehlende Übersetzungsschlüssel vervollständigen (DE/EN), alle raw-string-Literals in noch nicht migrierten Komponenten durch t()-Aufrufe ersetzen, Translation-Files auf Vollständigkeit prüfen und ggf. Namespacing einführen.

**Rationale:** Migration from REQUIREMENTS.md (REQ-055)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-055.
**Test Status:** Missing
**Remarks:** DX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-113

---

### REQ-L1-151: Accessibility-Basisabsicherung

Nur 20 aria-/role-Treffer in 10 von 117 Komponenten. eslint-plugin-jsx-a11y in frontend/eslint.config.js ergänzen + aktivieren. Offensichtliche A11y-Fehler in häufig genutzten Komponenten beheben. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-13

**Rationale:** Migration from REQUIREMENTS.md (REQ-056)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-056.
**Test Status:** Missing
**Remarks:** Accessibility

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-114

---

### REQ-L1-152: Redis absichern

docker-compose.yml:51-61 konfiguriert Redis ohne Passwort, ohne maxmemory-Policy und ohne Persistenz. requirepass setzen, maxmemory + maxmemory-policy volatile-lru konfigurieren, AOF-Persistenz für Broker-Zuverlässigkeit aktivieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-8

**Rationale:** Migration from REQUIREMENTS.md (REQ-057)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-057.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-115

---

### REQ-L1-153: Unsichere DB-Password-Defaults entfernen

docker-compose.yml:36,78,119 nutzt DB_PASSWORD:-reqflow als stillen Trivial-Passwort-Default. Fail-Fast-Verhalten: Fehler wenn DB_PASSWORD nicht gesetzt, kein Default. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-9

**Rationale:** Migration from REQUIREMENTS.md (REQ-058)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-058.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-116

---

### REQ-L1-154: USER-Direktive in Dockerfiles

backend/Dockerfile und frontend/Dockerfile laufen Container als root — kein USER definiert. Dedizierten Non-Root-User anlegen und als USER setzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-10

**Rationale:** Migration from REQUIREMENTS.md (REQ-059)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-059.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-117

---

### REQ-L1-155: Healthchecks für Backend und Celery

docker-compose.yml:66-102,142-157 hat keine Healthchecks für backend- und celery-Service. depends_on ohne condition wartet nicht auf Backend-Readiness. Healthcheck-Direktiven für beide Services ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-11

**Rationale:** Migration from REQUIREMENTS.md (REQ-060)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-060.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-118

---

### REQ-L1-156: Backend-Dockerfile Multi-Stage

backend/Dockerfile ist Single-Stage: gcc/libpq-dev (~150 MB Build-Dependencies) verbleiben im Runtime-Image. Multi-Stage-Build: Builder-Stage mit Dev-Dependencies, Runtime-Stage nur mit installierten Packages. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-12

**Rationale:** Migration from REQUIREMENTS.md (REQ-061)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-061.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-119

---

### REQ-L1-157: Secrets nicht als Compose-Env-Variables

docker-compose.yml:73,115 gibt Secrets direkt als environment-Werte an Container (via docker inspect lesbar). Auf env_file mit .env-Datei oder Docker Secrets umstellen. Trennung von Infra-Config und Secrets dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-13

**Rationale:** Migration from REQUIREMENTS.md (REQ-062)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-062.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-120

---

### REQ-L1-158: Observability-Grundausstattung

Keinerlei Metriken-, Tracing- oder Log-Aggregations-Infrastruktur vorhanden. Mindest-Maßnahmen: strukturierte JSON-Logs (django-structlog oder python-json-logger), /metrics-Endpoint (django-prometheus), Celery-Task-Metriken, Outbox-Backlog-Gauge. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-14

**Rationale:** Migration from REQUIREMENTS.md (REQ-063)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-063.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-121

---

### REQ-L1-159: Migration aus Container-Startkommando lösen

docker-compose.yml:100-102 führt migrate im Startkommando aus — Race-Condition bei mehreren Replicas. Dedizierter Init-Container oder Startup-Job für Migrationen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-15

**Rationale:** Migration from REQUIREMENTS.md (REQ-064)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-064.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-122

---

### REQ-L1-160: CI loaddata Fixture-Fehler sichtbar machen

.github/workflows/playwright.yml:65 nutzt loaddata initial_data

**Rationale:** Migration from REQUIREMENTS.md (REQ-065)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-065.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-123

---

### REQ-L1-161: Service-Layer-Grenzen schärfen

Option B (Django-idiomatisch): kein direkter ORM-Zugriff in rest_api/ (Views), ORM gekapselt in Application-/Domain-Services; wiederverwendete/komplexe Queries in Custom Manager/QuerySets. Phase 1 (Writes aus Views, 34de8ab–d85ba5d), Phase 2 (Reads: ArtifactService.list_child_summaries/resolve_artifact_titles/collect_artifact_names, Commit b50ed5c) und Phase 3 (BE-10-Hotspot allocation_coverage → TraceLinkService.get_requirement_allocations, Latent-Bug get_with_level gefixt, Commit b013d0c) vollständig abgeschlossen. views.py ist jetzt vollständig ORM-frei (Guardrail-Ratchet auf 0). Referenz: DEEP_SYSTEM_ANALYSIS.md BE-10

**Rationale:** Migration from REQUIREMENTS.md (REQ-066)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-066.
**Test Status:** Missing
**Remarks:** Architektur

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-124

---

### REQ-L1-162: factory-boy-Entscheidung

factory-boy ist in backend/requirements.txt deklariert, wird aber nirgends genutzt (alle Fixtures manuell). Entscheidung: entweder key-Fixtures auf factory-boy migrieren oder Dependency aus requirements.txt streichen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-11

**Rationale:** Migration from REQUIREMENTS.md (REQ-067)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-067.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-125

---

### REQ-L1-163: conftest.py-Fossil bereinigen

backend/conftest.py enthält tote Fixtures/Konfiguration. Aufräumen: tote Fixtures entfernen, aktive Fixtures kommentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-12

**Rationale:** Migration from REQUIREMENTS.md (REQ-068)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-068.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-126

---

### REQ-L1-164: Outbox-Monitoring: Backlog-Gauge

backend/application/event_bus.py exponiert weder Backlog-Größe noch DLQ-Umfang als Metrik oder Log. Nach poll_and_dispatch() Backlog-Größe und DLQ-Count loggen (INFO-Level) damit stilles Liegenbleiben erkennbar wird. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-13

**Rationale:** Migration from REQUIREMENTS.md (REQ-069)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-069.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-127

---

### REQ-L1-165: N+1-Audit für alle 16 ViewSets

backend/rest_api/views.py und serializers.py haben in mehreren ViewSets fehlende select_related/prefetch_related-Aufrufe. Alle 16 ViewSets auditieren, N+1-Stellen mit select_related/prefetch_related beheben. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-14

**Rationale:** Migration from REQUIREMENTS.md (REQ-070)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-070.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-128

---

### REQ-L1-166: API-Fehlerformat-Konsistenz (REST vs. MCP)

DRF-Endpoints und MCP-Server (backend/mcp_server/protocol_handler.py) geben unterschiedliche Fehlerformate zurück. Gemeinsames Error-Envelope definieren und beide Seiten darauf vereinheitlichen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-15

**Rationale:** Migration from REQUIREMENTS.md (REQ-071)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-071.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-129

---

### REQ-L1-167: Celery-Task-Idempotenz für Outbox-Dispatch

Outbox-Dispatch braucht at-least-once-taugliche, idempotente Handler. Jeder Handler muss bei Wiederholung dasselbe Ergebnis liefern (Idempotenz-Key oder Datenbank-Constraint). Referenz: DEEP_SYSTEM_ANALYSIS.md BE-16

**Rationale:** Migration from REQUIREMENTS.md (REQ-072)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-072.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-130

---

### REQ-L1-168: Transaktionsgrenzen dokumentieren

Unklar welche Service-Methoden in atomic() laufen und wann Domain-Events relativ zum Commit gefeuert werden. Transaktionsgrenzen in backend/application/** durch Inline-Kommentare und/oder eine Tabelle im ARCHITECTURE.md dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-17

**Rationale:** Migration from REQUIREMENTS.md (REQ-073)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-073.
**Test Status:** Missing
**Remarks:** Dokumentation

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-131

---

### REQ-L1-169: DB-Query-Logging in Dev aktivieren

backend/reqflow/settings.py hat kein LOGGING-Setup für SQL-Queries in Dev. django-silk oder LOGGING['django.db.backends'] auf DEBUG in Test-/Dev-Settings aktivieren um O(N)- und N+1-Regressionen sichtbar zu machen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-18

**Rationale:** Migration from REQUIREMENTS.md (REQ-074)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-074.
**Test Status:** Missing
**Remarks:** DX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-132

---

### REQ-L1-170: Test-Pyramide rebalancieren + Wiring-Tests

1042 grüne Tests haben toten Async-Pfad, crashendes SSE und nicht instanziierbare Provider nicht erkannt. Wiring-Tests ergänzen: jeder Celery-Task registriert, jeder Beat-Eintrag vorhanden, jede URL antwortet mit korrekter Server-Klasse. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-19

**Rationale:** Migration from REQUIREMENTS.md (REQ-075)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-075.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-133

---

### REQ-L1-171: Paginierungs-Verträge in OpenAPI dokumentieren

Paginierungsverhalten (Cursor vs. Offset, Seitengröße, Gesamtzahl) ist nicht explizit definiert. In OpenAPI-Schema via drf-spectacular verankern; Paginierungsparameter als standardisierte Query-Params dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-20

**Rationale:** Migration from REQUIREMENTS.md (REQ-076)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-076.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-134

---

### REQ-L1-172: Celery-Routing/Queues definieren

backend/reqflow/celery.py nutzt Single-Queue für alle Tasks. Separate Queues für LLM-Tasks (llm), Events (events) und Standard-Tasks (default) definieren — Voraussetzung für getrennte Skalierung. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-21

**Rationale:** Migration from REQUIREMENTS.md (REQ-077)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-077.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-135

---

### REQ-L1-173: Stiller Mock-Fallback markieren

backend/application/ai_derivation_service.py:342-345 fällt bei jedem LLM-Fehler still auf MockProvider zurück — Nutzer erhält unmarkierten Fake-Content. Fallback-Ergebnisse als provider: "mock-fallback" kennzeichnen und im Response-Body ausweisen; besser: Fehler propagieren statt still faken. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.3

**Rationale:** Migration from REQUIREMENTS.md (REQ-078)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-078.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-136

---

### REQ-L1-174: Echte Input-Schemas für 11 MCP-Tool-Gruppen

backend/mcp_server/tools/base.py:125-146 fällt für 11 von 14 Tool-Gruppen auf {"kwargs": {"type": "object"}} zurück — MCP-Clients sehen keine Parameternamen oder -typen. Jede Tool-Gruppe bekommt ein konkretes JSON-Schema mit expliziten Parameter-Definitionen. Referenz: DEEP_SYSTEM_ANALYSIS.md F1.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-079)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-079.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-137

---

### REQ-L1-175: Prompt-Injection-Oberfläche reduzieren

backend/llm_adapter/providers.py (alle Prompt-Builder) interpolieren User-Content ungefiltert ohne Delimiter oder Escaping in Prompts. Delimiter-basiertes Escaping oder Instruction-Hierarchie (System/User-Trennung) einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.3

**Rationale:** Migration from REQUIREMENTS.md (REQ-080)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-080.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-138

---

### REQ-L1-176: Klartext-Secrets in Persistenz beseitigen

API-Key als Klartext in Redis (sse_pubsub.py:33, schwächt REQ-036-Fix), Provider-api_key im Klartext in Postgres (persistence/models.py:1217), CORS * mit Credentials-Flag. Alle Stellen auf sichere Speicherung umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.4

**Rationale:** Migration from REQUIREMENTS.md (REQ-081)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-081.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-139

---

### REQ-L1-177: Retry/Circuit-Breaker für LLM-Calls

backend/resilience/-Modul existiert, wird aber nicht genutzt. LLM-Provider-Aufrufe in providers.py durch Retry-Wrapper (exponential backoff, max 3 Versuche) und Circuit-Breaker aus dem vorhandenen resilience/-Modul schützen. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.2

**Rationale:** Migration from REQUIREMENTS.md (REQ-082)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-082.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-140

---

### REQ-L1-178: Tenant-LLM-Settings in Celery-Worker propagieren

backend/llm_adapter/dispatcher.py übergibt per-Tenant-Provider-Konfiguration nicht an den Worker — wirkt nur im Sync-Pfad. Worker-Task muss Tenant-ID erhalten und Settings zur Laufzeit laden. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.4

**Rationale:** Migration from REQUIREMENTS.md (REQ-083)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-083.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-141

---

### REQ-L1-179: Sync-LLM-Call auf Async-Pfad umlenken

Nach REQ-042-Fix (Async-Pfad repariert): Sync-LLM-Calls in backend/llm_adapter/ blockieren den Request-Thread bis 30 s (Gunicorn-Worker-Erschöpfung). Auf den reparierten Async-Pfad umlenken oder zumindest Timeout setzen. Referenz: DEEP_SYSTEM_ANALYSIS.md F5.2

**Rationale:** Migration from REQUIREMENTS.md (REQ-084)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-084.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-142

---

### REQ-L1-180: Contract-Tests Provider + SSE-E2E-Tests

Keine Contract-Tests die Provider gegen Interface-Vertrag prüfen (hätte F2.1 sofort gefangen). SSE-E2E-Tests testen tote API-Form (POST statt GET). Contract-Tests für alle 5 Provider + echte SSE-GET-E2E-Tests schreiben. Referenz: DEEP_SYSTEM_ANALYSIS.md F7.1/F7.2

**Rationale:** Migration from REQUIREMENTS.md (REQ-085)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-085.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-143

---

### REQ-L1-181: MCP-Tool-Fehler als isError-Result + Thread-Pool

backend/mcp_server/protocol_handler.py meldet Tool-Fehler als JSON-RPC-Error statt als isError:true Tool-Result (MCP-Spec-Abweichung). Pro Message wird unbegrenzt Thread gestartet (OOM-Risiko). Thread-Pool einführen, Tool-Fehler als isError-Result formatieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F8.2/F8.4

**Rationale:** Migration from REQUIREMENTS.md (REQ-086)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-086.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-144

---

### REQ-L1-182: REQ-036 Beschreibung redaktionell anpassen

docs/REQUIREMENTS.md REQ-036-Eintrag beschreibt "SHA-256-Hash" — tatsächliche Implementierung nutzt Django-Signing (reversible Verschlüsselung für Downstream-Kompatibilität). Beschreibungstext auf "reversible Verschlüsselung (Django-Signing)" korrigieren. Kein Code-Change.

**Rationale:** Migration from REQUIREMENTS.md (REQ-087)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-087.
**Test Status:** Missing
**Remarks:** Dokumentation

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-145

---

### REQ-L1-183: Service-Layer O(N) in list()-Aufrufen

Service-Methoden in backend/application/** geben teils list(queryset) zurück statt QuerySets zu delegieren — O(N)-Materialisierung auch außerhalb der View-Paginierung. Alle list(qs)-Aufrufe in Service-Methoden durch QuerySet-Delegation ersetzen. Follow-up aus REQ-034-Partial-Fix.

**Rationale:** Migration from REQUIREMENTS.md (REQ-088)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-088.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-146

---

### REQ-L1-184: check_consistency-Verdrahtung und validate-MCP-Caller

Nach REQ-046 (Artefakt-Inhalt in Prompts): kein Service-Aufrufer ruft check_consistency auf (Funktion nie erreichbar); requirement.validate MCP-Tool übergibt noch id-only. Service-Aufruf für check_consistency verdrahten, MCP-Tool-Caller auf inhaltstragende Signatur umstellen.

**Rationale:** Migration from REQUIREMENTS.md (REQ-089)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-089.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-147

---

### REQ-L1-185: 9 vorbestehende E2E-Test-Failures in test_e2e_mcp.py

test_e2e_mcp.py hat 9 Failures die nicht durch P1-Wave verursacht wurden. Root-Cause analysieren, Failures beheben oder Tests als expected-failure markieren mit Issue-Referenz.

**Rationale:** Migration from REQUIREMENTS.md (REQ-090)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-090.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-148

---

### REQ-L1-186: Listen-Virtualisierung für große Artefakt-Listen

RequirementList.tsx:259 und NeedList.tsx:270 rendern vollständige Listen ohne Virtualisierung — kombiniert mit O(N)-Backend-Paginierung (REQ-034) skaliert das doppelt schlecht. react-window oder react-virtual einführen für lange Listen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-14

**Rationale:** Migration from REQUIREMENTS.md (REQ-091)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-091.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-149

---

### REQ-L1-187: Memoization in Hot-Paths ergänzen

React.memo/useMemo nur in 15 von 117 Komponenten-Dateien; in den größten Render-Bäumen (BaselinesView, IcdView) fehlt sie weitgehend. Gezielte Memoization in identifizierten Hot-Paths ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-15

**Rationale:** Migration from REQUIREMENTS.md (REQ-092)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-092.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-150

---

### REQ-L1-188: Typ-Löcher in API-Client schließen

frontend/src/api/client.ts:47,93 enthält `undefined as unknown as T` bei 204-Responses und `as Record<string, string>`-Header-Cast — Null-Fehler werden zur Laufzeit verschoben. Typsichere Alternativen einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-16

**Rationale:** Migration from REQUIREMENTS.md (REQ-093)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-093.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-151

---

### REQ-L1-189: ESLint-Versions-Inkonsistenz beheben

frontend/eslint.config.js behauptet "ESLint 9 flat config", frontend/package.json pinnt eslint ^8.57.0, globals ^17.7.0 setzt neuere Node-Umgebung voraus — widersprüchliche Versionsangaben bereinigen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-17

**Rationale:** Migration from REQUIREMENTS.md (REQ-094)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-094.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-152

---

### REQ-L1-190: Prettier einführen

Keinerlei Formatter-Konfiguration im Frontend-Projekt. .prettierrc ergänzen, npm-Script für format/format:check, CI-Hook. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-18

**Rationale:** Migration from REQUIREMENTS.md (REQ-095)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-095.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-153

---

### REQ-L1-191: Test-Layout vereinheitlichen

Frontend-Tests liegen teils co-located (components/**/**.test.tsx), teils zentral (src/test/), teils als api/*.test.ts — einheitliche Konvention festlegen und dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-19

**Rationale:** Migration from REQUIREMENTS.md (REQ-096)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-096.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-154

---

### REQ-L1-192: fabric-Mock Contract-Test ergänzen

fabric-Mock-Alias nur in Vitest-Config (vite.config.ts:34-38) — Prod-Typprüfung und Test-Realität divergieren. Contract-Test gegen echtes fabric-Interface ergänzen um sicherzustellen dass der Mock die echte API abbildet. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-20

**Rationale:** Migration from REQUIREMENTS.md (REQ-097)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-097.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-155

---

### REQ-L1-193: Node-Versionsdrift beheben

frontend/Dockerfile baut mit node:22, CI-Workflow (.github/workflows/playwright.yml:86) testet mit node 20 — gleiche Version in Docker und CI verwenden. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-17

**Rationale:** Migration from REQUIREMENTS.md (REQ-098)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-098.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-156

---

### REQ-L1-194: Docker-Image-Versionen härten

frontend/Dockerfile:4,31 nutzt nginx:alpine und node:22-slim ohne Digest-/Minor-Pin — Image-Versionen mit vollständigem Tag oder Digest pinnen um reproduzierbare Builds zu gewährleisten. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-18

**Rationale:** Migration from REQUIREMENTS.md (REQ-099)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-099.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-157

---

### REQ-L1-195: E2E-CI gegen Prod-Build ausführen

.github/workflows/playwright.yml:94-98 führt E2E-Tests gegen Vite-Dev-Server aus — Prod-Regressionen (wie der defekte Prod-Build) bleiben unsichtbar. E2E-Pipeline auf Docker-Prod-Build umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-19

**Rationale:** Migration from REQUIREMENTS.md (REQ-100)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-100.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-158

---

### REQ-L1-196: Dependabot für Python- und npm-Dependencies aktivieren

Kein automatisches Dependency-Update konfiguriert. .github/dependabot.yml mit Konfiguration für pip (backend) und npm (frontend) anlegen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-20

**Rationale:** Migration from REQUIREMENTS.md (REQ-101)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-101.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-159

---

### REQ-L1-197: Backup-Strategie für postgres_data-Volume

postgres_data-Volume (docker-compose.yml:159-160) hat keine Backup-Strategie. pg_dump-Script oder Sidecar-Service mit Cron-Scheduling einführen und in docker-compose.backup.yml dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-21

**Rationale:** Migration from REQUIREMENTS.md (REQ-102)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-102.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-160

---

### REQ-L1-198: Log-Rotation-Limit für Docker-Container

docker-compose.yml:32,53,70 setzt restart: unless-stopped ohne Log-Rotation — Log-Volumes wachsen unbegrenzt. logging.options.max-size und max-file für alle Services ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-22

**Rationale:** Migration from REQUIREMENTS.md (REQ-103)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-103.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-161

---

### REQ-L1-199: Read-Model für Traceability-Matrix

backend/application/ berechnet die Traceability-Matrix durch Live-Graph-Traversierung — bei Extended-Rigor-Projekten mit tausenden Trace-Links skaliert das schlecht. Materialisierte Sicht oder Cache-Layer einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-22

**Rationale:** Migration from REQUIREMENTS.md (REQ-104)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-104.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-162

---

### REQ-L1-200: Response-Caching für LLM-Derivation-Anfragen

backend/application/ai_derivation_service.py führt identische LLM-Anfragen wiederholt aus ohne Caching. Prompt-Hash-basiertes Caching (Django-Cache-Backend) für Derivation-Ergebnisse einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md F5.1

**Rationale:** Migration from REQUIREMENTS.md (REQ-105)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-105.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-163

---

### REQ-L1-201: Token-Usage pro Tenant aggregieren und limitieren

backend/llm_adapter/ loggt Token-Usage, speichert sie aber nicht auswertbar. Token-Verbrauch pro Tenant in der DB aggregieren, Query-API bereitstellen und konfigurierbares Limit mit 429-Response einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md F5.3

**Rationale:** Migration from REQUIREMENTS.md (REQ-106)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-106.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-164

---

### REQ-L1-202: SSE Event-IDs und Last-Event-ID-Replay

backend/mcp_server/sse_pubsub.py liefert SSE-Events ohne Event-ID — bei Verbindungsabbruch gehen Events verloren (at-most-once). Event-IDs ergänzen und Last-Event-ID-Header für Replay-Unterstützung implementieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F8.3

**Rationale:** Migration from REQUIREMENTS.md (REQ-107)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-107.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-165

---

### REQ-L1-203: MCP-Protokoll-Kleinigkeiten beheben

backend/mcp_server/protocol_handler.py und tool_registry.py: (1) Response auf notifications/initialized obwohl Notifications keine Antwort erwarten, (2) hartkodierte protocolVersion, (3) unbounded PresetCache ohne Größenlimit, (4) list_tools ignoriert RBAC (Viewer sieht Schreib-Tools). Referenz: DEEP_SYSTEM_ANALYSIS.md F8.5

**Rationale:** Migration from REQUIREMENTS.md (REQ-108)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-108.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-166

---

### REQ-L1-204: pgvector Python-Dependency ergänzen

Celery-Container crasht beim Start wegen fehlendem pgvector-Modul (ImportError). pgvector in backend/requirements.txt ergänzen und Dockerfile-Build sicherstellen. Neues Finding aus P2-Implementierungsbericht.

**Rationale:** Migration from REQUIREMENTS.md (REQ-109)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-109.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-167

---

### REQ-L1-205: python-json-logger Dependency im Container sicherstellen

python-json-logger fehlt im laufenden Container-Image (aus REQ-063, JSON-Logging-Feature). Dependency in backend/requirements.txt ergänzen und im Backend-Dockerfile sicherstellen dass der Package-Build korrekt erfolgt. Neues Finding aus P2-Implementierungsbericht.

**Rationale:** Migration from REQUIREMENTS.md (REQ-110)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-110.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-168

---

### REQ-L1-206: Symmetrische Rollen-Auflösung für Bearer-Tokens

Bearer-Token-Pfad verwendet JWT-Claims als einzige Rollen-Quelle. Wenn Rollen im JWT leer sind (neuer User / Rolle nach Login zugewiesen), erhalten Users 403 auf Schreib-Endpoints. Fix: DB-Fallback identisch dem API_KEY-Pfad wenn `claims.roles` leer ist (`auth_tenancy/rest.py`).

**Rationale:** Migration from REQUIREMENTS.md (REQ-126)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-126.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-169

---

### REQ-L1-207: Decomposition backend/rest_api/views.py (P1 Architektur)

views.py: 4524 Zeilen, 30+ ViewSets + 100+ Action-Methoden in einer Datei. Decompose in Domain-Submodule (views_artifacts.py, views_requirements.py, views_architecture.py, views_test_management.py etc.). Jedes Submodul enthält verwandte ViewSet-Gruppen (ein Domain pro Datei), reduziert Komplexität und Änderungsradius bei Fehlerbehebung. Blocking für skalable Architektur. Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Migration from REQUIREMENTS.md (REQ-111)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-111.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-170

---

### REQ-L1-208: Decomposition backend/rest_api/serializers.py (P1 Architektur)

serializers.py: 1110 Zeilen, 31 Serializer-Klassen in einer Datei. Analog views.py-Decomposition: serializers_artifacts.py, serializers_requirements.py etc. Ein Serializer-Set pro Domain. Bessere Übersicht und reduzierte Merge-Konflikte. Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Migration from REQUIREMENTS.md (REQ-112)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-112.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-171

---

### REQ-L1-209: Decomposition CanvasEditor.tsx (P1 Frontend-Architektur)

CanvasEditor.tsx: 1364 Zeilen, monolithische Canvas+Toolbar+Fabric.js-Lifecycle, 28 Hooks entangled (ToolbarState, GeometryState, SelectionState, etc.). Extract: ToolbarPresenter-Komponente, useCanvasState Hook (centralisiertes Canvas-State-Management), pure Geometry-Utility-Funktionen (Transformer-Kalkulationen, Path-Simplifizierung). Reduziert Complexity auf <500 Zeilen Pro-Subkomponente. Blocking für Bug-Fixes in Canvas. Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Migration from REQUIREMENTS.md (REQ-113)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-113.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-172

---

### REQ-L1-210: Decomposition SidebarNavigation.tsx (P1 Frontend-Architektur)

SidebarNavigation.tsx: 821 Zeilen, Route-Registrierung + Preset-Gating, single Point of Failure (alle Route-Änderungen erfordern Edit dieser Datei). Extract: useRouteRegistry Hook (Zentrale Route-Deklaration + Visibility-Logic), usePresetVisibility Hook (Preset-basiertes Gating), RoutePresetPresenter Komponente. Ermöglicht dezentralisierte Route-Registrierung (Feature-Modules können eigene Routes anmelden). Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Migration from REQUIREMENTS.md (REQ-114)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-114.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-173

---

### REQ-L1-211: Hardcoded Default-Secrets in settings.py (P2 Security)

backend/reqflow/settings.py Zeile 32 (SECRET_KEY = "CHANGE-ME-IN-PRODUCTION") und Zeile 267 (AUTH_JWT_SECRET = "CHANGE-ME-IN-PRODUCTION") sind Production-Deployment-Blocker. Fix: Secrets NICHT hardcoden, stattdessen zwingend aus ENV-Variablen laden. .env.example bereitstellen mit Secrets-Checklist und Kommentaren zu generierten Werten (Django-generierten SECRET_KEY, JWT-Secret-Generierung). Deployment-Docs: Fail-Fast-Verhalten wenn Secrets nicht gesetzt. Status: Backlog.

**Rationale:** Migration from REQUIREMENTS.md (REQ-115)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-115.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-174

---

### REQ-L1-212: API-Contract-Drift TypeScript vs DRF (P2 API)

frontend/src/types/index.ts vs backend/rest_api/serializers.py sind nur manuell synchronisiert. Empfehlung: OpenAPI Codegen-Integration einführen (drf-spectacular im Backend → OpenAPI-Schema-Export, TypeScript-Codegen in Frontend). Alternativ: TypeScript-Definitionenfile als Single Source of Truth mit Codegen in beide Richtungen (Backend-Validator, Frontend-Types). Reduziert Typ-Drift-Bugs um ~90%. Status: Backlog.

**Rationale:** Migration from REQUIREMENTS.md (REQ-116)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-116.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-175

---

### REQ-L1-213: N+1 Queries in MCP-Server (P2 Performance)

backend/mcp_server/tools/requirements.py:58-71 (_requirement_to_dict) lädt Requirement→Artifact→Workspace ohne select_related/prefetch_related — pro Item min. 3 zusätzliche DB-Queries. Fix: n-Queries vor der Serialisierung mit select_related('artifact__workspace') laden, oder auf GraphQL-artige Feld-Selektion migrieren. Status: Backlog.

**Rationale:** Migration from REQUIREMENTS.md (REQ-117)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-117.
**Test Status:** Missing
**Remarks:** Performance

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-176

---

### REQ-L1-214: Multi-Worker Cache-Invalidierung unvollständig (P2 Non-Functional)

REQ-038 referenziert diesen Punkt: aktuell nur Single-Worker-Deployment sicher. backend/reqflow/settings.py:333-340 hat Cache-Konfiguration aber KEINE Invalidierungsstrategie nach Writes. Mehrere Worker sehen alte Werte. Fix: Signal-basierte Invalidierung (post_save/post_delete auf Domain-Models) oder TTL-Strategie für alle Cache-Keys. Test: ≥2 Worker, Write in Worker-1, Read in Worker-2 muss neue Wert sehen. Status: Backlog.

**Rationale:** Migration from REQUIREMENTS.md (REQ-118)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-118.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-177

---

### REQ-L1-215: React-Query-Migration zu 92% fertig (P2 Functional)

REQ-049 (React-Query-Migration) zu 92% implementiert. Offene Aufgaben: 2 verbleibende Hooks (useTestCaseData.ts und useDashboardData.ts) noch mit useState+useEffect+fetch statt TanStack Query implementiert. Migriere diese 2 Hooks zu @tanstack/react-query QueryClient, align Error/Loading-States mit bestehenden Patterns (useAdrData, useRiskData, etc.). Status: Backlog (sollte vor RC-Release done sein).

**Rationale:** Migration from REQUIREMENTS.md (REQ-119)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-119.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-178

---

### REQ-L1-216: Container/Presenter zu 90% fertig (P2 Functional)

REQ-050 (Monster-Komponenten-Zerlegung) zu 90% implementiert. Offenes TODO in TestRunDetailEditor.tsx:12-13: testRunsApi.listResults() ruft noch direktes API auf statt über useTestRunsData Hook zu gehen. Extract useTestRunsData Hook (oder nutze bestehenden entsprechenden Hook), migiere TestRunDetailEditor zu Container/Presenter-Pattern (Daten-Container in Container-Komponente, UI-Rendering in Presenter). Status: Backlog (sollte vor RC-Release done sein).

**Rationale:** Migration from REQUIREMENTS.md (REQ-120)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-120.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-179

---

### REQ-L1-217: DEFAULT_TENANT_ID hardcoded (P3 Non-Functional)

backend/reqflow/settings.py:358 — DEFAULT_TENANT_ID ist hardcoded zu '1'. Für echte Multi-Tenancy vorsehen: ENV-Var DJANGO_DEFAULT_TENANT_ID mit Fallback oder ganz aus Code entfernen (Multi-Tenancy sollte request-aware sein, nicht global). Status: Backlog (P3 Optimierung).

**Rationale:** Migration from REQUIREMENTS.md (REQ-121)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-121.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-180

---

### REQ-L1-218: Frontend-Monolithen-Kandidaten (P3 Non-Functional)

DecompositionTree.tsx (835 Zeilen) und TraceabilityView.tsx (802 Zeilen) sind nächste Zerlegungs-Kandidaten nach REQ-050. Baum-Algorithmen/Such-Logik entangled mit UI-Rendering. Extract: Utility-Module mit Pure-Funktionen (Baum-Traverse, Filter-Logik, Path-Suche), useTreeState Hook für State-Management, TreePresenter Komponente. Status: Backlog (P3).

**Rationale:** Migration from REQUIREMENTS.md (REQ-122)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-122.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-181

---

### REQ-L1-219: TypeScript-Typing: any statt unknown (P3 Non-Functional)

CanvasEditor.tsx:110-113 (type AnyObj = Record<string, any>), AdrForm.tsx:35 (handleChange value: any) und weitere Stellen nutzen `any` statt `unknown` + Type-Guards. any schwächt TypeScript-Sicherheit, `unknown` erzwingt Type-Checks. Ersetze `any` durch `unknown` + Discriminator-Patterns oder konkrete Typen. Status: Backlog (P3).

**Rationale:** Migration from REQUIREMENTS.md (REQ-123)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-123.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-182

---

### REQ-L1-220: Accessibility: Error-State A11y (P3 Accessibility)

frontend/src/components/.../ArtifactDiff.tsx:441-450 — Error-State-Div fehlt role="alert" und aria-live="assertive". Liveregion-Markup ergänzen um sicherzustellen dass Screen-Reader Fehler aussprechen. Weitere Stellen mit Error/Toast-Komponenten auditieren. Status: Backlog (P3).

**Rationale:** Migration from REQUIREMENTS.md (REQ-124)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-124.
**Test Status:** Missing
**Remarks:** Accessibility

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-183

---

### REQ-L1-221: Unused/Overlapping Component (P3 Functional)

AiPromptsSection.tsx überlappt konzeptuell mit PromptTemplateSection.tsx (ähnliche Funktionalität, unterschiedliche Naming). Entscheidung erforderlich: Komponente löschen oder zusammenführen + Naming vereinheitlichen (UX-Entscheidung mit Team). Status: Backlog (Entscheidung nötig vor Cleanup).

**Rationale:** Migration from REQUIREMENTS.md (REQ-125)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-125.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-184

---

### REQ-L1-222: MCP API-Key Rollen-Propagation

MCP API-Key-Authentifizierung muss Workspace-Rollen des Users laden und in den MCP-Dispatch-Kontext propagieren. Ohne workspace_id in Tool-Call-Parametern bleibt active_roles leer und blockiert alle Schreib-Operationen für API-Key-authentifizierte User. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-127)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-127.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-185

---

### REQ-L1-223: URL-Routing StakeholderNeedViewSet — derive-requirements

GET /api/v1/needs/derive-requirements/ darf nicht 500 zurückgeben. Der DRF-Router interpretiert "derive-requirements" als UUID-pk. Fix: lookup_value_regex in StakeholderNeedViewSet auf UUID-Muster einschränken, damit Custom Actions nicht als pk aufgelöst werden. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-128)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-128.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-186

---

### REQ-L1-224: MCP tools/list — doppelte Einträge entfernen

MCP tools/list-Response muss eindeutige Tool-Einträge zurückgeben. Aktuell erscheinen 7 Tools doppelt, verursacht durch shared object references und mehrere CrossCuttingToolGroup-Instanzen. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-129)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-129.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-187

---

### REQ-L1-225: MCP Typed inputSchemas für alle Tool-Gruppen

Alle MCP-Tool-Gruppen müssen typisierte inputSchema-Parameter exponieren statt generischem {"kwargs": {"type": "object"}}. Aktuell haben nur requirement.*, prompt_template.get und ai_derivation.* typisierte Schemas — betrifft 15+ Tool-Gruppen. Priorität: Backlog (außerhalb des aktuellen Sprints — zu groß).

**Rationale:** Migration from REQUIREMENTS.md (REQ-130)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-130.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-188

---

### REQ-L1-226: MCP Capability Declaration — nur implementierte Transports

MCP Capability-Declaration darf nur implementierte Transports ausweisen. "sse" aus der Transports-Liste entfernen, da SSE-Transport nicht implementiert ist. Die aktuelle Deklaration führt MCP-Clients in die Irre. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-131)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-131.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-189

---

### REQ-L1-227: Ollama base_url Validierungsfehler

Wenn LLM-Provider "ollama" ist und base_url leer ist, muss das Backend einen klaren Validierungsfehler zurückgeben statt still auf localhost:11434 zurückzufallen. Zusätzlich OLLAMA_BASE_URL in der Dokumentation ergänzen. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-132)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-132.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-190

---

### REQ-L1-228: Workspace language-Feld in Datenbank persistieren

Die Workspace-Spracheinstellung muss in der Datenbank gespeichert werden. Das Workspace-Model hat keine language-Spalte; der Serializer gibt immer den Default "en" zurück. language-Feld zum Workspace-Model hinzufügen inkl. Migration. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-133)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-133.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-191

---

### REQ-L1-229: API-Key Retrieve-Endpoint

GET /api/v1/api-keys/{id}/ muss 200 mit den Key-Details zurückgeben. Aktuell sind nur list (GET /api-keys/) und create (POST) implementiert. retrieve-Action zu ApiKeyViewSet hinzufügen. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-134)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-134.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-192

---

### REQ-L1-230: change_reason Validierungsfehler mit Kontext

change_reason-Validierungsfehler muss Workspace-Name und Preset in der Fehlermeldung enthalten. Aktuelle Meldung "change_reason required" gibt keinen Kontext darüber, welcher Workspace die Angabe erfordert oder warum. Priorität: Could.

**Rationale:** Migration from REQUIREMENTS.md (REQ-135)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-135.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-193

---

### REQ-L1-231: Attribut-Visibility-Config leere Antwort fehlerfrei behandeln

Das Frontend muss eine leere []-Antwort von /api/v1/attribute-visibility-configs/ ohne console.error verarbeiten. Die aktuelle Implementierung ruft console.error bei leerem Array auf; AdminDialog zeigt bei jedem API-Fehler eine nutzerseitige Fehlermeldung. Priorität: Could.

**Rationale:** Migration from REQUIREMENTS.md (REQ-136)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-136.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-194

---

### REQ-L1-232: Preferences GET-Endpoint muss 200 mit leeren Defaults zurückgeben

GET /api/v1/users/me/preferences/?workspace_id=<uuid> MUSS HTTP 200 mit einer neu angelegten (leeren) Preference-Row zurückgeben, wenn für das gegebene User/Workspace-Paar noch kein Eintrag existiert — statt HTTP 404. Entspricht der get_or_create-Semantik des PATCH-Endpoints und verhindert console.error-Fluten im Frontend (WorkspaceContext). Fix: GET-Handler in UserPreferenceView auf PreferenceService.get_or_create_preference() umstellen statt get_preference(). Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-137)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-137.
**Test Status:** Missing
**Remarks:** API / Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-195

---

### REQ-L1-233: CSRF Trusted Origins für Browser-SPA konfiguriert

Das Backend MUSS in CSRF_TRUSTED_ORIGINS alle erlaubten SPA-Origins (mindestens http://localhost:5173 für den Vite-Dev-Server und die produktive Frontend-URL) eintragen, sodass state-ändernde REST-Anfragen (POST, PATCH, PUT, DELETE) der Browser-SPA nicht mit HTTP 403 abgelehnt werden. Hintergrund: Der Cookie-basierte Session-Auth-Pfad erzwingt die Django-CSRF-Origin-Prüfung; fehlt der Origin in CSRF_TRUSTED_ORIGINS, scheitern alle Schreibzugriffe der SPA. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-138)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-138.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-196

---

### REQ-L1-234: Automatisierter CSRF-Regressionstest (Cross-Origin Enforcement)

Es MUSS ein automatisierter Test existieren, der das Cross-Origin-CSRF-Enforcement des Django-Backends prüft. Der Test verwendet `django.test.Client` mit `enforce_csrf_checks=True` und sendet POST/PATCH/DELETE-Anfragen sowohl mit korrektem als auch mit fehlendem/falschem Origin-Header gegen mindestens einen schreibenden REST-Endpoint. Ein korrekter Origin MUSS HTTP 2xx zurückgeben; ein fehlender oder nicht-erlaubter Origin MUSS HTTP 403 zurückgeben. Ziel: Regressionen wie REQ-138 (fehlende CSRF_TRUSTED_ORIGINS) werden automatisch erkannt. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-139)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-139.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-197

---

### REQ-L1-235: npm install ohne --legacy-peer-deps: fabric.js/jsdom-Kompatibilität

`npm install` im Frontend-Verzeichnis MUSS ohne `--legacy-peer-deps`-Flag erfolgreich durchlaufen. Die fabric.js-Abhängigkeit MUSS mit dem jsdom@^25-devDependency (oder einer kompatiblen jsdom-Version) peer-kompatibel sein. Existiert keine kompatibel veröffentlichte Version von fabric.js, MUSS die Inkompatibilität in der Codebase dokumentiert und mit technischer Begründung gerechtfertigt sein. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-140)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-140.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-198

---

### REQ-L1-236: TracePanel im ArtifactInspector an echte TraceLink-API anbinden

Das TracePanel im ArtifactInspector MUSS echte Trace-Links über `/api/v1/tracelinks/` laden statt des `mockFetchTraceLinks`-Stubs (liefert immer `[]`). Loading-, Error- und Empty-State MÜSSEN unterschieden werden; „keine Links" darf erst nach erfolgreichem Fetch angezeigt werden. `resolveArtifactRef` MUSS verdrahtet sein, sodass Link-Endpunkte mit Titel/UID angezeigt werden. Priorität: Must. (AP-07)

**Rationale:** Migration from REQUIREMENTS.md (REQ-141)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-141.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-199

---

### REQ-L1-237: Versions- und Diff-Endpoints für Diagramm & Glossar

Für Diagramme und Glossar-Einträge MÜSSEN `GET …/{pk}/versions/` und `GET …/{pk}/diff/?from_version=&to_version=` analog zu den Requirement-Endpoints existieren (Versionstabellen `DiagramVersion`/`GlossaryTermVersion` sind vorhanden). Die Frontend-Stubs in `api/glossary.ts`/`api/diagrams.ts` („Not Implemented") sowie die Mock-Fallbacks in VersionPanel/DiffPanel MÜSSEN durch echte Aufrufe ersetzt werden. Priorität: Should. (AP-08)

**Rationale:** Migration from REQUIREMENTS.md (REQ-142)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-142.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-200

---

### REQ-L1-238: Status-Modell konsolidieren: Workflow-Engine als Quelle der Wahrheit

Es DARF nur einen Schreibpfad für Statuswechsel geben: die Workflow-Engine (`workflow`-App). Das freie `status`-CharField auf Requirement/Need wird zum denormalisierten, read-only Spiegel, gesetzt ausschließlich durch Workflow-Transitions. Direkte Status-Writes via REST/MCP MÜSSEN abgelehnt oder ignoriert werden. Datenmigration mappt Bestandswerte auf gültige Workflow-States; Mapping wird als ADR dokumentiert. Priorität: Must. (AP-09)

**Rationale:** Migration from REQUIREMENTS.md (REQ-143)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-143.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-201

---

### REQ-L1-239: Review-/Approval-UI auf Basis der Workflow-Engine

Es MUSS eine Review-Ansicht (`/reviews`) geben: Liste aller Items im Zustand `in_review`, Detailansicht mit Diff zur letzten approved-Version, Aktionen Approve/Reject. Approve MUSS das vorhandene Signature-Gate nutzen (Credential-Dialog Passwort/TOTP, HMAC-Seal, approver-Rolle). Workflow-Historie inkl. Seal-Status MUSS am Item sichtbar sein. Ein Playwright-E2E-Szenario deckt draft→in_review→approved ab. Priorität: Must. (AP-10)

**Rationale:** Migration from REQUIREMENTS.md (REQ-144)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-144.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-202

---

### REQ-L1-240: PDF-Export-Stubs fertigstellen (VCRM-PDF, Export-PDF)

Der VCRM-Report-Generator und der Export-Service DÜRFEN für PDF kein `NotImplemented` mehr werfen. VCRM-PDF (Matrix-Tabelle) und Export-PDF werden mit reportlab vervollständigt (Vorbild: `traceability/pdf_report_generator.py`). Tests prüfen, dass ein nicht-leeres PDF mit Stichproben-Inhalten erzeugt wird. Priorität: Should. (AP-11)

**Rationale:** Migration from REQUIREMENTS.md (REQ-145)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-145.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-203

---

### REQ-L1-241: ReqIF-Export

Requirements, Stakeholder Needs und TraceLinks eines Workspace MÜSSEN als ReqIF 1.2 exportierbar sein (`GET /api/v1/workspaces/{pk}/export/reqif/`): Artefakte als SPEC-OBJECT mit typespezifischen Attributen, Hierarchie als SPECIFICATION/SPEC-HIERARCHY, TraceLinks als SPEC-RELATION, stabile IDENTIFIER aus Artifact-UUID (Re-Export ändert IDs nicht). Die exportierte Datei MUSS gegen das ReqIF-Schema validieren und von einem Referenz-Parser lesbar sein. Priorität: Must. (AP-12)

**Rationale:** Migration from REQUIREMENTS.md (REQ-146)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-146.
**Test Status:** Missing
**Remarks:** Integration

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-204

---

### REQ-L1-242: ReqIF-Import

ReqIF-Dateien MÜSSEN importierbar sein (`POST /api/v1/workspaces/{pk}/import/reqif/`): atomar, Upsert per IDENTIFIER-Matching gegen vorhandene UIDs (Re-Import aktualisiert statt dupliziert), unbekannte Attribute → custom_fields, Dry-Run-Modus (`?dry_run=true`) liefert Bericht ohne Persistenz. Roundtrip Export→Import MUSS idempotent sein. Priorität: Must. (AP-13)

**Rationale:** Migration from REQUIREMENTS.md (REQ-147)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-147.
**Test Status:** Missing
**Remarks:** Integration

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-205

---

### REQ-L1-243: Issue-Status Normalisierung (Case-Insensitive)

IssueSerializer MUSS case-insensitive Status-Eingaben akzeptieren und normalisieren (z.B. 'open', 'IN PROGRESS', 'wONtFiX' → Title-Case). Implementierung via NormalizedChoiceField mit .title()-Transformation. Tests decken lowercase, uppercase und mixed-case Inputs ab. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-148)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-148.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-206

---

### REQ-L1-244: Workspace-Kontext: neutraler Placeholder während Load

WorkspaceContext.DEFAULT_WORKSPACE.name MUSS während der initialen Workspace-Loading-Phase auf leeren String gesetzt sein statt auf 'Default Workspace', um Verwirrung zu vermeiden. Nutzer sehen keinen irreführenden Text wenn der echte Workspace 'Demo Workspace' oder anderes heißt. Loading-State ist already vorhanden; UI-Konsumenten prüfen isLoadingWorkspace vor Rendering. Priorität: Could.

**Rationale:** Migration from REQUIREMENTS.md (REQ-149)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-149.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-207

---

### REQ-L1-245: ADR-Supersedes-Link bei Statusübergang

Wenn ein ADR in den Status 'Superseded' übergeht, MUSS AdrService.transition_status() einen optionalen Parameter `superseded_by_id` (UUID des Nachfolger-ADRs) akzeptieren und bei Angabe einen TraceLink vom neuen (Nachfolger-)ADR zum alten (abgelösten) ADR anlegen, damit der TraceLink-Graph die Ablösung dokumentiert. 'supersedes' ist kein Mitglied von VALID_LINK_TYPES; 'decides' (bereits für ADR-Entscheidungs-Links verwendet, REQ-L2-TE-020) ist die semantisch nächstliegende Alternative. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-150)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-150.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-208

---

### REQ-L1-246: Extended-Preset: implemented/verified-States (V-Modell rechte Seite)

Das Extended-Workflow-Preset (workflow/definition_store.py PRESET_SCHEMAS) endet aktuell bei approved/deprecated und kann die rechte Seite des V-Modells (Implementierung, Verifikation) nicht abbilden. Ergänzung um States `implemented` (nach `approved`) und `verified` (nach `implemented`) mit Transitions approved→implemented und implemented→verified. Rollenmapping nutzt die vorhandenen RBAC-Rollen (admin/editor/viewer/approver aus auth_tenancy/models.py) — "editor" für die Implementierungs-Transition, "approver" für die Verifikations-Transition, da "developer"/"reviewer"/"verifier" keine im System definierten Rollen sind. Bestandsanforderungen in approved/deprecated bleiben gültig (Backward-Compatibility). Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-151)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-151.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-209

---

### REQ-L1-247: Hierarchie-Konsolidierung: Artifact.parent zugunsten von TraceLinks deprecaten

Artifact.parent (Self-FK, persistence/models.py) und 'derives-from'-TraceLinks bilden zwei parallele Hierarchie-Mechanismen. Domain-Services (RequirementService, StakeholderNeedService, AdrService, ...) befüllen Artifact.parent nicht und nutzen ausschließlich TraceLinks; die generische ArtifactService (COMP-AS-001) sowie einzelne Baseline-/ReqIF-/Workspace-Duplizierungs-Codepfade lesen/schreiben das Feld weiterhin. Das Feld wird mit Deprecation-Kommentar versehen (single source of truth: 'derives-from'-TraceLink), ohne Migration/Verhaltensänderung; betroffene Lesestellen erhalten TODO-Kommentare zur schrittweisen Migration. Priorität: Could.

**Rationale:** Migration from REQUIREMENTS.md (REQ-152)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-152.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-210

---

### REQ-L1-248: Requirement-Hierarchie-Level (L0-L4) als explizites Feld

Requirement besitzt kein `level`-Feld — die V-Modell-Hierarchie (L0 System, L1 Subsystem, L2 Component, L3 Part, L4 Material) existiert bisher nur als Namenskonvention. Ein nullable `level`-Feld (PositiveSmallIntegerField, choices 0-4) MUSS die Ebene explizit und abfragbar machen. Additiv/backward-compatible: Bestandszeilen bleiben `NULL` (kein Backfill; die Ebene wird bewusst zugewiesen). Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-153)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-153.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-211

---

### REQ-L1-249: TestCase-Testtyp als First-Class-Feld + Verification-Method Demonstration

TestCase kodiert den Testtyp bisher als String-Präfix im `artifact_type` (z.B. "TestCase:System"). Ein nullable `test_type`-Feld (CharField, choices system/integration/unit/inspection/analysis/demonstration) MUSS den Typ als eigenständiges Feld führen; eine Datenmigration backfilled aus dem Legacy-Präfix. Zusätzlich wird `Demonstration` zu VerificationMethod ergänzt (V-Modell-Vollständigkeit). Additiv/backward-compatible. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-154)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-154.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-212

---

### REQ-L1-250: Functional/Physical Architecture Separation

The artifact model must distinguish between functional architecture elements (functions, logical blocks, behavioral decomposition) and physical architecture elements (components, hardware items, physical topology). Currently both are stored as generic Artifact records without semantic differentiation. Future implementation should: (a) add an `architecture_domain` field (functional/physical) to Architecture-type Artifacts, (b) add a dedicated `allocates` TraceLink type from functional to physical elements, (c) update MBSE views to render functional and physical hierarchies separately. Priority: Follow-up / Post-v1.

**Rationale:** Migration from REQUIREMENTS.md (REQ-155)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-155.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-213

---

### REQ-L1-251: TestRun Baseline Support

TestRun/TestRunResult entities must be includeable in Baseline snapshots to enable reproducible verification evidence at each project milestone. The `ScopeResolver` MUST include `pl_test_run` and `pl_test_run_result` rows (by `workspace_id`/`tenant_id`) when building project- and global-scoped baselines. Each entity is stored as a `BaselineDeltaIndexEntry` with `entity_type="test_run"` or `entity_type="test_run_result"`. Full state (name, status, timestamps, ci_job_id, results) is captured via `state_capture.py`. No schema migration required — `BaselineDeltaIndexEntry.entity_type` is a free-form `CharField`. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-156)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-156.
**Test Status:** Missing
**Remarks:** Test

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-214

---

### REQ-L1-252: Change Request Management — CCB Approval Workflow

Users must be able to create, submit, review, approve/reject, and implement Change Requests (CR) through a formal CCB (Configuration Control Board) approval workflow powered by the existing WorkflowEngine. The CR lifecycle MUSS follow the states: draft → submitted → under_review → approved

**Rationale:** Migration from REQUIREMENTS.md (REQ-157)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-157.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-215

---

### REQ-L1-253: Bug: Build-Version zeigt "unknown"

`version.py` behandelt den Default-String (z.B. `"unknown"`) als validen Git-SHA, wodurch der Git-Fallback-Pfad nie erreicht wird und die Build-Version in der UI dauerhaft als "unknown" angezeigt wird. `version.py` MUSS den Default-String von einem echten Git-SHA unterscheiden: Ist kein valider SHA verfügbar (Wert leer, gleich `"unknown"` oder ein bekannter Placeholder), MUSS der Git-Fallback-Pfad ausgeführt werden. Akzeptanzkriterium: Ein Prod-Build zeigt in der UI eine echte Commit-SHA oder einen definierten Fallback-String (z.B. `"dev"`) statt `"unknown"`. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-158)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-158.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-216

---

### REQ-L1-254: Bug: AuthContext-Attributfehler in StakeholderNeedService

`stakeholder_need_service.py` Zeile 207 greift via `ctx.user` auf ein nicht vorhandenes Attribut des `AuthContext` zu — `AuthContext` exponiert `user_id`, nicht `user`. Der Aufruf wirft `AttributeError` und blockiert alle StakeholderNeed-Operationen, die diesen Pfad durchlaufen. Die betroffene Stelle MUSS `ctx.user_id` statt `ctx.user` verwenden. Akzeptanzkriterium: StakeholderNeed-Operationen (Create, Update, Derive) schlagen nicht mehr mit `AttributeError: 'AuthContext' object has no attribute 'user'` fehl. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-159)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-159.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-217

---

### REQ-L1-255: Bug: Artefakt-Formulare umgehen WorkflowFacade — leere Transitions-Liste

Alle Artefakt-Formulare außer `RequirementForm` (d.h. `AdrForm`, `TestCaseForm`, `NeedForm`, `RiskForm`, `IssueForm`, `ChangeRequestForm`) führen Status-Writes direkt per REST durch und umgehen die `WorkflowFacade`. Bei fehlendem `WorkflowItemState`-Eintrag liefert die Transitions-API eine leere Liste, Status-Änderungen über die UI sind vollständig blockiert. Alle betroffenen Formulare MÜSSEN Status-Transitions ausschließlich über `WorkflowFacade.transition_status()` auslösen. Ein fehlender `WorkflowItemState`-Eintrag MUSS serverseitig automatisch auf den definierten Initial-State initialisiert werden statt eine leere Transitions-Liste zurückzugeben. Akzeptanzkriterium: Status-Transitionen für alle sieben Artefakt-Typen sind in der UI ausführbar; ein Artefakt ohne `WorkflowItemState`-Eintrag erhält automatisch den Initial-State und zeigt erlaubte Transitionen. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-160)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-160.
**Test Status:** Missing
**Remarks:** Workflow

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-218

---

### REQ-L1-256: Redesign: Unified Workflow Status Editor (wiederverwendbare Komponente)

Eine wiederverwendbare React-Komponente `WorkflowStatusEditor` MUSS für alle Artefakt-Typen (Requirements, ADR, TestCase, StakeholderNeed, Risk, Issue, ChangeRequest) bereitgestellt werden. Die Komponente zeigt den aktuellen Workflow-Status und die erlaubten Transitionen über die `WorkflowFacade`-API an, löst Transition-Aktionen aus und behandelt Fehlerzustände (leere Transitions-Liste, fehlender State, Netzwerkfehler) einheitlich mit sichtbarem Feedback. Hardcoded Status-Select-Dropdowns in Artefakt-Formularen werden durch `WorkflowStatusEditor` ersetzt. Akzeptanzkriterium: Kein Artefakt-Formular enthält ein eigenständiges Status-Dropdown mehr; alle Status-Änderungen laufen über dieselbe Komponente und die `WorkflowFacade`-API. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-161)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-161.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-219

---

### REQ-L1-257: Bug: NeedForm fehlt change_reason-Feld für Extended-Preset

`NeedForm.tsx` besitzt keinen `change_reason`-State, kein Eingabefeld und keinen API-Payload-Eintrag für das Feld `change_reason`. Der Backend-Service `stakeholder_need_service.py` (Zeilen 177–180, 239–242) erzwingt `change_reason` als Pflichtfeld bei Update- und Delete-Operationen, wenn der Workspace das Extended-Rigor-Preset nutzt — die fehlende Feldübergabe führt zu HTTP-400-Fehlern ("change_reason is required by preset policy"). `NeedForm.tsx` MUSS ein `change_reason`-Textarea-Feld erhalten, das ausschließlich bei aktivem Extended-Preset sichtbar ist, bei Update- und Delete-Requests im API-Payload mitgesendet wird und analog zur bestehenden Implementierung in `RequirementForm.tsx` (Zeilen 86, 110–111, 435–451) und `ArchitectureForm.tsx` aufgebaut ist. Akzeptanzkriterium: Im Extended-Preset sind Update- und Delete-Operationen auf StakeholderNeeds ohne HTTP-400-Fehler ausführbar; im Minimal- und Standard-Preset wird das Feld nicht angezeigt. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-162)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-162.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-220

---

### REQ-L1-258: LLM-Fähigkeiten standardmäßig nicht aktiviert

Das Backend liest `LLM_CAPABILITIES` aus einer Umgebungsvariable (`backend/llm_adapter/router.py:110`). Fehlt die Variable oder ist sie leer, sind alle vier LLM-Fähigkeiten (`validate_artifact`, `decompose_requirement`, `check_consistency`, `derive_requirements`) deaktiviert — ohne Fehlermeldung. Die `.env`- und `.env.example`-Dateien enthalten diese Variable nicht. `LLM_CAPABILITIES=validate_artifact,decompose_requirement,check_consistency,derive_requirements` MUSS in `.env` und `.env.example` ergänzt und dokumentiert werden. Akzeptanzkriterium: Ein frisch ausgechecktes Projekt mit `docker-compose up` aktiviert alle vier LLM-Fähigkeiten, da die Variable in `.env.example` vorbelegt ist. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-163)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-163.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-221

---

### REQ-L1-259: Fehlende requests-Dependency im Backend

Die Python-Bibliothek `requests` wird im Backend (LLM-Adapter-Provider) verwendet, ist aber nicht in `backend/requirements.txt` deklariert — führt zu `ImportError` zur Laufzeit, wenn das Paket nicht zufällig transitiv installiert ist. `requests>=2.31.0` MUSS explizit in `backend/requirements.txt` ergänzt werden. Akzeptanzkriterium: `pip install -r backend/requirements.txt` in einer sauberen virtualenv-Umgebung endet ohne ImportError; LLM-Adapter-Provider sind instanziierbar. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-164)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-164.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-222

---

### REQ-L1-260: Universelle Workflow-Engine für alle primären Entitätstypen

Die `WorkflowEngine` (eingeführt mit REQ-160/161) deckt aktuell nur `Requirement` vollständig und `StakeholderNeed` teilweise ab. Alle primären Entitätstypen — `Requirement`, `StakeholderNeed`, `Adr` (Architecture Decision Record), `TestCase`, `Risk`, `Issue` — MÜSSEN einen einheitlichen Workflow-Status besitzen, der ausschließlich durch die `WorkflowEngine` verwaltet wird. Der `WorkflowStatusEditor` MUSS in allen zugehörigen Frontend-Formularen sichtbar und funktionsfähig sein. Kein Entitätstyp darf Status-Writes mehr direkt via REST durchführen. Akzeptanzkriterium: Status-Transitionen sind für alle sechs Entitätstypen über die `WorkflowFacade`-API auslösbar; kein Formular enthält ein eigenständiges Status-Dropdown. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-165)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-165.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-223

---

### REQ-L1-261: Entitätstyp-spezifisch konfigurierbare Workflow-Presets

Jeder Entitätstyp MUSS eine eigene, unabhängig konfigurierbare Workflow-Zustandsmaschine besitzen — kein einziges globales Preset für alle Typen. Standard-Presets MÜSSEN dem RM/SE-Standard-Lifecycle folgen: Draft → In Review → Approved → Released/Deprecated/Rejected. Die Preset-Konfiguration MUSS in der Datenbank (z.B. `WorkflowEngineDefinition`) gespeichert werden, nicht hartkodiert. Ein Konfigurationsinterface (UI oder Admin-Einstellungen) MUSS pro Entitätstyp vorhanden sein, über das Zustände und erlaubte Übergänge angepasst werden können. Akzeptanzkriterium: Für zwei Entitätstypen können unterschiedliche Zustandsmaschinen aktiv sein; Änderungen über das Konfigurationsinterface wirken ohne Deployment. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-166)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-166.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-224

---

### REQ-L1-262: Workflow-Approval/Release-Dialog-Integration für alle Entitätstypen

Workflow-Zustandsübergänge, die Genehmigungs- oder Freigabeschritte darstellen (z.B. → Approved, → Released), MÜSSEN mit den bestehenden `SignatureDialog`- und `ReviewsView`-Komponenten integriert werden. Die aktuelle Verdrahtung des Signature-Gate-Mechanismus gilt ausschließlich für `Requirement`; alle weiteren Entitätstypen (`StakeholderNeed`, `Adr`, `TestCase`, `Risk`, `Issue`) MÜSSEN denselben Mechanismus nutzen. Akzeptanzkriterium: Ein Approve-Übergang für einen ADR oder ein TestCase öffnet denselben Signature-Dialog wie bei Anforderungen; die Signature-Gate-Prüfung ist für alle Entitätstypen einheitlich. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-167)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-167.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-225

---

### REQ-L1-263: Bug: change_reason-Enforcement-Inkonsistenz in Workflow-Transitionen

Der `WorkflowFacade` erzwingt `change_reason` bei Extended-Preset auf Workspace-Ebene für ALLE Transitionen; der `GET /transitions/`-Endpoint gibt jedoch pro-Transitions-Flags `requires_change_reason` (oft `false`) zurück, anhand derer das Frontend das Eingabefeld einblendet. Betroffen: `NeedForm` (draft→in_review), `RiskForm` (Accepted→Closed), `TestCaseForm` (Draft→Ready). Der `GET /transitions/`-Endpoint MUSS das effektive `requires_change_reason` zurückgeben, das Workspace-Preset und per-Transitions-Flag kombiniert. Akzeptanzkriterium: Im Extended-Preset wird das `change_reason`-Eingabefeld immer angezeigt, wenn das Backend es als Pflichtfeld behandelt; im Minimal/Standard-Preset nur wenn die Transition es explizit erfordert. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-169)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-169.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-226

---

### REQ-L1-264: Bug: Requirement-Workflow für Bestandsworkspaces nicht initialisiert

Die Migration `0004_backfill_entity_workflow_definitions` übersprang den Entitätstyp `"Requirement"` unter der falschen Annahme, dass `workspace_service` diesen bei Workspace-Erstellung anlegt. Workspaces, die vor dem entsprechenden Fix erstellt wurden, besitzen keinen `WorkflowEngineDefinition`-Eintrag für `"Requirement"`. Der Lazy-Init-Pfad in `lifecycle_manager.py` greift nur, wenn eine Definition bereits vorhanden ist, und kann den fehlenden Eintrag nicht nachholen. Es MUSS eine neue Django-Migration erstellt werden, die fehlende `Requirement`-Definitionen für alle betroffenen Workspaces nachträglich anlegt (Backfill). Akzeptanzkriterium: Alle Workspaces (einschließlich vor dem Fix erstellter) besitzen nach Ausführung der Migration einen `WorkflowEngineDefinition`-Eintrag für `"Requirement"`. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-170)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-170.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-227

---

### REQ-L1-265: Bug: ArchitectureForm ohne WorkflowStatusEditor-Integration

`ArchitectureForm.tsx` enthält keine `WorkflowStatusEditor`-Komponente, obwohl alle anderen Entitätsformulare (`AdrForm`, `IssueForm`, `RiskForm`, `NeedForm`, `TestCaseForm`, `RequirementForm`) diese Integration erhalten haben. Zusätzlich fehlt der Wert `"architecture"` in `WorkflowArtifactType` (`frontend/src/api/workflow-transitions.ts`). `ArchitectureForm.tsx` MUSS `WorkflowStatusEditor` integrieren; `WorkflowArtifactType` MUSS `"architecture"` als gültigen Typ enthalten. Akzeptanzkriterium: Architektur-Elemente zeigen Workflow-Status und erlaubte Transitionen in der UI; kein hardkodiertes Status-Dropdown in `ArchitectureForm`. Priorität: Must.

**Rationale:** Migration from REQUIREMENTS.md (REQ-171)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-171.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-228

---

### REQ-L1-266: Konfigurierbare per-Transition-change_reason-Anforderung

Die `change_reason`-Pflichtfeld-Logik MUSS pro Transition und pro Entitätstyp konfigurierbar sein — nicht global auf Workspace-Preset-Ebene erzwungen. Das State-Machine-Schema (`WorkflowEngineDefinition` / `definition_store`) MUSS je Transition eine Eigenschaft `requires_change_reason` unterstützen, die festlegt ob `change_reason` für diese spezifische Transition erforderlich ist. Das Workspace-Preset `extended` SOLL nur den Standardwert setzen; individuelle Transitionen können diesen Standard überschreiben. Die globale `_check_change_reason()`-Logik wird durch die per-Transition-Konfiguration ersetzt. Ergänzend: globale Standard-Workflow-Definitionen pro Entitätstyp, Workspace-Level-Override dieser Defaults und eine Reset-to-Default-Funktion (UI: Formular mit Standardwerten, Override und Reset-Button). Akzeptanzkriterium: Zwei Transitionen desselben Entitätstyps können unterschiedliche `requires_change_reason`-Werte haben; Workspace-Preset-Override und Zurücksetzen auf Default sind möglich. Priorität: Should. Abhängigkeit: REQ-166.

**Rationale:** Migration from REQUIREMENTS.md (REQ-172)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-172.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-229

---

### REQ-L1-267: Workflow-Engine-Erweiterung auf nicht unterstützte Entitätstypen

Die Workflow-Engine (`WorkflowTransitionsMixin`, `WorkflowStatusEditor`, `WorkflowArtifactType`) MUSS auf die aktuell nicht unterstützten Entitätstypen `TestRun`, `Baseline`, `ICD`, `Diagram` und `Glossary` erweitert werden. Jeder Entitätstyp MUSS erhalten: einen Backend-ViewSet-Mixin (`WorkflowTransitionsMixin`), eine Workflow-Definition im `definition_store` und eine Frontend-`WorkflowStatusEditor`-Integration im jeweiligen Formular-Component. Akzeptanzkriterium: Alle fünf neuen Entitätstypen zeigen Workflow-Status und erlaubte Transitionen in der UI; Transitionen sind über die `WorkflowFacade`-API auslösbar und in der Datenbank protokolliert. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-173)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-173.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-230

---

### REQ-L1-268: Workflow-Settings-UI-Redesign (Umsetzung REQ-166)

Die bestehende `WorkflowsSection` in den Workspace-Einstellungen ist ein primitives Admin-Tool (rohe UUIDs, Freitexteingabe für State-Namen) und erfüllt REQ-166 nicht. Eine vollwertige Workflow-Settings-UI MUSS bereitstellen: (1) Übersicht der aktuellen Workflow-Konfiguration pro Entitätstyp, (2) Bearbeitung globaler Standardwerte, (3) Anwendung von Workspace-Level-Overrides, (4) Zurücksetzen von Overrides auf globale Defaults (Reset-Button). Rohe UUIDs und Freitexteingaben für State-Namen werden durch strukturierte Formular-Elemente ersetzt. Akzeptanzkriterium: Ein Workspace-Administrator kann für jeden Entitätstyp den aktiven Workflow-Preset einsehen und überschreiben; geänderte Konfigurationen wirken ohne Deployment. Priorität: Should. Abhängigkeit: REQ-172.

**Rationale:** Migration from REQUIREMENTS.md (REQ-174)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-174.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-231

---

### REQ-L1-269: Visueller Workflow-Editor (Phase 1, read-only)

Ein grafischer State-Machine-Editor (`WorkflowEditorPage`, Route `/workflows/:entityType`) MUSS die vollständige Workflow-Definition je Entitätstyp read-only visualisieren: alle States (typ-klassifiziert: initial/active/terminal/error) und Transitionen (mit Rollen-, change_reason- und Signatur-Metadaten) als interaktiver Graph (React Flow) mit Auto-Layout, Inspector-Panel und Mermaid-Export. Datenquelle: `GET /api/v1/workflows/definition/?workspace_id&item_type`. Akzeptanzkriterium: Für jeden der 7 Entitätstypen wird die komplette State-Machine korrekt gerendert; States/Transitionen sind selektier- und inspizierbar. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-176)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-176.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-232

---

### REQ-L1-270: Visueller Workflow-Editor (Phase 2, Edit Mode)

Der Workflow-Editor (REQ-176) MUSS einen admin-gegateten Edit-Modus erhalten, der die Workflow-Definition mutiert: States hinzufügen/umbenennen/löschen und Transitionen hinzufügen/bearbeiten/löschen (Backend-Mutations-Endpunkte unter `/api/v1/workflows/definition/states

**Rationale:** Migration from REQUIREMENTS.md (REQ-177)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-177.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-233

---

### REQ-L1-271: Globales, PRO-PRESET Workflow-Definitions-Modell als Source-of-Truth

Workflow-Definitionen (`WorkflowDefinition`, `backend/workflow/models.py`) existieren aktuell ausschließlich pro Workspace (`workspace_id`-Feld, keine tenant-weite Default-Ebene) — Provisionierung (`provision_workflow_definitions`-Command, Presets minimal/standard/full) seedet direkt in jeden Workspace, ohne gemeinsame Quelle. Es MUSS je Rigor-Preset (Minimal/Standard/Extended) eine EIGENE tenant-weite globale Workflow-Definition je Entitätstyp als Source-of-Truth existieren — KEIN einzelner, presetübergreifend geteilter globaler Default. Ein neu angelegter Workspace MUSS beim Erstellen automatisch die aktuell gültige globale Workflow-Definition SEINES Presets je Entitätstyp erben (Persistenzform — Kopie oder Referenz — ist Aufgabe des Datenmodell-Designs, nicht dieser Anforderung). Der on-default/customized-Zustand eines Workspace (REQ-180) MUSS gegen den globalen Default DES EIGENEN Presets des Workspace berechnet werden, nicht gegen einen presetübergreifenden Durchschnitts- oder Mehrheitswert — dies vereinheitlicht zugleich das Backfill- und Change-Handling über alle drei Presets hinweg. Akzeptanzkriterium: Für einen frisch erstellten Workspace ist ohne manuelle Konfiguration für jeden Entitätstyp eine funktionsfähige, aus dem globalen Default SEINES Presets abgeleitete Workflow-Definition vorhanden; zwei Workspaces mit unterschiedlichem Preset erben nachweislich unterschiedliche globale Defaults, auch wenn beide "on-default" sind. Priorität: Must. Abhängigkeit: REQ-166, REQ-172.

**Rationale:** Migration from REQUIREMENTS.md (REQ-178)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-178.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-234

---

### REQ-L1-272: Workspace-Workflow-Override bleibt vollständig editierbar

Ein Workspace MUSS seine geerbte Workflow-Definition weiterhin vollständig anpassen können (States/Transitionen hinzufügen, ändern, entfernen) — die bestehende Editier-Fähigkeit des Workflow-Editors (REQ-177, `WorkflowEditorPage.tsx`, Mutations-Endpunkte unter `/api/v1/workflows/definition/...`) DARF durch die Einführung globaler Defaults (REQ-178) nicht eingeschränkt, verändert oder entfernt werden (Regressionsschutz). Eine workspace-eigene Anpassung wird als Override der globalen Definition geführt und bleibt unabhängig vom globalen Default persistiert, bis ein Reset (REQ-180) erfolgt. Akzeptanzkriterium: Alle bisher via REQ-177 unterstützten Bearbeitungsoperationen (State/Transition hinzufügen/umbenennen/löschen, Validierungsregeln) funktionieren nach Einführung des globalen Default-Modells unverändert für einen Workspace mit Override. Priorität: Must. Abhängigkeit: REQ-176, REQ-177, REQ-178.

**Rationale:** Migration from REQUIREMENTS.md (REQ-179)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-179.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-235

---

### REQ-L1-273: Workflow Reset-to-Default

Ein Workspace, dessen Workflow-Definition vom globalen Default abweicht (Override, REQ-179), MUSS jederzeit auf den aktuell gültigen globalen Default zurückgesetzt werden können. Das System MUSS erkennbar unterscheiden, ob eine Workspace-Workflow-Definition aktuell dem globalen Default entspricht ("on-default") oder davon abweicht ("customized") — sichtbar für Nutzer und Administratoren. Der Reset verwirft workspace-spezifische Anpassungen vollständig und übernimmt den globalen Default. Akzeptanzkriterium: Für einen Workspace im "customized"-Zustand ist eine Reset-Aktion verfügbar, die nach Ausführung den "on-default"-Zustand herstellt; der Zustand ("on-default"/"customized") ist vor und nach dem Reset für den Nutzer erkennbar. Priorität: Must. Abhängigkeit: REQ-178, REQ-179.

**Rationale:** Migration from REQUIREMENTS.md (REQ-180)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-180.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-236

---

### REQ-L1-274: Globales Permissions-Default-Modell als Source-of-Truth

Berechtigungen (RBAC-Rollenmodell admin/editor/viewer/approver, `ItemPermission`-Datenmodell, `auth_tenancy`) existieren aktuell ausschließlich pro Workspace — analog zum bisherigen Workflow-Modell (REQ-178, vor dessen Fix). Es MUSS — symmetrisch zu REQ-178 — eine tenant-weite globale Permissions-Default-Definition existieren. Ein neu angelegter Workspace MUSS beim Erstellen automatisch die aktuell gültige globale Permissions-Default-Definition erben. Diese Anforderung beschreibt ausschließlich das Datenmodell (Global-Default + Vererbung); ob und wie dieses Modell die bestehende hartkodierte `UserRole`/`ItemPermission`-Durchsetzung als autoritative Zugriffskontrolle ablöst, regelt REQ-186. Akzeptanzkriterium: Für einen frisch erstellten Workspace ist ohne manuelle Konfiguration ein aus dem globalen Default abgeleitetes, funktionsfähiges Berechtigungsschema vorhanden. Priorität: Must. Abhängigkeit: REQ-014, REQ-178.

**Rationale:** Migration from REQUIREMENTS.md (REQ-181)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-181.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-237

---

### REQ-L1-275: Workspace-Permissions-Override bleibt vollständig editierbar

Ein Workspace MUSS seine geerbte Permissions-Konfiguration weiterhin vollständig anpassen können (z.B. abweichende Rollenzuordnungen, Item-Permissions). Eine workspace-eigene Anpassung wird als Override der globalen Permissions-Default-Definition geführt und bleibt unabhängig davon persistiert, bis ein Reset (REQ-183) erfolgt. Regressionsschutz bezieht sich auf die für Nutzer sichtbare Bearbeitungsfähigkeit (bestehende Bedienelemente/Operationen aus REQ-014 und Item-Permission-Verwaltung MÜSSEN funktional erhalten bleiben) — NICHT auf den Fortbestand der bisherigen hartkodierten `UserRole`/`ItemPermission`-Durchsetzungslogik selbst, deren Ablösung als autoritative Zugriffskontrolle explizit Ziel von REQ-186 ist. Akzeptanzkriterium: Alle bisher unterstützten Berechtigungs-Bearbeitungsoperationen funktionieren nach Einführung des globalen Default-Modells unverändert für einen Workspace mit Override — unabhängig davon, ob im Hintergrund bereits das neue autoritative Modell (REQ-186) oder noch die Legacy-Durchsetzung entscheidet. Priorität: Must. Abhängigkeit: REQ-181.

**Rationale:** Migration from REQUIREMENTS.md (REQ-182)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-182.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-238

---

### REQ-L1-276: Permissions Reset-to-Default

Ein Workspace, dessen Permissions-Konfiguration vom globalen Default abweicht (Override, REQ-182), MUSS jederzeit auf den aktuell gültigen globalen Default zurückgesetzt werden können. Das System MUSS — analog zu REQ-180 — erkennbar unterscheiden, ob die Workspace-Permissions-Konfiguration aktuell dem globalen Default entspricht ("on-default") oder davon abweicht ("customized"). Akzeptanzkriterium: Für einen Workspace im "customized"-Zustand ist eine Reset-Aktion verfügbar, die nach Ausführung den "on-default"-Zustand herstellt; der Zustand ist vor und nach dem Reset für den Nutzer erkennbar. Priorität: Must. Abhängigkeit: REQ-181, REQ-182.

**Rationale:** Migration from REQUIREMENTS.md (REQ-183)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-183.
**Test Status:** Missing
**Remarks:** Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-239

---

### REQ-L1-277: Settings-IA-Split: System Settings als eigener Navigationsbereich

Workspace-Einstellungen und System-Einstellungen sind aktuell in einer einzigen Komponente/Route zusammengefasst (`WorkspaceSettings.tsx`, Tabs general/traceability/visibility/llm/governance/admin). Es MUSS ein eigenständiger Top-Level-Navigationseintrag "System Settings" mit eigener Route entstehen. Workspace-bezogene Einstellungen (Allgemein, Traceability, Sichtbarkeit, LLM) VERBLEIBEN unter der bestehenden workspace-gebundenen Settings-Route. System-weite Einstellungen (Administration, System-Health, Lifecycle sowie neu: globale Workflow-Defaults REQ-178 und globale Permissions-Defaults REQ-181) ZIEHEN in den neuen System-Settings-Bereich um. Bestehendes Karten-/Tab-Styling bleibt visuell unverändert — reiner IA-Split, kein Redesign. Akzeptanzkriterium: System-weite Einstellungen sind über einen eigenen Top-Level-Navigationseintrag erreichbar und nicht mehr Teil der workspace-gebundenen Settings-Ansicht; Workspace-bezogene Einstellungen bleiben an ihrem bisherigen Ort erreichbar. Priorität: Should.

**Rationale:** Migration from REQUIREMENTS.md (REQ-184)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-184.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-240

---

### REQ-L1-278: Governance-Tab "Workflows & Berechtigungen" auf Global/Override/Reset-Modell umstellen

Der bestehende Governance-Tab (`WorkspaceSettings.tsx:295`, `WorkflowsSection.tsx`, `PermissionsSection`) bildet ausschließlich workspace-lokale Konfiguration ab und wird durch die Einführung globaler Defaults (REQ-178, REQ-181) fachlich obsolet — er MUSS dismantled und auf das neue Modell umgebaut werden: globaler Default (Verwaltung im System-Settings-Bereich, REQ-184), Workspace-Override-Status ("on-default"/"customized") und Zugriff auf die Reset-Aktion (REQ-180, REQ-183) für Workflows und Berechtigungen. Das konkrete visuelle/interaktive Design dieser Umstellung ist NICHT Teil dieser Anforderung, sondern eines nachgelagerten Design-Schritts (ui-ux-designer). Akzeptanzkriterium: Der bestehende Governance-Tab (bzw. sein Nachfolger) zeigt für Workflows und Berechtigungen erkennbar den Override-Status je Workspace und bietet Zugriff auf Reset und (im System-Settings-Bereich) auf die globalen Defaults. Priorität: Should. Abhängigkeit: REQ-178, REQ-180, REQ-181, REQ-183, REQ-184.

**Rationale:** Migration from REQUIREMENTS.md (REQ-185)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-185.
**Test Status:** Missing
**Remarks:** UI/UX

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-241

---

### REQ-L1-279: Globales Permission-Modell wird alleinige autoritative Durchsetzungsinstanz

Die tatsächliche Zugriffskontrolle läuft heute ausschließlich über hartkodierte `UserRole`/`ItemPermission`-Prüfungen (COMP-AT-002 AuthorizationService, `backend/auth_tenancy`) — unabhängig vom Global-Default/Override/Reset-Permissions-Modell aus REQ-181–183, das ursprünglich als zusätzliche Governance-/Anzeige-Schicht NEBEN dieser Durchsetzung konzipiert war. Der Nutzer hat entschieden, dass diese additive Einordnung nicht ausreicht: Das Global-Default/Override/Reset-Permission-Modell MUSS die reale, alleinige autoritative Durchsetzungsinstanz für Zugriffsentscheidungen in der gesamten Anwendung werden und die hartkodierten `UserRole`/`ItemPermission`-Prüfungen vollständig ablösen (nicht nur ergänzen). Akzeptanzkriterium: Nach vollständiger Umsetzung entscheiden ausschließlich das globale Permission-Default-Modell und seine Workspace-Overrides (REQ-181–183) über Zugriffsberechtigungen für alle Artefakttypen und Operationen; keine Zugriffsentscheidung im System stützt sich mehr auf die alte hartkodierte `UserRole`/`ItemPermission`-Prüfung als primäre Quelle. Priorität: Must. Abhängigkeit: REQ-181, REQ-182, REQ-183.

**Rationale:** Migration from REQUIREMENTS.md (REQ-186)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-186.
**Test Status:** Missing
**Remarks:** Security

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-242

---

### REQ-L1-280: Sicherer Migrationspfad mit sichtbarem Regressionsrisiko für Permission-Ablösung

Die Ablösung der hartkodierten `UserRole`/`ItemPermission`-Durchsetzung durch das neue autoritative Permission-Modell (REQ-186) betrifft die live Zugriffskontrolle der gesamten Anwendung und hat damit einen erheblichen Blast-Radius. Die Umstellung DARF NICHT als stiller Hard-Cutover erfolgen. Es MUSS ein sicherer Rollout-Pfad existieren, der Regressionsrisiken vor der endgültigen Abschaltung der Legacy-Prüfung sichtbar macht, statt sie zu verbergen (konkreter Mechanismus — z.B. Parallelbetrieb/Verifikation alt vs. neu, schrittweise Aktivierung — ist Aufgabe von database-engineer/senior-developer und NICHT Teil dieser Anforderung). Akzeptanzkriterium: Vor der endgültigen Abschaltung der `UserRole`/`ItemPermission`-Hardcoding-Prüfung liegt ein Nachweis vor, dass zwischen alter und neuer Zugriffsentscheidung keine unbeabsichtigten Abweichungen bestehen, oder etwaige Abweichungen sind explizit dokumentiert und bewusst akzeptiert; ein negativer bzw. fehlender Nachweis blockiert den Cutover. Priorität: Must. Abhängigkeit: REQ-186.

**Rationale:** Migration from REQUIREMENTS.md (REQ-187)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-187.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-243

---

### REQ-L1-281: Selbstständige Erstinitialisierung der Applikation ohne separate Bootstrap-/Provisioning-Mechanismen

Die Erstinitialisierung eines frischen Deployments erfolgt aktuell über zwei getrennte, fehleranfällige Mechanismen: (1) einen dedizierten `bootstrap`-Service in `docker-compose.yml` (`command: python manage.py bootstrap_admin`), der ausschließlich den Admin-Account anlegt, und (2) das separate Management-Command `provision_workflow_definitions` für Workflow-Definitionen pro Workspace, das NICHT automatisch aufgerufen wird. Der Bootstrap-Service ruft das Workflow-Seeding nicht mit auf — Folge: Nach jedem `docker-compose up` mit frischem Volume steht der Demo-/Erst-Workspace ohne Workflow-Definitionen da. Die Applikation MUSS ihren Erstinitialisierungs-Zustand (Admin-Account UND Default-Workflow-Definitionen pro neuem Workspace) beim ersten Start SELBST herstellen — OHNE dediziertes Bootstrap-Container-/Service-Pattern und OHNE separat manuell aufzurufendes Provisioning-Command. Denkbare Zielarchitektur (nicht bindend vorgeschrieben): Self-Initializing beim Anwendungsstart, z.B. via Django `AppConfig.ready()`, Signal, Lazy-Check beim ersten Request oder direkt im `create_workspace`-Aufruf. Diese Anforderung ergänzt REQ-178 (regelt das Datenmodell des globalen, presetweiten Workflow-Defaults) um den Trigger-/Provisionierungs-Mechanismus (WIE/WANN die Erstinitialisierung ausgelöst wird) — sie ersetzt REQ-178 nicht. Akzeptanzkriterium: Ein frisches `docker-compose up` (leeres Volume) führt ohne manuellen Zusatzschritt zu einem vollständig initialisierten Demo-/Erst-Workspace (Admin-Account UND Workflow-Definitionen vorhanden) — ohne dedizierten Bootstrap-Container und ohne manuellen Aufruf eines Provisioning-Commands. Priorität: Should. Abhängigkeit: REQ-178.

**Rationale:** Migration from REQUIREMENTS.md (REQ-188)
**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-188.
**Test Status:** Missing
**Remarks:** Non-Functional

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-244

---

### REQ-L1-282: ReviewPolicy-Modell und Workspace-Konfiguration

Ein neues `ReviewPolicy`-Modell mit Feldern `workspace`, `mode` (auto/review_changes/review_all/review_high_risk), und `min_confidence` (Dezimalzahl, Schwellwert für high_risk-Modus) wird in die Persistenz-Schicht eingefügt. `SettingsService` erhält zwei neue Methoden: `get_effective_review_policy(workspace_id)` (liefert Workspace-Policy oder Tenant-Default) und `update_review_policy(workspace_id, mode, min_confidence)` (speichert Workspace-Override). Die Konfiguration ist pro-Workspace editierbar und wirkt auf alle AI-Derivation- und Approval-Workflow-Übergänge. Priorität: Must. Abhängigkeit: Phase 0 (outdate-Mechanismus, WorkflowItemState).

**Rationale:** Migration from REQUIREMENTS.md (REQ-189)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-189.
**Test Status:** Missing
**Remarks:** Data

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-245

---

### REQ-L1-283: MCP-Tool-Gruppe `review.*` für Approval-Workflows

Neue MCP-Tool-Group `review` mit vier Tools: `review.list_pending` (Artefakte in `in_review`-State), `review.approve` (Transition zu `approved`), `review.reject` (Transition zu einem `rejected`/`draft`-State), `review.request_changes` (Requester-Notification ohne State-Änderung). Jedes Tool ist Thin Wrapper über `WorkflowFacade`-Transitionen und erzeugt `WorkflowHistoryEntry`-Audit-Einträge. RBAC-Gating: nur `approver`-Rolle und höher darf diese Tools nutzen. Tools werden in `backend/mcp_server/tool_registry.py` registriert. Priorität: Must. Abhängigkeit: REQ-190-Test (Approval-Workflows aus Phase 0).

**Rationale:** Migration from REQUIREMENTS.md (REQ-190)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-190.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-246

---

### REQ-L1-284: REST-Endpunkt für ReviewPolicy-Verwaltung

Neuer REST-Endpoint `GET/PUT /api/v1/workspaces/{workspace_id}/review-policy/` (admin-only) mit DRF-Serializer für `ReviewPolicy`. Der GET-Endpoint liefert die effektive Policy (Workspace-Override oder Tenant-Default). Der PUT-Endpoint aktualisiert die Workspace-Policy via `SettingsService.update_review_policy()` und validiert die Eingaben (mode muss gültig sein, min_confidence ≥ 0.0 und ≤ 1.0). Fehlerhafte Eingaben werden mit HTTP 400 abgelehnt, fehlende Admin-Berechtigung mit HTTP 403. Priorität: Must. Abhängigkeit: REQ-189.

**Rationale:** Migration from REQUIREMENTS.md (REQ-191)
**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-191.
**Test Status:** Missing
**Remarks:** API

**Domain:** system
**Priorität:** desired
**Externe Interfaces:**
- Eingang: N/A
- Ausgang: N/A

**Traceability:** REQ-L0-247


---

### REQ-L1-285: Integration of Context Generators and Prompt Templates

Implement context generators to automate prompt enrichment, and introduce a flexible prompt template system. Dies ermöglicht dynamische Agenten-Workflows, die kontextbezogen Informationen aufbereiten.

**Rationale:** Derived from SN-248 (Superpower Context Generation and Prompt Templates).
**Implementation State:** Planned
**Review Findings:** Abgeleitet aus Phase 1 Superpowers Einarbeitung.
**Test Status:** Missing
**Remarks:** Backend/AI Engine

**Domain:** system
**Priorität:** must
**Externe Interfaces:**
- Eingang: Context Data, Prompt Configuration
- Ausgang: Enriched Prompts

**Traceability:** REQ-L0-248

---

### REQ-L1-286: Implement Agent Templates and Review Endpoints

Derive Write Modes must be supported natively to adapt agent responses. Agent Templates shall be implemented according to Phase 6 specifications, integrated with the frontend feedback strategy and review endpoints.

**Rationale:** Derived from SN-249 (Superpower Agent Templates and Write Modes).
**Implementation State:** Planned
**Review Findings:** Abgeleitet aus Phase 1 Superpowers Einarbeitung.
**Test Status:** Missing
**Remarks:** Full Stack

**Domain:** system
**Priorität:** must
**Externe Interfaces:**
- Eingang: Template Config, Feedback Inputs
- Ausgang: Agent Response, Review Output

**Traceability:** REQ-L0-249

