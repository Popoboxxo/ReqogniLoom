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
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

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
