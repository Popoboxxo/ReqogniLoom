# ReqFlow — Konzept-Dokument

> Status: FINAL — Runden 1, 2 und 3 abgeschlossen | Letzte Aktualisierung: 2026-06-17
>
> Dieses Dokument konsolidiert alle Entscheidungen aus den Ideation-Runden 1–3 und dient
> als vollständige Konzeptgrundlage für die formale Anforderungsaufnahme (requirements-Agent).
> Basis: VISION.md + KONZEPT.md Runden 1 & 2 (Commit c1c17f8)

---

## 1. Executive Summary — Was ist ReqFlow und warum existiert es?

ReqFlow ist das erste Requirements-Management-Tool, das AI-Agenten als native Prozess-Teilnehmer behandelt — nicht als Texthelfer oder nachträgliches Add-on, sondern als vollständige, strukturierte Schnittstelle für den gesamten Anforderungslebenszyklus.

### Das Problem

Softwareteams und Systems Engineers teilen 2026 ein gemeinsames, wachsendes Problem: AI-Agenten sind längst keine isolierten Assistenten mehr. Sie generieren Code, schreiben Tests, führen Reviews durch und orchestrieren Workflows. Doch ihnen fehlt der strukturierte, maschinenlesbare Zugriff auf das *Warum* hinter dem Code: auf Anforderungen, Akzeptanzkriterien, Testabdeckung und Traceability. Die Folge ist, dass AI-generierter Code oft am Kontext vorbeigeht — weil der Kontext nirgends maschinenlesbar vorliegt.

Gleichzeitig stecken viele Teams zwischen zwei unbefriedigenden Polen: Agile-Tools wie Jira oder Linear sind zu leichtgewichtig für echtes Requirements Engineering. Enterprise-Systeme wie IBM DOORS, Siemens Polarion oder PTC Codebeamer sind zu schwer, zu teuer und haben keinen AI-nativen Ansatz. Der Mittelweg fehlt.

### Die Lösung

ReqFlow schließt diese Lücke durch drei strategische Entscheidungen:

Erstens bietet ReqFlow einen nativen MCP Server (Model Context Protocol) als gleichrangige Schnittstelle neben der REST API. AI-Agenten können damit direkt und strukturiert Anforderungen abrufen, anlegen, verändern und in Beziehung setzen — ohne Umwege über Text-Parsing oder Webhook-Wrapper.

Zweitens skaliert ReqFlow über ein gemeinsames generisches Artefakt-Datenmodell von einfachem Anforderungsmanagement bis zu vollwertigen Systems-Engineering-Strukturen. Die Tiefe der Nutzung ist über konfigurierbare Projekt-Presets einstellbar, nicht global hart verdrahtet.

Drittens ist ReqFlow vollständig Open Source (Apache 2.0) mit Self-Hosted-Deployment via Docker Compose — ohne Vendor-Lock-in, ohne Lizenzkosten, mit maximaler Kontrolle über Daten und Infrastruktur.

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

Die Kernentitäten des generischen Modells sind: Artifact (hierarchisch, beliebige Tiefe), Requirement (mit Typ, Status, Kategorie), TraceLink (Beziehungstypen: parent-child, derives-from, satisfies, verifies) und TestCase (verknüpft mit Requirements).

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

**Artefakt-Hierarchie und Requirements CRUD:** Anforderungen werden in verschachtelten Artefakten verwaltet (beliebige Hierarchietiefe). Vollständiges CRUD für Requirements mit Kategorien (Functional, Non-Functional, API, UI/UX, Data, Integration, Test), Status-Lifecycle (Draft, Approved, Deprecated) und optionaler Priorität.

**Traceability-Engine:** Verknüpfung von Requirements untereinander (parent-child, derives-from, satisfies) und mit Tests (verifies). Upstream/Downstream-Queries für Impact-Analysen. Coverage-Übersicht (welche Requirements haben mindestens einen Test).

