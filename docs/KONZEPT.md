# ReqFlow — Konzept-Dokument

> Status: FINAL — Runden 1, 2, 3 und 4 abgeschlossen | Letzte Aktualisierung: 2026-06-17
>
> Dieses Dokument konsolidiert alle Entscheidungen aus den Ideation-Runden 1–4 und dient
> als vollständige Konzeptgrundlage für die formale Anforderungsaufnahme (requirements-Agent).
> Basis: VISION.md + KONZEPT.md Runden 1–3 (Commit 3ac8a29)

---

## 1. Executive Summary — Was ist ReqFlow und warum existiert es?

ReqFlow ist das erste Requirements-Management-Tool, das AI-Agenten als native Prozess-Teilnehmer behandelt — nicht als Texthelfer oder nachträgliches Add-on, sondern als vollständige, strukturierte Schnittstelle für den gesamten Anforderungslebenszyklus.

### Das Problem

Softwareteams und Systems Engineers teilen 2026 ein gemeinsames, wachsendes Problem: AI-Agenten sind längst keine isolierten Assistenten mehr. Sie generieren Code, schreiben Tests, führen Reviews durch und orchestrieren Workflows. Doch ihnen fehlt der strukturierte, maschinenlesbare Zugriff auf das *Warum* hinter dem Code: auf Anforderungen, Akzeptanzkriterien, Testabdeckung und Traceability. Die Folge ist, dass AI-generierter Code oft am Kontext vorbeigeht — weil der Kontext nirgends maschinenlesbar vorliegt.

Gleichzeitig stecken viele Teams zwischen zwei unbefriedigenden Polen: Agile-Tools wie Jira oder Linear sind zu leichtgewichtig für echtes Requirements Engineering. Enterprise-Systeme wie IBM DOORS, Siemens Polarion oder PTC Codebeamer sind zu schwer, zu teuer und haben keinen AI-nativen Ansatz. Der Mittelweg fehlt.

### Die Lösung

ReqFlow schließt diese Lücke durch drei strategische Entscheidungen:

Erstens bietet ReqFlow einen nativen MCP Server (Model Context Protocol) als gleichrangige Schnittstelle neben der REST API. AI-Agenten können damit direkt und strukturiert Anforderungen, Architektur-Elemente und Tests abrufen, anlegen, verändern und in Beziehung setzen — ohne Umwege über Text-Parsing oder Webhook-Wrapper.

Zweitens skaliert ReqFlow über ein gemeinsames generisches Artefakt-Datenmodell von einfachem Anforderungsmanagement bis zu vollwertigen Systems-Engineering-Strukturen. Die Tiefe der Nutzung ist über konfigurierbare Projekt-Presets einstellbar, nicht global hart verdrahtet.

Drittens ist ReqFlow vollständig Open Source (Apache 2.0) mit Self-Hosted-Deployment via Docker Compose — ohne Vendor-Lock-in, ohne Lizenzkosten, mit maximaler Kontrolle über Daten und Infrastruktur.

### Was "AI-nativ" bei ReqFlow bedeutet — zwei Dimensionen

"AI-nativ" ist bei ReqFlow kein Marketing-Begriff, sondern beschreibt zwei konkrete, architektonische Dimensionen:

**Dimension 1 — LLM als pluggable Capability quer über alle Artefakttypen**

LLM-Unterstützung ist nicht auf ein einzelnes Tool (`requirement.validate`) beschränkt. LLMs werden als konfigurierbare, optionale Capability quer über alle Artefakttypen eingebunden: Requirements, Architektur-Elemente und Tests. Die Architektur sieht alle vier Capabilities als pluggable vor, sodass die konkrete v1-Auswahl (welche Capabilities werden operativ implementiert) keine Architekturänderung erfordert. Konkrete Einsatzpunkte:

- *Generierung*: LLM-gestützte Vorschläge für Requirements-Formulierungen, Testfall-Ableitung aus Anforderungen, Architektur-Beschreibungen
- *Validierung*: Qualitätsprüfung auf Vollständigkeit, Eindeutigkeit und Testbarkeit (nicht nur bei Requirements, sondern auch bei Test-Coverage-Analysen)
- *Decomposition*: Automatische Zerlegungsvorschläge für komplexe Anforderungen in Kind-Artefakte
- *Konsistenz-Checks*: LLM-gestützte Prüfung auf Widersprüche zwischen Requirements, Architektur und Tests

Technisch: Bring-Your-Own-Provider / Standard-API. Default-Empfehlung ist Claude (neueste verfügbare Version). Jede LLM-Capability ist einzeln konfigurierbar und kann pro Deployment deaktiviert werden. Self-Hosted-Nutzer ohne LLM-Zugang verlieren AI-gestützte Features, aber keine Kernfunktionalität — der Rest des Systems bleibt vollständig nutzbar.

**Dimension 2 — MCP als vollwertige externe Schnittstelle für ALLE Artefakttypen**

Der MCP Server bietet nicht nur Zugriff auf Requirements. Alle drei zentralen Artefakttypen — Requirements, Architektur und Tests — sind via MCP vollständig les- und schreibbar. Architektur-Elemente sind damit ein eigener, schreibbarer Artefakttyp im Datenmodell und in der MCP-Tool-Liste. Details im MCP-Abschnitt (Abschnitt 6).

### Positionierung

ReqFlow besetzt den bisher leeren Quadranten im Markt: AI-nativ und handhabbar — mit echtem Systems-Engineering-Rückgrat, aber ohne Enterprise-Overhead.

```
                    Einfachheit / Agilität
                           ^
                           |
          Linear  ---------+--------- ReqFlow (Ziel)
          Notion           |
                           |
─────── AI-Add-on ─────────+───────── AI-nativ ─────
                           |
         Jira + AI-Plugin  |
                           |
    DOORS / Polarion ──────+
    Codebeamer             |
                           v
                   Enterprise-Komplexität
```

---

## 2. Designprinzip: Configurable Rigor

"Configurable Rigor" ist das zentrale Differenzierungsmerkmal von ReqFlow und die Antwort auf die Frage, wie ein einziges Produkt zwei so unterschiedliche Zielgruppen bedienen kann.

### Kerngedanke

Die Strenge des Prozesses — SE-Tiefe, Audit-Anforderungen, Compliance-Stufe, Workflow-Stufen — ist bei ReqFlow keine globale, fest verdrahtete Eigenschaft des Systems. Sie ist pro Projekt und teils pro Dokument über konfigurierbare Presets einstellbar. Ein Startup-Team, das schnell iteriert, wählt ein minimales Preset und hat eine schlanke, agile Erfahrung. Ein Automotive-Zulieferer, der formale Baselines, Approval-Workflows und Audit-Trails benötigt, aktiviert ein erweitertes Preset — ohne ein anderes Produkt zu kaufen oder die Infrastruktur zu wechseln.

Dieses Prinzip löst gleichzeitig das "beide Zielgruppen in einem Produkt"-Problem: Es gibt keine Kompromisse im Datenmodell und keine Zielgruppen-spezifischen Code-Pfade. Stattdessen gibt es ein gemeinsames, reichhaltiges Fundament und konfigurierbare Sichtbarkeits- und Verhaltensschichten darüber.

### Wie Configurable Rigor sich durch das System zieht

**Im Datenmodell:** Das Datenmodell ist von Beginn an vollständig — alle Felder für Audit, Compliance und erweiterte Workflows sind vorhanden. Was sich ändert, ist ob und wie diese Felder vom System genutzt und erzwungen werden. Ein Projekt im Minimal-Preset hat dieselbe Datenstruktur wie ein Projekt im Extended-Preset — nur mit weniger Pflichtfeldern und ohne Approval-Workflow.

**In der UI:** Die Oberfläche blendet Funktionen ein oder aus, je nach aktivem Preset. Ein Nutzer im Minimal-Preset sieht keine Baselines, keine Approval-Buttons, keine Compliance-Felder — sie existieren im System, sind aber ausgeblendet. Der Wechsel zu einem höheren Preset aktiviert diese Elemente schrittweise, ohne Datenmigration.

