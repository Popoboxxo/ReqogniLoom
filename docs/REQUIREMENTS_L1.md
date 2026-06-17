# ReqFlow — L1 System-Anforderungen

> Status: ENTWURF | Erstellt: 2026-06-17 | Quelle: KONZEPT.md (Runden 1–4, FINAL)
>
> Dieses Dokument definiert die Stakeholder-Needs (SN) und L1-System-Anforderungen (SYS-REQ)
> für ReqFlow v1. Es bildet die Grundlage für die formale SE-Kaskade.
> Sprache: Deutsch (internes Dokument gemäß Sprachregeln).

---

## Stakeholder-Needs (SN)

### SN-01: Maschinenlesbarer Anforderungskontext für AI-Agenten

AI-Agenten (Coding-Agenten, Orchestratoren, CI/CD-Pipelines) benötigen strukturierten,
maschinenlesbaren Zugriff auf Anforderungen, Architektur und Tests — ohne Text-Parsing
oder Webhook-Wrapper — damit Code-Generierung und -Review mit vollständigem fachlichem
Kontext erfolgen können.

**Rationale:** Ohne strukturierte Schnittstelle geht AI-generierter Code oft am fachlichen
Kontext vorbei, weil das "Warum" hinter dem Code nicht maschinenlesbar vorliegt (KONZEPT.md, Abschnitt 1).

---

### SN-02: Skalierbare SE-Tiefe ohne Produktwechsel

Teams unterschiedlicher Reife (von Startups bis zu Automotive-Zulieferern) müssen
dieselbe Plattform mit unterschiedlicher Prozessstrenge nutzen können — von einfachem
Anforderungs-CRUD bis zu vollständigem Systems Engineering mit Baselines,
Approval-Workflows und Audit-Trails — ohne das Tool zu wechseln oder die Infrastruktur
umzubauen.

**Rationale:** Der Markt bietet keinen Mittelpunkt zwischen zu leichtgewichtigen Agile-Tools
und zu schweren Enterprise-Systemen (KONZEPT.md, Abschnitt 1, 2).

---

### SN-03: Vollständige Traceability zwischen Requirements, Architektur und Tests

Systems Engineers und AI-first Teams benötigen bidirektionale Verknüpfungen zwischen
Anforderungen, Architektur-Elementen und Testfällen, um Impact-Analysen, Coverage-Reports
und Konsistenz-Prüfungen durchzuführen — sowohl manuell als auch durch Agenten automatisiert.

**Rationale:** Ohne Traceability sind Blast-Radius-Analysen bei Anforderungsänderungen
nicht möglich; dies ist ein Kernbedarf beider Zielgruppen (KONZEPT.md, Abschnitt 3.4, 4.1).

---

### SN-04: Unveränderliche, benannte Anforderungs-Baselines auf mehreren Ebenen

Teams in regulierten oder sicherheitskritischen Umgebungen müssen zu jedem Zeitpunkt
auf einen exakten, unveränderlichen Stand aller Anforderungen zurückgreifen können —
auf Dokumentebene, Projektebene und instanzweit — um Übergaben, Reviews und spätere
Compliance-Nachweise zu ermöglichen.

**Rationale:** Baselines sind ein Must-Have für die SE-Zielgruppe; ohne sie ist
ReqFlow für Systems Engineers nicht ernsthaft nutzbar (KONZEPT.md, Abschnitt 4.1, 7.3).

---

### SN-05: Konfigurierbarer Item-Lifecycle mit Rollen und Approval-Gates

Projektteams müssen den Lifecycle-Workflow für Requirements, Architektur-Elemente und
Testfälle an ihre Domäne und Compliance-Anforderungen anpassen können — inklusive
rollengebundener Approval-Gates — ohne Code-Änderungen am System.

**Rationale:** Ein hartcodierter Status-Enum (Draft/Approved/Deprecated) ist zu starr
für domänenspezifische Prozesse und formale Compliance-Anforderungen
(KONZEPT.md, Abschnitt 7a).

---

### SN-06: Self-Hosted Deployment ohne Vendor-Lock-in

Datenschutz-sensible Organisationen und Teams mit eigener Infrastruktur müssen
ReqFlow vollständig on-premise betreiben können — ohne Cloud-Zwang, ohne Lizenzkosten,
mit voller Datenkontrolle.

**Rationale:** Open Source (Apache 2.0) + Docker Compose ist die bewusste Entscheidung
gegen Vendor-Lock-in; SaaS erst ab v2 (KONZEPT.md, Abschnitt 1, 9.1, Anhang A).

---

### SN-07: LLM-gestützte Qualitätssicherung als optionale Capability

Teams, die LLM-Zugang haben, müssen AI-gestützte Funktionen (Validierung,
Zerlegungsvorschläge, Konsistenz-Checks) nutzen können — ohne dass das System bei
fehlendem LLM-Zugang nicht funktioniert.

**Rationale:** LLM als pluggable Capability ist eine der zwei AI-nativen Dimensionen;
Self-Hosted-Nutzer ohne LLM-Zugang dürfen keine Kernfunktionalität verlieren
(KONZEPT.md, Abschnitt 1, 9.3).

---

### SN-08: Mandantenfähige Isolation für spätere SaaS-Erweiterung

Das Datenmodell muss bereits in v1 so angelegt sein, dass eine spätere Aktivierung
echter Multi-Tenancy (mehrere Kunden auf einer Instanz) keine Datenmigration erfordert.

**Rationale:** Row-Level-Isolation mit tenant_id ist die Voraussetzung für den v2-SaaS-Betrieb
ohne Schema-Umbau (KONZEPT.md, Abschnitt 5.4, Anhang A).