**Baselines (ab Standard-Preset):** Unveränderliche, benannte Snapshots einer Anforderungsmenge zu einem Zeitpunkt (z.B. "Sprint-3-Release", "CDR-Baseline"). Ermöglicht Vergleich zwischen Ständen. Baselines sind ein Must-Have für Systems Engineers.

**Testmanagement:** Testfälle anlegen, mit Requirements verknüpfen, Test-Status verwalten (Passed / Failed / Not Run). Test-Suiten als Gruppierung.

Volltextsuche über alle Requirements und Artefakte ist ebenfalls Teil von v1.

### 4.2 Non-Functional — Qualitätsanforderungen

API-Antwortzeiten unter 200ms für Standard-Queries bei bis zu 10.000 Requirements. Rollenbasierte Zugriffskontrolle (Admin, Editor, Viewer). Transaktionale Konsistenz ohne Datenverluste. Vollständige Auditierbarkeit aller Änderungen (Wer, Wann, Was).

### 4.3 API

Vollständige REST API mit CRUD-Unterstützung für alle Entitäten, Token-basierter Authentifizierung (Bearer Token / API Keys) und maschinenlesbarer OpenAPI-Spezifikation. MCP Server mit 11 Tools (siehe Abschnitt 6). Webhook-Support für Anforderungsänderungen ist als Should-Have für v1 vorgesehen.

### 4.4 UI/UX

Dashboard mit Übersicht über Projekte, Artefakte und offene Punkte. Requirements-Editor mit Inline-Editing und Markdown-Support. Artefakt-Navigation als Baumstruktur. Traceability-Anzeige mit verknüpften Requirements und Tests. Facettierte Such- und Filteroberfläche.

### 4.5 Data

Das Datenmodell ist im Detail in Abschnitt 5 beschrieben. Kern-Entitäten sind Artifact, Requirement, TraceLink, TestCase, Baseline und Tenant.

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
        └── Artifact (n, hierarchisch, beliebige Tiefe)
              └── Requirement (n)
                    ├── TraceLink (n)    -- zu anderen Requirements oder TestCases
                    └── Baseline (n)    -- Snapshots der Anforderungsmenge
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
| status | Enum | draft / approved / deprecated |
| version | Integer (auto-increment) | Optimistic Locking, Basis für spätere Versionierung |
| change_reason | Text (optional) | Begründung für Änderung |
| tags | JSON-Array | Freitags für Filterung |
| created_by | FK → User | Autor-Nachweis |
| created_at | Timestamp | Erstellungszeitpunkt |
| modified_by | FK → User | Letzter Bearbeiter |
| modified_at | Timestamp | Letzter Änderungszeitpunkt |

**TraceLink**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| source | FK → Requirement | Quelle |
| target_requirement | FK → Requirement (nullable) | Ziel-Anforderung |
| target_test | FK → TestCase (nullable) | Ziel-Testfall |
| link_type | Enum | parent-child / derives-from / satisfies / verifies |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |

**TestCase**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| workspace | FK → Workspace | Zugehöriger Workspace |
| title | String | Bezeichnung |
| description | Text | Beschreibung / Testschritte |
| test_type | Enum | Unit / Integration / System / Acceptance |
| status | Enum | not_run / passed / failed / skipped |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |
| modified_by | FK → User | Letzter Bearbeiter |
| modified_at | Timestamp | Letzter Änderungszeitpunkt |

**Baseline**

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID | Primärschlüssel |
| tenant | FK → Tenant | Tenant-Isolation |
| workspace | FK → Workspace | Zugehöriger Workspace |
| name | String | Bezeichnung (z.B. "Sprint-3-Release") |
| snapshot | JSON | Unveränderlicher Snapshot aller Requirement-IDs + Versionen |
| created_by | FK → User | Ersteller |
| created_at | Timestamp | Erstellungszeitpunkt |
| description | Text (optional) | Kontext / Begründung |

Baselines sind nach der Erstellung unveränderlich. Änderungen an enthaltenen Requirements erzeugen eine neue Requirement-Version, die Baseline bleibt unberührt.

### 5.3 Audit-Felder — Vollständige Übersicht

Folgende Audit-Felder sind auf allen relevanten Entitäten vorhanden:

| Feld | Entität | Zweck |
|---|---|---|
| created_by (FK → User) | Requirement, TraceLink, TestCase, Artifact | Autor-Nachweis |
| created_at (Timestamp) | Requirement, TraceLink, TestCase, Artifact | Erstellungszeitpunkt |
| modified_by (FK → User) | Requirement, Artifact, TestCase | Letzter Bearbeiter |
| modified_at (Timestamp) | Requirement, Artifact, TestCase | Letzter Änderungszeitpunkt |
| version (Integer, auto-increment) | Requirement | Optimistic Locking + Versionierungsbasis |
| change_reason (Text, optional) | Requirement | Begründung für Änderungen |
| status (Enum: draft/approved/deprecated) | Requirement | Lifecycle-Steuerung |

Diese Felder sind leichtgewichtig, erzeugen kaum Overhead und ermöglichen später formale Audit-Trails ohne Datenmigration.

### 5.4 Multi-Tenancy: Row-Level-Isolation

Alle Entitäten tragen ein `tenant`-Fremdschlüsselfeld. Alle Datenbankabfragen enthalten automatisch einen `tenant_id`-Filter, durchgesetzt über einen Custom Django Manager und Middleware, die den aktiven Tenant aus dem JWT/API-Key extrahiert.

In v1 existiert genau ein Tenant ("default"). Das Modell ist für Multi-Tenancy vorbereitet, ohne es aktiv zu betreiben. Vorteil: Die spätere Aktivierung echter Multi-Tenancy (für SaaS in v2) erfordert keine Datenmigration — nur das Anlegen weiterer Tenants und die Implementierung der Tenant-Auflösungslogik in der Middleware.

---

## 6. MCP-Server-Konzept

Der MCP Server ist eine gleichrangige Produktions-Schnittstelle neben der REST API — kein Anhängsel, kein Plugin. Er ermöglicht AI-Agenten vollständigen strukturierten Zugriff auf den Anforderungskontext.

### 6.1 Grundprinzipien

**Read + Write + Audit-Log:** Der MCP Server in v1 hat vollen Read- und Write-Access. AI-Agenten können Requirements anlegen, ändern und zerlegen. Jede schreibende MCP-Operation wird im Audit-Log erfasst (welcher Agent-Client, welcher API-Key, welche Operation, wann). Dies macht agentengesteuerte Änderungen vollständig nachvollziehbar.

**Generische Entitätsnamen:** Der MCP Server nutzt immer die generischen Entitätsnamen (Requirement, Artifact, TraceLink) — unabhängig vom aktiven Terminologie-Profil. AI-Agenten müssen das Profil nicht kennen.

**Konfigurierbare LLM-Anbindung (requirement.validate):** Das Tool `requirement.validate` ruft intern ein konfigurierbares LLM an. Der LLM-Anbieter und API-Key sind pro Deployment konfigurierbar (Default-Empfehlung: Claude, aktuelle Version). Deployments ohne LLM-Anbindung können `requirement.validate` deaktivieren. Das Feature ist optional und nicht kritisch für den Kern-Workflow.

### 6.2 MCP-Tool-Set v1 (11 Tools)