**In der MCP-API:** Die MCP-Tools sind immer vollständig verfügbar. Das Preset beeinflusst jedoch, welche Felder in Responses zurückgegeben werden und welche Operationen serverseitig validiert werden (z.B. ob ein `requirement.update` ohne `change_reason` abgelehnt wird, wenn das Projekt einen strengeren Preset hat).

**In Presets:** Presets sind JSON-Konfigurationen, die auf Projekt-Ebene (und teils auf Dokument-Ebene) gesetzt werden. Sie können aus einer Bibliothek vordefinierter Preset-Templates gewählt oder manuell angepasst werden. Drei Standard-Presets decken die meisten Anwendungsfälle ab (siehe Abschnitt 7).

**Im Item-Level-Workflow (neu in Runde 4):** Configurable Rigor erstreckt sich auch auf die Status-Workflows einzelner Items. Was bisher ein fest verdrahteter Status-Enum war (draft/approved/deprecated), wird zu einem konfigurierbaren Workflow pro Item-Typ — die Übergänge und Berechtigungen sind Teil des Presets. Details in Abschnitt 7a.

---

## 3. Zielgruppen und Terminologie-Layer

### 3.1 Dual-Zielgruppen-Strategie

ReqFlow bedient zwei gleichwertige Primärzielgruppen in v1. Diese Entscheidung ist bewusst: Beide Gruppen teilen dasselbe Kernproblem (strukturierter Anforderungskontext fehlt) und profitieren vom selben Lösungsansatz (generisches Artefakt-Datenmodell + MCP-Integration). Die Unterschiede in Terminologie und Prozesstiefe werden durch Configurable Rigor aufgelöst.

**Zielgruppe A — AI-first Software Teams**

Software-Teams, die bereits AI-Agenten (Claude Code, Cursor, GitHub Copilot) in ihrem Entwicklungsprozess einsetzen und einen strukturierten, maschinenlesbaren Anforderungskontext benötigen. Diese Teams denken in Epics, Stories und Acceptance Criteria, arbeiten agil und erwarten ein schlankes, schnelles Tool ohne Prozess-Overhead.

**Zielgruppe B — Systems Engineers (Embedded / Safety-Critical)**

Engineers in regulierten oder sicherheitskritischen Domänen, die formale Artefakt-Hierarchien, Traceability und strukturierte Anforderungszerlegung benötigen. Diese Teams denken in System Requirements, Functions und Verification Criteria, arbeiten mit Baselines und Approval-Workflows. Sie stecken heute zwischen zu einfachen Agile-Tools und zu schweren Enterprise-Lösungen (DOORS, Polarion).

Explizit nicht für ReqFlow v1:
- Teams ohne jegliche Requirements-Disziplin, die nur Issue-Tracking brauchen (Jira/Linear)
- Hochregulierte Programme mit Zertifizierungspflicht (ISO 26262 ASIL-D, DO-178C Level A) — v2+
- Primärer Fokus auf Dokument-Management (Confluence/SharePoint)

### 3.2 Gemeinsames generisches Artefakt-Datenmodell

Beide Zielgruppen arbeiten auf demselben Datenmodell. Es gibt keine parallelen Code-Pfade oder doppelten Entitäten. Die Unterschiede sind ausschließlich auf Präsentations- und Konfigurationsebene angesiedelt.

Die Kernentitäten des generischen Modells sind: Artifact (hierarchisch, beliebige Tiefe), Requirement (mit Typ, Status, Kategorie), ArchitectureElement (schreibbarer Artefakttyp, neu in Runde 4), TraceLink (Beziehungstypen: parent-child, derives-from, satisfies, verifies) und TestCase (verknüpft mit Requirements).

### 3.3 Konfigurierbare Terminologie-Layer

Über ein konfigurierbares Workspace-Setting wählt das Team sein Terminologie-Profil. Die Daten bleiben identisch — nur Labels und UI-Texte ändern sich. Das Terminologie-Mapping ist als JSON-Konfiguration im Workspace-Modell hinterlegt; die React-UI liest Labels aus dem aktiven Workspace-Profil. Kein Datenbank-Schema ändert sich beim Profilwechsel.

| Generische Entität | Dev-Modus (Software Teams) | SE-Modus (Systems Engineering) |
|---|---|---|
| Artifact (L1) | Epic | System Requirement |
| Artifact (L2) | Story | Function |
| Artifact (L3) | Task | Component |
| Requirement | Acceptance Criterion | Verification Criterion |
| TraceLink.verifies | Test covers Story | Test verifies Requirement |
| Status: draft | Draft | Draft |
| Status: approved | Done | Approved |

Die REST API und der MCP Server nutzen immer die generischen Entitätsnamen — unabhängig vom aktiven Terminologie-Profil. Exporte enthalten das aktive Profil als Metadatum.

Profilwechsel erfordern eine explizite Bestätigung mit dem Hinweis "Nur Labels ändern sich, keine Daten gehen verloren". Das aktive Profil ist persistent im Header der Anwendung angezeigt.

### 3.4 Traceability-Engine

Die Traceability-Engine ist für beide Zielgruppen identisch. TraceLinks sind universell modelliert. Upstream/Downstream-Queries, Impact-Analysen und Coverage-Reports funktionieren vollständig unabhängig vom aktiven Terminologie-Profil.

---

## 4. Funktionsumfang v1

### 4.1 Functional — Kernfunktionen

Das funktionale Herzstück von ReqFlow v1 bilden vier Bereiche:

**Artefakt-Hierarchie und Requirements CRUD:** Anforderungen werden in verschachtelten Artefakten verwaltet (beliebige Hierarchietiefe). Vollständiges CRUD für Requirements mit Kategorien (Functional, Non-Functional, API, UI/UX, Data, Integration, Test), konfigurierbarem Status-Workflow (Default: Draft, Approved, Deprecated) und optionaler Priorität.

**Traceability-Engine:** Verknüpfung von Requirements untereinander (parent-child, derives-from, satisfies) und mit Tests (verifies). Upstream/Downstream-Queries für Impact-Analysen. Coverage-Übersicht (welche Requirements haben mindestens einen Test).

**Baselines (ab Standard-Preset):** Unveränderliche, benannte Snapshots auf Dokument-, Projekt- und Global-Ebene (neu in Runde 4: drei Baseline-Ebenen). Ermöglicht Vergleich zwischen Ständen. Baselines sind ein Must-Have für Systems Engineers.

**Testmanagement:** Testfälle anlegen, mit Requirements verknüpfen, Test-Status verwalten (Passed / Failed / Not Run). Test-Suiten als Gruppierung.

Volltextsuche über alle Requirements und Artefakte ist ebenfalls Teil von v1.

### 4.2 Non-Functional — Qualitätsanforderungen

API-Antwortzeiten unter 200ms für Standard-Queries bei bis zu 10.000 Requirements. Rollenbasierte Zugriffskontrolle (Admin, Editor, Viewer, Approver). Transaktionale Konsistenz ohne Datenverluste. Vollständige Auditierbarkeit aller Änderungen (Wer, Wann, Was).

### 4.3 API

Vollständige REST API mit CRUD-Unterstützung für alle Entitäten, Token-basierter Authentifizierung (Bearer Token / API Keys) und maschinenlesbarer OpenAPI-Spezifikation. MCP Server mit erweitertem Tool-Set für Requirements, Architektur und Tests (siehe Abschnitt 6). Webhook-Support für Anforderungsänderungen ist als Should-Have für v1 vorgesehen.

### 4.4 UI/UX

Dashboard mit Übersicht über Projekte, Artefakte und offene Punkte. Requirements-Editor mit Inline-Editing und Markdown-Support. Artefakt-Navigation als Baumstruktur. Traceability-Anzeige mit verknüpften Requirements und Tests. Facettierte Such- und Filteroberfläche.

### 4.5 Data

Das Datenmodell ist im Detail in Abschnitt 5 beschrieben. Kern-Entitäten sind Artifact, Requirement, ArchitectureElement, TraceLink, TestCase, Baseline, WorkflowDefinition und Tenant.