---

### SN-09: Zweisprachige Benutzeroberfläche (Deutsch und Englisch)

Teams in deutschsprachigen Märkten und international gemischte Teams müssen die
Oberfläche in ihrer Arbeitssprache nutzen können, ohne Funktionseinschränkungen.

**Rationale:** Duale Marktausrichtung DE/EN ist eine v1-Entscheidung; nachträgliche
String-Extraktion ist aufwändiger als proaktive i18n-Integration
(KONZEPT.md, Abschnitt 9.3, Anhang A).

---

### SN-10: Terminologie-Flexibilität für zwei Zielgruppen ohne Datenverlust

Software-Teams (Epics, Stories, Acceptance Criteria) und Systems Engineers
(System Requirements, Functions, Verification Criteria) müssen auf demselben
Datenmodell arbeiten, ohne dass ein Profilwechsel Datenverluste oder Migrationen verursacht.

**Rationale:** Gemeinsames generisches Artefakt-Datenmodell mit konfigurierbaren
Terminologie-Layern ist das Fundament der Dual-Zielgruppen-Strategie
(KONZEPT.md, Abschnitt 3.2, 3.3).

---

### SN-11: Vollständiger Audit-Trail für agentengesteuerte und manuelle Änderungen

Compliance-orientierte Teams müssen zu jeder Anforderung, jedem Architektur-Element
und jedem Testfall nachvollziehen können: wer hat was wann geändert — einschließlich
AI-Agenten, die via MCP schreiben.

**Rationale:** Vollständige Auditierbarkeit aller Änderungen ist eine explizite
Non-Functional-Anforderung; MCP-Schreibzugriff ohne Audit-Log wäre ein Sicherheitsrisiko
(KONZEPT.md, Abschnitt 4.2, 6.1, 8.1).

---

### SN-12: REST API und MCP Server als gleichrangige, vollständige Schnittstellen

Entwickler und AI-Agenten müssen alle CRUD-Operationen auf allen Artefakttypen
sowohl über REST als auch über MCP vollständig durchführen können — keine
Zweit-Klassen-Schnittstelle.

**Rationale:** Der MCP Server ist kein Anhängsel, sondern greift direkt auf die
Django-Service-Schicht zu; REST ist für direkte Integration, MCP für AI-Agenten
(KONZEPT.md, Abschnitt 6.1, 9.3).

---

## L1 System-Anforderungen (SYS-REQ)

### SYS-REQ-01: Artefakt-Hierarchie mit beliebiger Tiefe

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

---

### SYS-REQ-02: Requirements CRUD mit konfigurierbarem Status-Workflow

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

---

### SYS-REQ-03: Traceability-Engine mit bidirektionalen Links

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

---

### SYS-REQ-04: ArchitectureElement als eigenständiger, schreibbarer Artefakttyp

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

---

### SYS-REQ-05: MCP Server mit vollständigem Read/Write-Zugriff auf alle Artefakttypen

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

---

### SYS-REQ-06: REST API mit OpenAPI-Spezifikation für alle Entitäten

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

---

### SYS-REQ-07: Configurable-Rigor-Presets (Minimal / Standard / Extended)

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

---

### SYS-REQ-08: Multi-Level-Baselines (Dokument / Projekt / Global)

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

---

### SYS-REQ-09: Konfigurierbarer Item-Level-Workflow mit Audit-Trail

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

---

### SYS-REQ-10: Rollenbasierte Zugriffskontrolle (Admin, Editor, Viewer, Approver)

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

---

### SYS-REQ-11: Vollständiger Audit-Trail für alle Änderungen

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

---

### SYS-REQ-12: Testmanagement mit Coverage-Tracking

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

---

### SYS-REQ-13: LLM-Capabilities als konfigurierbare, optionale Features

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

---

### SYS-REQ-14: Konfigurierbare Terminologie-Profile (Dev-Modus / SE-Modus)

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

---

### SYS-REQ-15: Multi-Tenancy-Vorbereitung mit Row-Level-Isolation

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

---

### SYS-REQ-16: Zweisprachige Benutzeroberfläche (Deutsch und Englisch)

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

---

### SYS-REQ-17: React-UI mit Dashboard, Editor und Navigations-Komponenten

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

---

### SYS-REQ-18: Docker-Compose-Deployment für Self-Hosted-Betrieb

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

---

### SYS-REQ-19: Export in JSON und CSV für alle Entitäten

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

---

### SYS-REQ-20: Volltextsuche über alle Artefakttypen

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

**OP-01 — LLM-Capabilities-Scope v1:**
Welche der vier LLM-Capabilities (Generierung, Validierung, Decomposition,
Test-Ableitung/Konsistenz-Checks) werden in v1 operativ implementiert?
Empfehlung aus KONZEPT.md: Validierung + Decomposition.
*Auswirkung auf: SYS-REQ-13, L2-MCP-01*

**OP-02 — Preset-Downgrade-Semantik:**
Was passiert mit Baselines, Approved-Items und Workflows beim Wechsel auf eine
niedrigere SE-Stufe (z.B. Extended → Standard)?
*Auswirkung auf: SYS-REQ-07, SYS-REQ-08, L2-BL-01*

**OP-03 — Workflow-Wechsel-Semantik:**
Was passiert mit Items in States, die nach einer WorkflowDefinition-Änderung
nicht mehr existieren?
*Auswirkung auf: SYS-REQ-09, L2-WF-01*

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade | 2026-06-17*
*Nächster Schritt: Übergabe an se-critic für Quality-Gate-Validierung*