| Tool | Signatur | Beschreibung |
|---|---|---|
| `requirement.get` | `(id)` | Einzelabruf einer Anforderung mit vollständigem Kontext (Traces, Tests, Audit-History). Primärer Einstiegspunkt für Coding-Agenten vor der Implementierung. |
| `requirement.query` | `(filters)` | Suche und Filter mit Facetten (Artefakt, Status, Typ, Kategorie, Tags). Primärer Use Case: Test-Agent ermittelt Abdeckungslücken. |
| `requirement.create` | `(title, description, type, artifact_id, parent_id?)` | Neue Anforderung anlegen. Alle schreibenden Operationen werden im Audit-Log erfasst. |
| `requirement.update` | `(id, fields, change_reason?)` | Felder einer Anforderung aktualisieren. `change_reason` ist im Extended-Preset Pflichtfeld. |
| `requirement.decompose` | `(id, children[])` | Zerlegung einer Anforderung in Kind-Artefakte als Batch-Operation. Ermöglicht strukturierte SE-Zerlegung durch Agenten ohne N einzelne API-Calls. |
| `requirement.validate` | `(id)` | LLM-gestützte Qualitätsprüfung: Vollständigkeit, Eindeutigkeit und Testbarkeit einer Anforderung. Gibt strukturiertes Feedback (Score + Verbesserungsvorschläge). Optional deaktivierbar, LLM-Anbieter konfigurierbar (Bring-your-own-API-Key). |
| `traceability.query` | `(artifact_id, direction?)` | Upstream/Downstream Impact-Analyse. Gibt alle abhängigen Requirements, Tests und Artefakte zurück. Primärer Use Case: Blast-Radius-Analyse bei Änderungen. |
| `test.create` | `(title, type, linked_req_id?)` | Testfall anlegen und optional direkt mit einer Anforderung verknüpfen. |
| `test.link` | `(test_id, req_id)` | Nachträgliche Verknüpfung eines Testfalls mit einer Anforderung. |
| `workspace.get_context` | `()` | Workspace-Status abrufen: offene Requirements, unverknüpfte Tests, Coverage-Summary, aktives Terminologie-Profil, aktives SE-Preset. Orientierungspunkt für AI-Agenten beim Einstieg in eine Session. |
| `artifact.get_tree` | `(root_id?)` | Gesamte Artefakt-Hierarchie abrufen (optional ab einem bestimmten Root-Knoten). Strukturüberblick für Agenten. |

### 6.3 Primäre AI-Workflows

**Workflow 1 — Context-Aware Code Generation:** Ein Coding-Agent (z.B. Claude Code) ruft vor der Implementierung einer Komponente via `requirement.get` und `requirement.query` alle zugehörigen Requirements ab. Code-Generierung erfolgt mit vollständigem Anforderungskontext.

**Workflow 2 — Automated Test Coverage Analysis:** Ein Test-Agent scannt via `requirement.query` alle Requirements eines Artefakts, prüft die Coverage via `traceability.query` und legt Testfälle für Lücken via `test.create` an.

**Workflow 3 — Change Impact Analysis:** Bei einer Anforderungsänderung ruft ein Analyse-Agent via `traceability.query` alle abhängigen Requirements, Tests und Artefakte ab und erstellt einen Blast-Radius-Report.

**Workflow 4 — Requirements Elicitation:** Ein Elicitation-Agent führt strukturierte Interviews und schreibt Ergebnisse via `requirement.create` direkt als strukturierte Requirements in ReqFlow.

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
| **Baselines** | Nein | Ja (Must-Have) | Ja |
| **Change-Tracking** | Nur Timestamps | Timestamps + change_reason optional | Timestamps + change_reason Pflichtfeld |
| **Status-Lifecycle** | draft / done | draft / approved / deprecated | draft / in_review / approved / deprecated |
| **Approval-Workflow** | Nein | Nein | Ja (Editor schreibt, Approver bestätigt) |
| **Impact-Analyse-UI** | Nur via MCP | Nur via MCP | Vollständige UI-Visualisierung |
| **Compliance-Felder** | Ausgeblendet | Optional sichtbar | Aktiv und teils verpflichtend |
| **`change_reason` bei Update** | Optional | Optional | Pflichtfeld |

### 7.2 Preset: Minimal

Das Minimal-Preset ist für Teams gedacht, die schnell starten wollen ohne Prozess-Overhead. Artefakt-Hierarchie, Requirements CRUD und Traceability sind vorhanden. Keine Baselines, keine formalen Approval-Workflows. Der Status-Lifecycle ist vereinfacht (draft/done). Change-Tracking beschränkt sich auf automatische Timestamps.

Typischer Anwendungsfall: Ein Startup-Team will strukturierte Anforderungen verwalten und seinen AI-Agenten Kontext geben — ohne den Overhead eines formalen Requirements-Engineering-Prozesses.

### 7.3 Preset: Standard