### 4.6 Integration

Export in JSON und CSV für alle Entitäten (Must-Have). GitHub-Integration für das Verknüpfen von Anforderungen mit GitHub Issues und Pull Requests (Should-Have). PDF-Reports für Anforderungsdokumente und Traceability-Matrizen (Should-Have). Import aus CSV für Bulk-Import (Must-Have).

Explizit v2+: ReqIF-Import/Export, bidirektionale Jira-Synchronisation, SSO (SAML/OIDC).

### 4.7 Test

Testfälle erstellen und mit Requirements verknüpfen. Test-Status und Coverage-Übersicht. Test-Suiten. Coverage-Report als CSV/PDF. Automatisierte Test-Ergebnis-Ingestion aus pytest/JUnit ist als Could-Have eingestuft.

---

## 5. Datenmodell-Konzept

Das Datenmodell folgt dem Prinzip "reichhaltiges Fundament, konfigurierbare Sichtbarkeit". Alle Felder für Audit, Compliance und erweiterte Workflows sind von Beginn an vorhanden.

### 5.1 Kern-Entitäten (konzeptuelle Übersicht)

```
Tenant (1)
  └── Workspace (n)           -- Konfigurationseinheit (Terminologie-Profil, SE-Preset)
        ├── WorkflowDefinition (n)  -- Konfigurierbare Workflows pro Item-Typ
        ├── Artifact (n, hierarchisch, beliebige Tiefe)
        │     ├── Requirement (n)
        │     │     ├── TraceLink (n)    -- zu anderen Requirements oder TestCases
        │     │     └── WorkflowState   -- aktueller State im konfig. Workflow
        │     └── ArchitectureElement (n)  -- schreibbarer Artefakttyp
        │           └── TraceLink (n)
        └── Baseline (n, auf drei Ebenen: Dokument / Projekt / Global)
TestCase (n)
  └── TraceLink               -- Verknüpfung zu Requirements
```

### 5.2 Entitäten im Detail

**Tenant**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| name | String | Anzeigename |
| slug | String (unique) | URL-freundlicher Bezeichner |
| created_at | Timestamp | Erstellungszeitpunkt |

In v1 existiert genau ein Tenant ("default"). Das Feld ist Voraussetzung für spätere Multi-Tenancy-Aktivierung ohne Datenmigration.

**Workspace**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Zugehöriger Tenant |
| name | String | Projektname |
| terminology_profile | JSON | Aktives Terminologie-Preset (Dev/SE/Custom) |
| se_preset | Enum | Minimal / Standard / Extended |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |

**Artifact**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| workspace | FK → Workspace | Zugehöriger Workspace |
| parent | FK → Artifact (nullable) | Übergeordnetes Artefakt |
| title | String | Bezeichnung |
| description | Text | Beschreibung |
| artifact_type | String | Konfigurierbar (System / Subsystem / Component o.ä.) |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |
| modified_by | FK → User | Letzter Bearbeiter |
| modified_at | Timestamp | Letzter Änderungszeitpunkt |

**Requirement**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| artifact | FK → Artifact | Zugehöriges Artefakt |
| title | String | Kurzbezeichnung |
| description | Text | Vollständige Anforderungsbeschreibung (Markdown) |
| category | Enum | Functional / Non-Functional / API / UI-UX / Data / Integration / Test |
| priority | Enum | High / Medium / Low (nullable) |
| workflow_state | FK → WorkflowState | Aktueller State im konfigurierbaren Workflow (ersetzt status-Enum) |
| version | Integer (auto-increment) | Optimistic Locking, Basis für spätere Versionierung |
| change_reason | Text (optional) | Begründung für Änderung |
| tags | JSON-Array | Freitags für Filterung |
| created_by | FK → User | Autor-Nachweis |
| created_at | Timestamp | Erstellungszeitpunkt |
| modified_by | FK → User | Letzter Bearbeiter |
| modified_at | Timestamp | Letzter Änderungszeitpunkt |

Hinweis: Der bisherige `status`-Enum (draft/approved/deprecated) wird durch `workflow_state` ersetzt. Der Default-Workflow bildet denselben Lifecycle ab (Draft → Approved → Deprecated), ist aber nicht mehr hartcodiert — siehe Abschnitt 7a.

**ArchitectureElement (neu in Runde 4)**

Architektur-Elemente sind ein eigener, schreibbarer Artefakttyp im Datenmodell — nicht nur ein Tag auf Artifact. Damit können Architektur-Inhalte strukturiert verwaltet, mit Requirements verknüpft und via MCP von Agenten gelesen und geschrieben werden.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| workspace | FK → Workspace | Zugehöriger Workspace |
| artifact | FK → Artifact (nullable) | Zugehöriges Artefakt (optional) |
| title | String | Bezeichnung (z.B. "Authentication Service", "Database Layer") |
| description | Text | Beschreibung (Markdown) |
| element_type | Enum | Component / Interface / Subsystem / Layer / Module |
| workflow_state | FK → WorkflowState | Aktueller State im konfigurierbaren Workflow |
| version | Integer (auto-increment) | Versionierungsbasis |
| change_reason | Text (optional) | Begründung für Änderung |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |
| modified_by | FK → User | Letzter Bearbeiter |
| modified_at | Timestamp | Letzter Änderungszeitpunkt |

**TraceLink**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| source_requirement | FK → Requirement (nullable) | Quell-Anforderung |
| source_architecture | FK → ArchitectureElement (nullable) | Quell-Architektur-Element |
| target_requirement | FK → Requirement (nullable) | Ziel-Anforderung |
| target_test | FK → TestCase (nullable) | Ziel-Testfall |
| target_architecture | FK → ArchitectureElement (nullable) | Ziel-Architektur-Element |
| link_type | Enum | parent-child / derives-from / satisfies / verifies / implements / refines |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |

Constraint: Genau ein Source-Feld und genau ein Target-Feld müssen befüllt sein (DB-Constraint oder Anwendungslogik).

**TestCase**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| workspace | FK → Workspace | Zugehöriger Workspace |
| title | String | Bezeichnung |
| description | Text | Beschreibung / Testschritte |
| test_type | Enum | Unit / Integration / System / Acceptance |
| workflow_state | FK → WorkflowState | Aktueller State im konfigurierbaren Workflow |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |
| modified_by | FK → User | Letzter Bearbeiter |
| modified_at | Timestamp | Letzter Änderungszeitpunkt |

**Baseline (erweitert in Runde 4: drei Ebenen)**

Baselines können auf drei Scopes erstellt werden — alle nutzen dieselbe Entität, unterscheiden sich aber im `scope`-Feld und im Snapshot-Inhalt:

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| workspace | FK → Workspace (nullable) | Für Projekt- und Dokument-Scope |
| artifact | FK → Artifact (nullable) | Für Dokument-Scope |
| scope | Enum | global / project / document | Baseline-Ebene |
| name | String | Bezeichnung (z.B. "Sprint-3-Release", "CDR-Baseline", "System-v1.0") |
| snapshot | JSON | Unveränderlicher Snapshot: Item-IDs + Versionen für den jeweiligen Scope |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |
| description | Text (optional) | Kontext / Begründung |

Baselines sind nach der Erstellung unveränderlich. Änderungen an enthaltenen Items erzeugen eine neue Item-Version, die Baseline bleibt unberührt.

Scope-Semantik:
- `global`: Snapshot über ALLE Workspaces und Artefakte einer Tenant-Instanz. Workspace und Artifact sind null. Geeignet für systemweite Release-Stände.
- `project`: Snapshot über einen Workspace (alle Artefakte und Requirements innerhalb). Artifact ist null. Wie bisher für Projekt-Übergaben.
- `document`: Snapshot über ein einzelnes Artefakt und dessen Nachkommen. Feingranularster Scope.

Referenzierung: Jede Baseline hält im `snapshot`-JSON eine Liste aller betroffenen Item-IDs (Requirements, ArchitectureElements, TestCases) zusammen mit deren Version zum Zeitpunkt des Einfrierens. Damit kann jederzeit der exakte Stand rekonstruiert werden, auch wenn Items später verändert wurden.

**WorkflowDefinition und WorkflowState (neu in Runde 4)**

Konzept-Skizze — kein Code, nur Datenmodell-Konzept:

```
WorkflowDefinition
  id: UUID
  workspace: FK → Workspace
  item_type: Enum (requirement / architecture_element / test_case)
  name: String
  is_default: Boolean
  states: JSON-Array von WorkflowStateDefinition
  transitions: JSON-Array von WorkflowTransitionDefinition

WorkflowStateDefinition (eingebettet in WorkflowDefinition.states)
  key: String (z.B. "draft", "in_review", "approved", "deprecated")
  label: String (Anzeigename, mehrsprachig via i18n-Key)
  is_initial: Boolean
  is_terminal: Boolean

WorkflowTransitionDefinition (eingebettet in WorkflowDefinition.transitions)
  from_state: String (key)
  to_state: String (key)
  allowed_roles: Array<String> (z.B. ["editor", "approver"])
  requires_change_reason: Boolean

WorkflowState (Instanz, an Item gebunden)
  id: UUID
  item_type: String
  item_id: UUID
  current_state: String (key aus WorkflowDefinition)
  workflow_definition: FK → WorkflowDefinition
  history: JSON-Array von Transitions (from, to, by, at, change_reason)
```

Der Default-Workflow (Minimal-Preset) bildet den bisherigen Status-Enum ab: Draft → Approved → Deprecated, alle Übergänge für Editor erlaubt, kein Approval-Gate. Im Extended-Preset ist der Default-Workflow: Draft → In Review → Approved → Deprecated, mit dem Übergang In Review → Approved nur für die Rolle Approver.

### 5.3 Audit-Felder — Vollständige Übersicht

Folgende Audit-Felder sind auf allen relevanten Entitäten vorhanden:

| Feld | Entität | Zweck |
|---|---|---|
| created_by (FK → User) | Requirement, TraceLink, TestCase, Artifact, ArchitectureElement | Autor-Nachweis |
| created_at (Timestamp) | Requirement, TraceLink, TestCase, Artifact, ArchitectureElement | Erstellungszeitpunkt |
| modified_by (FK → User) | Requirement, Artifact, TestCase, ArchitectureElement | Letzter Bearbeiter |
| modified_at (Timestamp) | Requirement, Artifact, TestCase, ArchitectureElement | Letzter Änderungszeitpunkt |
| version (Integer, auto-increment) | Requirement, ArchitectureElement | Optimistic Locking + Versionierungsbasis |
| change_reason (Text, optional) | Requirement, ArchitectureElement | Begründung für Änderungen |
| workflow_state (FK → WorkflowState) | Requirement, ArchitectureElement, TestCase | Lifecycle-Steuerung (konfigurierbar) |
| WorkflowState.history (JSON) | WorkflowState | Audit-Trail aller State-Übergänge |

Diese Felder sind leichtgewichtig, erzeugen kaum Overhead und ermöglichen später formale Audit-Trails ohne Datenmigration.

### 5.4 Multi-Tenancy: Row-Level-Isolation

Alle Entitäten tragen ein `tenant`-Fremdschlüsselfeld. Alle Datenbankabfragen enthalten automatisch einen `tenant_id`-Filter, durchgesetzt über einen Custom Django Manager und Middleware, die den aktiven Tenant aus dem JWT/API-Key extrahiert.

In v1 existiert genau ein Tenant ("default"). Das Modell ist für Multi-Tenancy vorbereitet, ohne es aktiv zu betreiben. Vorteil: Die spätere Aktivierung echter Multi-Tenancy (für SaaS in v2) erfordert keine Datenmigration — nur das Anlegen weiterer Tenants und die Implementierung der Tenant-Auflösungslogik in der Middleware.

---

## 6. MCP-Server-Konzept

Der MCP Server ist eine gleichrangige Produktions-Schnittstelle neben der REST API — kein Anhängsel, kein Plugin. Er ermöglicht AI-Agenten vollständigen strukturierten Zugriff auf den gesamten Anforderungskontext — Requirements, Architektur und Tests.

### 6.1 Grundprinzipien

**Read + Write + Audit-Log:** Der MCP Server in v1 hat vollen Read- und Write-Access auf alle Artefakttypen. AI-Agenten können Requirements anlegen, Architektur-Elemente erstellen und verändern sowie Tests anlegen und verknüpfen. Jede schreibende MCP-Operation wird im Audit-Log erfasst (welcher Agent-Client, welcher API-Key, welche Operation, wann). Dies macht agentengesteuerte Änderungen vollständig nachvollziehbar.

**Generische Entitätsnamen:** Der MCP Server nutzt immer die generischen Entitätsnamen (Requirement, ArchitectureElement, TraceLink) — unabhängig vom aktiven Terminologie-Profil. AI-Agenten müssen das Profil nicht kennen.

**LLM als konfigurierbare Capability:** LLM-gestützte Features (Validierung, Decomposition, Konsistenz-Checks) sind pro Deployment konfigurierbar. Der LLM-Anbieter und API-Key sind pro Deployment einstellbar (Default: Claude, aktuelle Version). Deployments ohne LLM-Anbindung können einzelne LLM-Capabilities deaktivieren — der Rest des MCP Servers bleibt vollständig funktionsfähig.

### 6.2 MCP-Tool-Set v1 — Vollständige Liste

Das Tool-Set deckt alle drei Artefakttypen ab. Tool-übergreifende Suche via `artifact.search` deckt den häufigen Anwendungsfall ab, wenn Agenten nicht wissen, in welchem Artefakttyp eine Information liegt.

**Requirements-Tools**

| Tool | Signatur | Beschreibung |
|---|---|---|
| `requirement.get` | `(id)` | Einzelabruf einer Anforderung mit vollständigem Kontext (Traces, Tests, Workflow-History, Audit-History). Primärer Einstiegspunkt für Coding-Agenten vor der Implementierung. |
| `requirement.query` | `(filters)` | Suche und Filter mit Facetten (Artefakt, Workflow-State, Typ, Kategorie, Tags). Primärer Use Case: Test-Agent ermittelt Abdeckungslücken. |
| `requirement.create` | `(title, description, type, artifact_id, parent_id?)` | Neue Anforderung anlegen. Alle schreibenden Operationen werden im Audit-Log erfasst. |
| `requirement.update` | `(id, fields, change_reason?)` | Felder einer Anforderung aktualisieren. `change_reason` ist im Extended-Preset Pflichtfeld. |
| `requirement.decompose` | `(id, children[])` | Zerlegung einer Anforderung in Kind-Artefakte als Batch-Operation. Ermöglicht strukturierte SE-Zerlegung durch Agenten ohne N einzelne API-Calls. |
| `requirement.validate` | `(id)` | LLM-gestützte Qualitätsprüfung: Vollständigkeit, Eindeutigkeit und Testbarkeit einer Anforderung. Gibt strukturiertes Feedback (Score + Verbesserungsvorschläge). Optional deaktivierbar, LLM-Anbieter konfigurierbar (Bring-your-own-API-Key). |

**Architektur-Tools (neu in Runde 4)**

| Tool | Signatur | Beschreibung |
|---|---|---|
| `architecture.get` | `(id)` | Einzelabruf eines Architektur-Elements mit Kontext (verknüpfte Requirements, Traces, Workflow-State). |
| `architecture.query` | `(filters)` | Architektur-Elemente suchen und filtern (Typ, Workspace, Artefakt, Tags). Primärer Use Case: Agents ermitteln welche Komponenten eine Anforderung implementieren. |
| `architecture.create` | `(title, description, element_type, workspace_id, artifact_id?)` | Neues Architektur-Element anlegen. Schreibende Operation — wird im Audit-Log erfasst. |
| `architecture.update` | `(id, fields, change_reason?)` | Felder eines Architektur-Elements aktualisieren. |
| `architecture.link` | `(architecture_id, target_id, target_type, link_type)` | Architektur-Element mit Requirement, TestCase oder anderem Architektur-Element verknüpfen. |