Das Standard-Preset fügt Baselines und erweitertes Change-Tracking hinzu. Baselines sind das kritische Feature für Systems Engineers — ohne Baselines ist ReqFlow für SE nicht ernsthaft nutzbar. Der Status-Lifecycle ist vollständig (draft / approved / deprecated). `change_reason` ist optional, aber im UI sichtbar und empfohlen.

Baselines sind unveränderliche, benannte Snapshots einer Anforderungsmenge. Sie ermöglichen Vergleiche zwischen Ständen, sind Voraussetzung für formale Reviews und bilden die Grundlage für spätere Compliance-Workflows.

Typischer Anwendungsfall: Ein Software-Team in einer regulierten Umgebung (z.B. Medizintechnik-Startup) braucht nachvollziehbare Anforderungsstände, aber noch keinen vollständigen Approval-Workflow.

### 7.4 Preset: Extended

Das Extended-Preset aktiviert zusätzlich den vollständigen Approval-Workflow und die Impact-Analyse-Visualisierung im UI.

**Approval-Workflow:** Requirements durchlaufen den Lifecycle Draft → In Review → Approved → Deprecated. Rollen: Editor (schreibt und stellt zur Review), Approver (genehmigt oder lehnt ab). Approved Requirements sind schreibgeschützt — Änderungen erfordern eine neue Draft-Version. Dies ist die Grundlage für spätere formale Compliance-Nachweise.

**Impact-Analyse-UI:** Wenn eine Anforderung geändert wird, visualisiert ReqFlow automatisch alle abhängigen Tests, Sub-Requirements und verknüpften Artefakte als Blast-Radius-Darstellung. Dies ist der UI-Gegenstück zur `traceability.query`-API — dieselben Daten, aber als interaktive Visualisierung.

**`change_reason` als Pflichtfeld:** Bei jedem Update einer Anforderung ist eine Begründung verpflichtend einzutragen.

Typischer Anwendungsfall: Ein Automotive-Zulieferer oder Industrial-Automation-Team, das auf eine formale Compliance-Zertifizierung (z.B. IEC 61508) hinarbeitet und bereits jetzt audit-ready sein möchte.

---

## 8. Compliance-Roadmap

### 8.1 v1 — Audit-ready, nicht compliance-zertifiziert

ReqFlow v1 ist bewusst nicht auf eine spezifische Compliance-Norm ausgerichtet. Die Grundlage wird jedoch bereits in v1 gelegt:

- Vollständige Audit-Felder auf allen relevanten Entitäten (created_by/at, modified_by/at, version, change_reason, status)
- Unveränderliche Baselines als Snapshot-Mechanismus
- Approval-Workflow (im Extended-Preset)
- Vollständige MCP-Audit-Logs für agentengesteuerte Änderungen

Diese Features machen ReqFlow v1 "audit-ready" — das System kann für interne Audits und Prozess-Reviews genutzt werden, ohne eine formale Norm-Zertifizierung anzustreben.

### 8.2 v2 — IEC 61508 als erste Compliance-Zielnorm

Die erste formale Compliance-Erweiterung zielt auf IEC 61508 (Funktionale Sicherheit elektrischer/elektronischer Systeme) als übergeordnete Norm. Die Begründung für diese Wahl:

IEC 61508 ist die Eltern-Norm für die relevantesten abgeleiteten Normen: ISO 26262 (Automotive Functional Safety), IEC 62061 (Maschinensicherheit) und EN 50128 (Bahntechnik). Wer die Anforderungen der IEC 61508 abdeckt, hat die Grundlage für alle diese abgeleiteten Normen und erschließt damit mehrere Märkte gleichzeitig.

DO-178C (Avionics) wurde bewusst nicht als erster Schritt gewählt: Die Norm erfordert eine Tool-Qualification (Zertifizierung des Werkzeugs selbst) mit sehr hohem Aufwand — zu aufwändig für eine Open-Source-Positionierung im Einstieg.

### 8.3 Compliance-Roadmap im Überblick