**Test-Tools (erweitert in Runde 4)**

| Tool | Signatur | Beschreibung |
|---|---|---|
| `test.get` | `(id)` | Einzelabruf eines Testfalls mit vollständigem Kontext (verknüpfte Requirements, Workflow-State, Ausführungshistorie). |
| `test.query` | `(filters)` | Testfälle suchen und filtern (Status, Typ, verknüpfte Anforderungen, Workspace). Primärer Use Case: Coverage-Analyse über alle Tests. |
| `test.create` | `(title, type, linked_req_id?)` | Testfall anlegen und optional direkt mit einer Anforderung verknüpfen. |
| `test.update` | `(id, fields)` | Testfall-Felder aktualisieren (Status, Beschreibung, Typ). Ermöglicht Agenten den Test-Status nach Ausführung zu schreiben. |
| `test.link` | `(test_id, req_id)` | Nachträgliche Verknüpfung eines Testfalls mit einer Anforderung. |

**Übergreifende und Kontext-Tools**

| Tool | Signatur | Beschreibung |
|---|---|---|
| `traceability.query` | `(artifact_id, direction?)` | Upstream/Downstream Impact-Analyse. Gibt alle abhängigen Requirements, Tests, Architektur-Elemente und Artefakte zurück. Primärer Use Case: Blast-Radius-Analyse bei Änderungen. |
| `artifact.search` | `(query, types?, workspace_id?)` | Artefakttyp-übergreifende Volltextsuche über Requirements, ArchitectureElements und TestCases. Liefert gemischte Ergebnisliste mit Typ-Annotation. Primärer Use Case: Agenten, die nicht wissen, in welchem Artefakttyp eine Information liegt. |
| `artifact.get_tree` | `(root_id?)` | Gesamte Artefakt-Hierarchie abrufen (optional ab einem bestimmten Root-Knoten). Strukturüberblick für Agenten. |
| `workspace.get_context` | `()` | Workspace-Status abrufen: offene Requirements, unverknüpfte Tests, Coverage-Summary, aktives Terminologie-Profil, aktives SE-Preset, aktive WorkflowDefinitions. Orientierungspunkt für AI-Agenten beim Einstieg in eine Session. |

**Begründung Tool-Architektur:** Separate Tools pro Artefakttyp (statt generischer Wrapper-Tools) ermöglichen klare Signaturen und typsichere Validierung. `artifact.search` als übergreifendes Tool vermeidet, dass Agenten drei separate Query-Calls machen müssen, wenn der Artefakttyp unbekannt ist. Tool-übergreifende Operationen (Traceability, Tree) bleiben auf der Artefakt-Abstraktionsebene.

### 6.3 Primäre AI-Workflows

**Workflow 1 — Context-Aware Code Generation:** Ein Coding-Agent (z.B. Claude Code) ruft vor der Implementierung einer Komponente via `requirement.get` und `architecture.query` alle zugehörigen Requirements und Architektur-Vorgaben ab. Code-Generierung erfolgt mit vollständigem Kontext.

**Workflow 2 — Automated Test Coverage Analysis:** Ein Test-Agent scannt via `requirement.query` alle Requirements eines Artefakts, prüft die Coverage via `traceability.query` und legt Testfälle für Lücken via `test.create` an.

**Workflow 3 — Change Impact Analysis:** Bei einer Anforderungsänderung ruft ein Analyse-Agent via `traceability.query` alle abhängigen Requirements, Tests und Architektur-Elemente ab und erstellt einen Blast-Radius-Report.

**Workflow 4 — Requirements Elicitation:** Ein Elicitation-Agent führt strukturierte Interviews und schreibt Ergebnisse via `requirement.create` direkt als strukturierte Requirements in ReqFlow.

**Workflow 5 — Architecture-Requirements-Alignment:** Ein Architektur-Agent liest via `architecture.query` alle Architektur-Elemente, prüft via `traceability.query` ob alle Requirements durch Architektur-Elemente abgedeckt sind und legt fehlende Verknüpfungen via `architecture.link` an.

### 6.4 MCP-Zielclients v1

- Claude Code (Anthropic) — nativer MCP-Support, primärer Use Case
- Cursor — MCP-kompatibel, breite Developer-Adoption
- Dedizierte Requirements-Agenten und Orchestratoren (beliebige MCP-kompatible Clients)
- CI/CD-Agenten (z.B. GitHub Actions mit MCP-Tool-Runner)

---

## 7. SE-Tiefe-Stufen als Projekt-Presets

Die SE-Tiefe ist pro Projekt über drei Standard-Presets einstellbar. Ein Preset ist eine JSON-Konfiguration, die auf Workspace-Ebene gesetzt wird und Funktionsumfang, Pflichtfelder und Workflow-Regeln definiert.

### 7.1 Preset-Übersicht

| Merkmal | Minimal | Standard | Extended |
|---|---|---|---|
| **Zielgruppe** | AI-first Dev Teams, schnelle Iteration | Software Teams + SE-Einstieg | Systems Engineers, regulierte Umgebungen |
| **Artefakt-Hierarchie** | Ja | Ja | Ja |
| **Requirements CRUD** | Ja | Ja | Ja |
| **Traceability** | Ja | Ja | Ja |
| **Baselines** | Nein | Ja: Dokument + Projekt | Ja: Dokument + Projekt + Global |
| **Change-Tracking** | Nur Timestamps | Timestamps + change_reason optional | Timestamps + change_reason Pflichtfeld |
| **Item-Level-Workflow** | Default (Draft/Done) | Erweiterter Default (Draft/Approved/Deprecated) | Konfigurierbar mit Approval-Gate |
| **Approval-Workflow** | Nein | Nein | Ja (Approver-Rolle erforderlich für Approved-Transition) |
| **Workflow-Konfigurierbarkeit** | Fest (Default) | Teilweise konfigurierbar | Vollständig konfigurierbar per WorkflowDefinition |
| **Impact-Analyse-UI** | Nur via MCP | Nur via MCP | Vollständige UI-Visualisierung |
| **Compliance-Felder** | Ausgeblendet | Optional sichtbar | Aktiv und teils verpflichtend |
| **`change_reason` bei Update** | Optional | Optional | Pflichtfeld |

### 7.2 Preset: Minimal

Das Minimal-Preset ist für Teams gedacht, die schnell starten wollen ohne Prozess-Overhead. Artefakt-Hierarchie, Requirements CRUD und Traceability sind vorhanden. Keine Baselines, keine formalen Approval-Workflows. Der Item-Level-Workflow ist der Default (Draft/Done), nicht konfigurierbar im Minimal-Preset. Change-Tracking beschränkt sich auf automatische Timestamps.

Typischer Anwendungsfall: Ein Startup-Team will strukturierte Anforderungen verwalten und seinen AI-Agenten Kontext geben — ohne den Overhead eines formalen Requirements-Engineering-Prozesses.

### 7.3 Preset: Standard

Das Standard-Preset fügt Baselines auf Dokument- und Projekt-Ebene sowie erweitertes Change-Tracking hinzu. Baselines sind das kritische Feature für Systems Engineers — ohne Baselines ist ReqFlow für SE nicht ernsthaft nutzbar. Der Item-Level-Workflow ist der erweiterte Default (Draft/Approved/Deprecated), teilweise konfigurierbar. `change_reason` ist optional, aber im UI sichtbar und empfohlen.

Typischer Anwendungsfall: Ein Software-Team in einer regulierten Umgebung (z.B. Medizintechnik-Startup) braucht nachvollziehbare Anforderungsstände, aber noch keinen vollständigen Approval-Workflow.

### 7.4 Preset: Extended

Das Extended-Preset aktiviert zusätzlich den vollständig konfigurierbaren Item-Level-Workflow mit Approval-Gates, Global-Baselines und die Impact-Analyse-Visualisierung im UI.

**Konfigurierbarer Item-Level-Workflow:** WorkflowDefinitions können pro Item-Typ (Requirement, ArchitectureElement, TestCase) individuell definiert werden — States, Übergänge und erlaubte Rollen je Übergang. Approved-Items sind schreibgeschützt — Änderungen erfordern einen neuen Draft-Eintrag. Dies ist die Grundlage für spätere formale Compliance-Nachweise.

**Global-Baselines:** Systemweite Snapshots über alle Workspaces des Tenants — für Release-Freeze und formale Übergaben.

**Impact-Analyse-UI:** Wenn eine Anforderung geändert wird, visualisiert ReqFlow automatisch alle abhängigen Tests, Sub-Requirements und verknüpften Architektur-Elemente als Blast-Radius-Darstellung.

**`change_reason` als Pflichtfeld:** Bei jedem Update einer Anforderung oder eines Architektur-Elements ist eine Begründung verpflichtend einzutragen.

Typischer Anwendungsfall: Ein Automotive-Zulieferer oder Industrial-Automation-Team, das auf eine formale Compliance-Zertifizierung (z.B. IEC 61508) hinarbeitet und bereits jetzt audit-ready sein möchte.

---

## 7a. Item-Level-Workflow — Konzept (neu in Runde 4)

### Motivation

Einzelne Items (Requirements, Architektur-Elemente, Testfälle) durchlaufen in der Praxis je einen eigenen Lifecycle — und dieser Lifecycle ist je nach Projekt, Domäne und Compliance-Anforderung unterschiedlich. Der bisherige `status`-Enum (draft/approved/deprecated) war zu starr: er kodiert einen bestimmten Workflow fest, erlaubt keine domänenspezifischen Anpassungen und unterstützt keine rollengebundenen Übergänge.

Mit dem konfigurierbaren Item-Level-Workflow wird der Enum zum Default-Fall eines flexiblen Mechanismus — ohne Breaking-Change im Nutzungsverhalten.

### Kernkonzept

Jeder Item-Typ (Requirement, ArchitectureElement, TestCase) ist einer WorkflowDefinition zugeordnet. Eine WorkflowDefinition beschreibt:

1. **States**: Die möglichen Zustände eines Items (z.B. draft, in_review, approved, deprecated). States können als initial oder terminal markiert sein.
2. **Transitions**: Die erlaubten Übergänge zwischen States. Jede Transition definiert:
   - `from_state` und `to_state`
   - `allowed_roles`: Welche Benutzerrollen diesen Übergang auslösen dürfen
   - `requires_change_reason`: Ob eine Begründung Pflichtfeld ist
3. **Audit**: Jeder State-Übergang wird mit User, Zeitstempel und optionaler Begründung in `WorkflowState.history` protokolliert.

### Relationship zu Configurable Rigor

- **Minimal-Preset**: Default-Workflow, nicht konfigurierbar. States: Draft, Done. Übergänge: alle für Editor erlaubt.
- **Standard-Preset**: Erweiterter Default. States: Draft, Approved, Deprecated. Teilweise konfigurierbar (Anpassung der Labels via Terminologie-Profil).
- **Extended-Preset**: Vollständig konfigurierbar. WorkflowDefinitions per Item-Typ, Approval-Gate: nur Approver-Rolle darf den Übergang zu Approved auslösen.

### Konsequenz für den bisherigen status-Enum

Der `status`-Enum (draft/approved/deprecated aus Runden 1–3) wird nicht als hartcodiertes Feld in der Datenbank belassen. Stattdessen wird `workflow_state` (FK → WorkflowState) die Lifecycle-Steuerung übernehmen. Die bisherigen Enum-Werte werden zum Default-Workflow und bleiben API-kompatibel: MCP-Tools und REST API können weiterhin `status: "draft"` und `status: "approved"` als Filter-Parameter nutzen — intern werden sie auf WorkflowState-Keys gemappt.

### Rollen und Approval-Binding

Rollen in v1: Admin, Editor, Viewer, Approver (neu durch Item-Level-Workflow). Die Approver-Rolle wird nur im Extended-Preset aktiviert. Rollen werden pro Workspace vergeben.

Für Compliance-Szenarien (SE-Zielgruppe): Approval-gebundene Übergänge sind protokolliert (wer, wann, mit welcher Begründung) — das ist die Grundlage für spätere elektronische Signatur-Features (v2+).

### v1 vs. v2-Schnittlinie (Empfehlung)

**v1 (Kern des Item-Level-Workflows):**
- WorkflowDefinition-Entität im Datenmodell
- Default-Workflows für alle drei Presets als vordefinierte Konfigurationen
- Transition-Validierung (Rolle prüfen, change_reason prüfen)
- Audit-Trail der State-Übergänge in WorkflowState.history
- Approver-Rolle im Extended-Preset

**v2+ (Erweiterungen):**
- Vollständiger Workflow-Editor in der UI (grafischer State-Machine-Editor)
- Komplexe Approval-Matrizen (z.B. 2-of-3 Approver, delegierte Approvals)
- Elektronische Signaturen auf State-Übergänge (IEC 61508 / ISO 26262)
- Zeitbasierte Eskalationen (z.B. "nach 5 Tagen in_review → Auto-Reminder")
- Workflow-Versionierung (Änderung an WorkflowDefinition ohne Verlust bestehender States)

---

## 8. Compliance-Roadmap

### 8.1 v1 — Audit-ready, nicht compliance-zertifiziert

ReqFlow v1 ist bewusst nicht auf eine spezifische Compliance-Norm ausgerichtet. Die Grundlage wird jedoch bereits in v1 gelegt:

- Vollständige Audit-Felder auf allen relevanten Entitäten (created_by/at, modified_by/at, version, change_reason, workflow_state)
- Unveränderliche Baselines auf drei Ebenen als Snapshot-Mechanismus
- Konfigurierbarer Approval-Workflow mit Audit-Trail (im Extended-Preset)
- Vollständige MCP-Audit-Logs für agentengesteuerte Änderungen

Diese Features machen ReqFlow v1 "audit-ready" — das System kann für interne Audits und Prozess-Reviews genutzt werden, ohne eine formale Norm-Zertifizierung anzustreben.

### 8.2 v2 — IEC 61508 als erste Compliance-Zielnorm

Die erste formale Compliance-Erweiterung zielt auf IEC 61508 (Funktionale Sicherheit elektrischer/elektronischer Systeme) als übergeordnete Norm. Die Begründung für diese Wahl:

IEC 61508 ist die Eltern-Norm für die relevantesten abgeleiteten Normen: ISO 26262 (Automotive Functional Safety), IEC 62061 (Maschinensicherheit) und EN 50128 (Bahntechnik). Wer die Anforderungen der IEC 61508 abdeckt, hat die Grundlage für alle diese abgeleiteten Normen und erschließt damit mehrere Märkte gleichzeitig.

DO-178C (Avionics) wurde bewusst nicht als erster Schritt gewählt: Die Norm erfordert eine Tool-Qualification (Zertifizierung des Werkzeugs selbst) mit sehr hohem Aufwand — zu aufwändig für eine Open-Source-Positionierung im Einstieg.

### 8.3 Compliance-Roadmap im Überblick

| Phase | Compliance-Scope |
|---|---|
| v1 | Audit-ready: Audit-Felder, Change-Tracking, Multi-Level-Baselines, konfigurierbarer Approval-Workflow (Extended) |
| v2 | IEC 61508: Norm-spezifische Anforderungsattribute, formale Verification-Matrizen, elektronische Signaturen |
| v3+ | ISO 26262 / IEC 62061 / EN 50128 (aufbauend auf IEC 61508-Grundlage) |

---

## 9. Architektur-Überblick

### 9.1 Tech-Stack

ReqFlow basiert auf einem bewusst konservativen, bewährten Stack:

- **Backend:** Python / Django + Django REST Framework
- **Frontend:** React + TypeScript
- **Datenbank:** PostgreSQL (via Django ORM)
- **Deployment:** Docker Compose (Self-Hosted)
- **Schnittstellen:** REST API + nativer MCP Server

Der Stack ist bekannt, gut dokumentiert, hat eine große Community und ist für die Zielgruppe (Developer-affine Teams) einfach zu betreiben. Kein Vendor-Lock-in durch proprietäre Cloud-Services.