| Phase | Compliance-Scope |
|---|---|
| v1 | Audit-ready: Audit-Felder, Change-Tracking, Baselines, Approval-Workflow (Extended) |
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
│   │   └── 11 Tools (requirement.*, traceability.*, test.*, workspace.*, artifact.*)
│   ├── Datenmodell (PostgreSQL via Django ORM)
│   │   └── Tenant-Isolation (Row-Level, Custom Manager)
│   └── Auth (Token-basiert, rollenbasierte Zugriffskontrolle)
└── Frontend (React + TypeScript)
    ├── Dashboard
    ├── Requirements-Editor (Inline, Markdown)
    ├── Artefakt-Navigation (Baumstruktur)
    ├── Traceability-Anzeige
    └── Workspace-Profil-Konfiguration (Terminologie, SE-Preset)
```

### 9.3 Wichtige Architektur-Entscheide

**MCP Server als eigenständige Schnittstelle:** Der MCP Server ist kein Wrapper über die REST API, sondern greift direkt auf die Django-Service-Schicht zu. Das vermeidet Overhead durch HTTP-Roundtrips und ermöglicht performante Batch-Operationen (z.B. `requirement.decompose`).

**Multi-Tenancy: Row-Level-Isolation:** Alle Entitäten tragen ein `tenant`-FK. Ein Custom Django Manager filtert automatisch nach dem aktiven Tenant. In v1 gibt es genau einen Default-Tenant. Schema-per-Tenant (django-tenants) und Database-per-Tenant wurden bewusst abgelehnt: zu hoher Overhead für ein Open-Source-Projekt mit Self-Hosted-Fokus.

**i18n: DE und EN in v1:** Django gettext für Backend-Strings, react-i18next für Frontend. Beide Sprachen (Deutsch, Englisch) sind in v1 enthalten. Die Entscheidung fiel für frühzeitige i18n-Integration, weil nachträgliche String-Extraktion aufwändiger ist als proaktive Translation-Key-Nutzung.

**Echtzeit-Kollaboration: v2:** v1 nutzt Standard-HTTP mit manuellem Refresh und optionalem Short-Polling für Dashboard-Updates. Keine WebSocket-Infrastruktur in v1. Requirements-Editing ist kein Google-Docs-Szenario — sequenzielle Änderungen überwiegen. Django Channels für Echtzeit-Kollaboration ist als v2-Feature vorgesehen.

**LLM-Anbindung: Konfigurierbar, optional:** ReqFlow ruft in v1 LLMs nur für `requirement.validate` auf. Der Anbieter ist konfigurierbar (Default: Claude API), der API-Key wird pro Deployment hinterlegt (Bring-your-own-Key). Deployments ohne LLM-Zugang können das Feature deaktivieren.

---

## 10. Abgrenzung v1 vs. v2+

### 10.1 Scope v1

Die folgende Tabelle fasst zusammen, was in v1 enthalten ist und was nicht.

| Bereich | In v1 | Begründung |
|---|---|---|
| Artefakt-Hierarchie + Requirements CRUD | Ja | Kern des Produkts |
| Traceability-Engine | Ja | Kern des Produkts |
| MCP Server (11 Tools) | Ja | AI-nativer Differenzierungsvorteil |
| REST API + OpenAPI | Ja | Kern des Produkts |
| React-UI (Dashboard, Editor, Navigation) | Ja | Kern des Produkts |
| Docker Compose Deployment | Ja | Self-Hosted v1 |
| Workspace-Profile (Terminologie-Presets) | Ja | Dual-Zielgruppen-Strategie |
| SE-Presets (Minimal/Standard/Extended) | Ja | Configurable Rigor |
| Baselines | Ja (ab Standard) | Must-Have für SE-Zielgruppe |
| Audit-Felder (created_by/at, version, etc.) | Ja | Compliance-Vorbereitung |
| Approval-Workflow (Draft/Approved/Deprecated) | Ja (Extended) | SE-Zielgruppe, Compliance-Vorbereitung |
| Impact-Analyse-UI | Ja (Extended) | SE-Zielgruppe |
| requirement.validate (LLM-gestützt) | Ja (optional, konfig.) | AI-natives Feature |
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
| AI-gestützte Test-Case-Generierung | v2 | Aufbauend auf v1-Datenqualität |

---

## 11. Offene Risiken und nächste Schritte

### 11.1 Offene Risiken

**R1 — Terminologie-Verwirrung zwischen Profilen:** Das Dual-Profil-System (Dev-Modus / SE-Modus) kann Nutzer verwirren, wenn nicht klar kommuniziert wird, was sich beim Profilwechsel ändert (nur Labels) und was nicht (Daten, API). Mitigiert durch persistente Header-Anzeige des aktiven Profils und Bestätigungs-Dialog mit explizitem Hinweis.

**R2 — Scope-Creep durch zwei Zielgruppen:** "Beide gleichwertig" verleitet dazu, zielgruppen-spezifische Features sofort zu bauen. Gegenmaßnahme: Datenmodell ist generisch, UI-Anpassungen minimal (nur Labels und Default-Views). Neue Features werden strikt gegen die Preset-Matrix geprüft.

**R3 — MCP Write-Access-Risiko:** AI-Agenten können Requirements direkt schreiben. Unkontrollierte oder fehlerhafte Agenten-Änderungen sind möglich. Mitigiert durch vollständiges Audit-Log aller MCP-Schreiboperationen und rollen-basierte API-Key-Berechtigungen (Write-Permission optional deaktivierbar pro Workspace).

**R4 — LLM-Abhängigkeit bei requirement.validate:** Wenn das Feature standardmäßig aktiviert ist und der konfigurierte LLM-Anbieter nicht erreichbar ist, muss das System graceful degradieren. `requirement.validate` muss klar als optionales, konfigurierbares Feature kommuniziert werden — nicht als Core-Funktion.

**R5 — i18n-Konsistenz:** Mit DE und EN von Beginn an muss sichergestellt werden, dass alle neuen UI-Strings in beiden Sprachen gepflegt werden. Empfehlung: Lint-Regel, die fehlende Translation-Keys als Build-Fehler behandelt.

### 11.2 Vor der formalen Anforderungsaufnahme zu klärende Punkte

Die folgenden Punkte sollten vor oder während der Arbeit mit dem requirements-Agenten geklärt werden, da sie die konkrete Ausgestaltung einzelner Anforderungen beeinflussen:

**Klärungsbedarf 1 — Preset-Wechsel-Semantik:** Was passiert, wenn ein Projekt von Standard auf Minimal downgradet? Werden Baselines eingefroren? Werden Approved-Requirements auf Draft zurückgesetzt? Die Semantik eines Preset-Wechsels (besonders Downgrade) muss vor der Modellierung definiert werden.

**Klärungsbedarf 2 — MCP-Audit-Log-Granularität:** Wie granular soll das MCP-Audit-Log sein? Reicht Feld-Level (welches Feld wurde geändert) oder genügt Operation-Level (welches Tool wurde mit welchen Parametern aufgerufen)? Dies beeinflusst das Datenmodell des Audit-Logs.

**Klärungsbedarf 3 — Baseline-Vergleich-UI:** Ist ein visueller Diff zwischen zwei Baselines (Side-by-Side oder Diff-View) ein v1-Feature im Extended-Preset oder v2? Die Entscheidung beeinflusst den Scope der Baseline-Implementierung erheblich.

**Klärungsbedarf 4 — Webhook-Scope:** Für welche Events sollen Webhooks in v1 feuern? (z.B. requirement.created, requirement.updated, requirement.approved, test.linked) Vollständiger Event-Katalog muss vor API-Design definiert werden.

**Klärungsbedarf 5 — requirement.validate Prompt-Strategie:** Soll der Qualitätsprüfungs-Prompt für `requirement.validate` konfigurierbar sein (z.B. domänenspezifische Qualitätskriterien für Automotive vs. Software)? Oder ist ein generischer Prompt für v1 ausreichend?

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

---

*Finalisiert durch ideation-Agenten (ReqFlow) — Ideation-Runde 3 | 2026-06-17*
*Nächster Schritt: Übergabe an requirements-Agenten für formale Anforderungsaufnahme*