### 9.2 Systemstruktur

```
ReqFlow
├── Backend (Django)
│   ├── REST API (Django REST Framework)
│   │   └── OpenAPI Spec (auto-generiert)
│   ├── MCP Server (nativer MCP-Protokoll-Handler)
│   │   ├── requirement.* Tools (6)
│   │   ├── architecture.* Tools (5)
│   │   ├── test.* Tools (5)
│   │   └── artifact.* / traceability.* / workspace.* Tools (4)
│   ├── Datenmodell (PostgreSQL via Django ORM)
│   │   ├── Tenant-Isolation (Row-Level, Custom Manager)
│   │   └── WorkflowEngine (WorkflowDefinition + WorkflowState)
│   └── Auth (Token-basiert, rollenbasierte Zugriffskontrolle inkl. Approver-Rolle)
└── Frontend (React + TypeScript)
    ├── Dashboard
    ├── Requirements-Editor (Inline, Markdown)
    ├── Architecture-Editor (neu in Runde 4)
    ├── Artefakt-Navigation (Baumstruktur)
    ├── Traceability-Anzeige
    └── Workspace-Profil-Konfiguration (Terminologie, SE-Preset, Workflow-Übersicht)
```

### 9.3 Wichtige Architektur-Entscheide

**MCP Server als eigenständige Schnittstelle:** Der MCP Server ist kein Wrapper über die REST API, sondern greift direkt auf die Django-Service-Schicht zu. Das vermeidet Overhead durch HTTP-Roundtrips und ermöglicht performante Batch-Operationen (z.B. `requirement.decompose`).

**Multi-Tenancy: Row-Level-Isolation:** Alle Entitäten tragen ein `tenant`-FK. Ein Custom Django Manager filtert automatisch nach dem aktiven Tenant. In v1 gibt es genau einen Default-Tenant. Schema-per-Tenant (django-tenants) und Database-per-Tenant wurden bewusst abgelehnt: zu hoher Overhead für ein Open-Source-Projekt mit Self-Hosted-Fokus.

**i18n: DE und EN in v1:** Django gettext für Backend-Strings, react-i18next für Frontend. Beide Sprachen (Deutsch, Englisch) sind in v1 enthalten. Die Entscheidung fiel für frühzeitige i18n-Integration, weil nachträgliche String-Extraktion aufwändiger ist als proaktive Translation-Key-Nutzung.

**Echtzeit-Kollaboration: v2:** v1 nutzt Standard-HTTP mit manuellem Refresh und optionalem Short-Polling für Dashboard-Updates. Keine WebSocket-Infrastruktur in v1. Requirements-Editing ist kein Google-Docs-Szenario — sequenzielle Änderungen überwiegen. Django Channels für Echtzeit-Kollaboration ist als v2-Feature vorgesehen.

**LLM-Anbindung: Konfigurierbar, optional, quer über Artefakttypen:** ReqFlow bindet LLMs als pluggable Capability ein — nicht nur für `requirement.validate`, sondern potenziell für alle Artefakttypen. Der Anbieter ist konfigurierbar (Default: Claude API), der API-Key wird pro Deployment hinterlegt (Bring-your-own-Key). Einzelne LLM-Capabilities können pro Deployment deaktiviert werden.

**WorkflowEngine: Leichtgewichtig in v1:** Die WorkflowEngine ist in v1 bewusst einfach gehalten — keine externe Workflow-Bibliothek, sondern eine eigene, schlanke Implementierung auf Basis von WorkflowDefinition-JSON und WorkflowState-Instanzen. Kein grafischer Workflow-Editor in v1.

---

## 10. Abgrenzung v1 vs. v2+

### 10.1 Scope v1

Die folgende Tabelle fasst zusammen, was in v1 enthalten ist und was nicht.

| Bereich | In v1 | Begründung |
|---|---|---|
| Artefakt-Hierarchie + Requirements CRUD | Ja | Kern des Produkts |
| Traceability-Engine | Ja | Kern des Produkts |
| MCP Server (Requirements + Architecture + Test Tools) | Ja | AI-nativer Differenzierungsvorteil |
| REST API + OpenAPI | Ja | Kern des Produkts |
| React-UI (Dashboard, Editor, Navigation) | Ja | Kern des Produkts |
| Docker Compose Deployment | Ja | Self-Hosted v1 |
| Workspace-Profile (Terminologie-Presets) | Ja | Dual-Zielgruppen-Strategie |
| SE-Presets (Minimal/Standard/Extended) | Ja | Configurable Rigor |
| ArchitectureElement-Entität + MCP-Tools | Ja | AI-nativ: MCP für alle Artefakttypen |
| Baselines (Dokument + Projekt) | Ja (ab Standard) | Must-Have für SE-Zielgruppe |
| Baselines (Global / Instanz-Ebene) | Ja (Extended) | Systemweite Release-Stände |
| Item-Level-Workflow (Default + Konfigurierbar) | Ja | Configurable Rigor, Kern der SE-Unterstützung |
| Approval-Workflow mit Approver-Rolle | Ja (Extended) | SE-Zielgruppe, Compliance-Vorbereitung |
| Audit-Trail der State-Übergänge | Ja | Compliance-Vorbereitung |
| Audit-Felder (created_by/at, version, etc.) | Ja | Compliance-Vorbereitung |
| Impact-Analyse-UI | Ja (Extended) | SE-Zielgruppe |
| LLM-Capabilities (konfigurierbar, optional) | Ja | AI-nativ: Dimension 1 |
| Multi-Tenancy-Vorbereitung (Row-Level) | Ja (Default-Tenant) | Vorbereitung für v2 SaaS |
| i18n DE + EN | Ja | Dual-Markt DE/EN |
| Export JSON/CSV | Ja | Grundfunktion |
| GitHub Integration | Should-Have v1 | Sinnvolle v1-Integration |

### 10.2 Explizit v2+

| Feature | Version | Begründung |
|---|---|---|
| SaaS / Managed Hosting | v2 | Infrastruktur-Aufwand, Multi-Tenancy aktiv |
| Echte Multi-Tenancy (mehrere aktive Tenants) | v2 | Benötigt Auth-/Billing-System |
| Echtzeit-Kollaboration (WebSockets/CRDT) | v2 | Erheblicher Architektur-Aufwand |
| MBSE / SysML-Elemente | v2+ | Anderes Metamodell, sprengt MVP |
| ReqIF-Import/Export | v2 | SE-Standard, aber nicht MVP-kritisch |
| Jira-Synchronisation (bidirektional) | v2 | Komplexe Sync-Logik |
| SSO (SAML/OIDC) | v2 | Enterprise-Feature |
| IEC 61508 Compliance-Features | v2 | Aufbauend auf v1-Audit-Grundlage |
| ISO 26262 / IEC 62061 / EN 50128 | v3+ | Aufbauend auf IEC 61508 |
| Horizontale Skalierung / Kubernetes | v2 | Enterprise-Deployment |
| Semantische Suche (Vektordatenbank) | v2 | ML-Infrastruktur |
| Grafischer Workflow-Editor (UI) | v2 | Nützlich, aber kein MVP-Blocker |
| Komplexe Approval-Matrizen (2-of-3) | v2 | Selten benötigt in v1-Zielgruppe |
| Elektronische Signaturen auf Übergänge | v2 | IEC 61508 / ISO 26262 Anforderung |
| Zeitbasierte Eskalationen im Workflow | v2 | Prozess-Automation, nicht MVP-kritisch |
| Workflow-Versionierung | v2 | Sicherheitsfeature bei Workflow-Änderungen |

---

## 11. Offene Punkte und Risiken

### 11.1 Hoch-Prioritäts-Punkte — zwingend in der Anforderungsaufnahme zu klären

Die folgenden drei Punkte beeinflussen direkt das Datenmodell, die API und die v1-Implementierung. Sie müssen vor dem Beginn der formalen Anforderungsaufnahme mit dem requirements-Agenten geklärt werden.

**[OFFEN — zwingend in der Anforderungsaufnahme (requirements-Phase) zu klären | Auswirkung auf Datenmodell/API]**

1. **LLM-Capabilities-Scope v1:** Welche der vier Capabilities (Generierung, Validierung, Decomposition, Test-Ableitung/Konsistenz-Checks) sind für v1 vorgesehen? Die Architektur soll alle vier als PLUGGABLE vorsehen, sodass die konkrete v1-Auswahl keine Architekturänderung erfordert — aber die operative Entscheidung (welche Capabilities werden tatsächlich im v1-MVP implementiert) muss vor API-Design getroffen werden. Empfehlung: Mit Validierung + Decomposition-Unterstützung starten; weitere Capabilities in v2.

2. **Preset-Downgrade-Semantik:** Was passiert mit Baselines, Approved-Items und Workflows beim Wechsel auf eine niedrigere SE-Stufe? Beispiel: Projekt im Extended-Preset mit Global-Baseline wechselt zu Standard — werden Global-Baselines gelöscht, eingefroren oder sichtbar gemacht? Werden Approved-Items auf Draft zurückgesetzt? Diese Semantik beeinflusst die Preset-Wechsel-Implementierung erheblich.

3. **Workflow-Wechsel-Semantik:** Was passiert mit Items in States, die nach einer WorkflowDefinition-Änderung nicht mehr existieren? Beispiel: Ein Projekt mit Custom-Workflow (States: draft, in_progress, approved) wechselt zu einem anderen Custom-Workflow (States: draft, ready_for_review, approved) — wie werden Items im State "in_progress" behandelt? Diese Entscheidung bestimmt die Fehlerbehandlung in der WorkflowEngine.

---

### 11.2 Bekannte offene Punkte (Mittel/Niedrig)

Die folgenden Punkte sind bekannt, erfordern aber weniger unmittelbare Klarheit für die Modellierung:

- **Audit-Log-Granularität:** Feld-Level (welches Feld wurde geändert) vs. Operation-Level (welches Tool, welche Parameter)?
- **Architecture-to-Architecture-Links:** Brauchen ArchitectureElemente Verknüpfungen zueinander? (z.B. "Layer A calls Layer B"). Falls ja: als TraceLink oder als eigenständige Entität?
- **Baseline-Scope-Granularität:** Kann eine Baseline mehrere Scopes kombinieren (z.B. "Projekt A + Dokument B") oder strikt ein Scope pro Baseline?
- **LLM-Provider-Konfig-Speicherort:** Workspace-Level, Tenant-Level oder Deployment-Level? (Beeinflusst Multi-Tenancy-Design)

---

### 11.3 Weitere Risiken und Mitigationen

**R1 — Terminologie-Verwirrung zwischen Profilen:** Das Dual-Profil-System (Dev-Modus / SE-Modus) kann Nutzer verwirren, wenn nicht klar kommuniziert wird, was sich beim Profilwechsel ändert (nur Labels) und was nicht (Daten, API). Mitigiert durch persistente Header-Anzeige des aktiven Profils und Bestätigungs-Dialog mit explizitem Hinweis.

**R2 — Scope-Creep durch zwei Zielgruppen:** "Beide gleichwertig" verleitet dazu, zielgruppen-spezifische Features sofort zu bauen. Gegenmaßnahme: Datenmodell ist generisch, UI-Anpassungen minimal (nur Labels und Default-Views). Neue Features werden strikt gegen die Preset-Matrix geprüft.

**R3 — MCP Write-Access-Risiko:** AI-Agenten können Requirements, Architektur-Elemente und Tests direkt schreiben. Unkontrollierte oder fehlerhafte Agenten-Änderungen sind möglich. Mitigiert durch vollständiges Audit-Log aller MCP-Schreiboperationen und rollen-basierte API-Key-Berechtigungen (Write-Permission optional deaktivierbar pro Workspace).

**R4 — LLM-Abhängigkeit bei AI-Capabilities:** Wenn LLM-Features aktiviert sind und der konfigurierte LLM-Anbieter nicht erreichbar ist, muss das System graceful degradieren. Alle LLM-gestützten Features müssen klar als optional markiert sein — das System bleibt ohne LLM vollständig funktionsfähig.

**R5 — i18n-Konsistenz:** Mit DE und EN von Beginn an muss sichergestellt werden, dass alle neuen UI-Strings in beiden Sprachen gepflegt werden. Empfehlung: Lint-Regel, die fehlende Translation-Keys als Build-Fehler behandelt.

**R6 — WorkflowEngine-Komplexität im Datenmodell:** Der Übergang vom hartcodierten Status-Enum zu einem konfigurierbaren Workflow-System erhöht die Datenmodell-Komplexität. Mitigierung: In v1 werden nur vordefinierte Workflow-Templates unterstützt (kein grafischer Editor, keine Custom-States via UI). WorkflowDefinitions sind JSON-Konfigurationen, die über Admin oder API gesetzt werden.

**R7 — Architektur-Artefakttyp: Scope-Abgrenzung:** Der neue ArchitectureElement-Typ muss klar vom Artifact-Typ abgegrenzt werden. Risiko: Nutzer sind unsicher, ob sie Architektur-Informationen als Artifact oder ArchitectureElement modellieren sollen. Mitigierung: Klare Dokumentation und UI-Hinweise; ArchitectureElement ist für strukturierte, versionierte Architektur-Beschreibungen, Artifact für Hierarchie-Gliederung.

**R8 — Global-Baseline-Semantik:** Eine Baseline über alle Workspaces kann sehr groß werden und komplexe Snapshot-Semantik erfordern. Risiko: Performance-Probleme bei großen Instanzen. Mitigierung: Global-Baselines nur im Extended-Preset; Snapshot ist asynchron berechenbar; in v1 auf Instanzen bis 10.000 Items beschränkt.

---

## Anhang A: Entscheidungshistorie

| Runde | Thema | Entscheidung |
|---|---|---|
| 1 | Zielgruppe | Beide gleichwertig (AI-first Teams + Systems Engineers); gemeinsames Datenmodell + Terminologie-Presets |
| 1 | Lizenz | Open Source Apache 2.0; Monetarisierung via Managed Hosting/Support |
| 1 | Deployment | Self-Hosted only v1 (Docker Compose); SaaS v2+ |
| 2 | MCP Write-Scope | Full Read+Write mit Audit-Log |
| 2 | requirement.validate | In v1 als optionales, konfigurierbares Feature mit Bring-your-own-API-Key |
| 2 | SE-Preset-Tiefe | Drei Presets: Minimal / Standard / Extended; Baselines Must-Have ab Standard |
| 2 | Compliance-Zielnorm | IEC 61508 als erste Zielnorm (v2) |
| 2 | Multi-Tenancy | Row-Level (tenant_id FK), Default-Tenant in v1 |
| 2 | i18n | In v1 (Django gettext + react-i18next, DE + EN) |
| 2 | Echtzeit-Kollaboration | v2 (v1: HTTP-Polling/Refresh) |
| 4 | AI-nativ Definition | Zwei Dimensionen: LLM als pluggable Capability quer über alle Artefakttypen + MCP für alle Artefakttypen |
| 4 | ArchitectureElement | Eigener, schreibbarer Artefakttyp im Datenmodell und in der MCP-Tool-Liste |
| 4 | MCP-Tool-Set | Erweitert auf architecture.* (5 Tools) und test.* (5 Tools); artifact.search als übergreifendes Tool |
| 4 | Baselining | Drei Ebenen: Global (Instanz) / Projekt / Dokument; Global nur im Extended-Preset |
| 4 | Item-Level-Workflow | Konfigurierbarer Workflow per Item-Typ ersetzt hartcodierten status-Enum; Default-Workflows per Preset |
| 4 | v1/v2-Schnittlinie (Workflow) | WorkflowEngine + Approver-Rolle in v1; Grafischer Editor, komplexe Matrizen, e-Signaturen in v2 |

---

*Finalisiert durch ideation-Agenten (ReqFlow) — Ideation-Runde 4 | 2026-06-17*
*Nächster Schritt: Übergabe an requirements-Agenten für formale Anforderungsaufnahme*
