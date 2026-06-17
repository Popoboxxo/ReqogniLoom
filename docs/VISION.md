# ReqFlow — Produktvision

> Erstellt: 2026-06-17 | Status: Entwurf | Branch: feat/vision-feature-set
>
> Dieses Dokument beschreibt die Produktvision, das priorisierte Feature-Set und offene
> Entscheidungsfragen für ReqFlow. Es ist das Ausgangsdokument für die formale
> Anforderungsaufnahme und wird nicht als REQUIREMENTS.md ersetzt, sondern ergänzt.

---

## 1. Produktvision

### 1.1 Ein-Satz-Pitch

**ReqFlow** ist das Requirements-Management-Tool, das AI-Agenten als First-Class Citizens
behandelt — nicht als Add-on, sondern als native Teilnehmer am Anforderungsprozess.

### 1.2 Ausführliche Beschreibung

ReqFlow verbindet klassisches Requirements Engineering mit der Realität von 2026: In
Software-Teams arbeiten AI-Agenten nicht mehr als isolierte Assistenten, sondern als aktive
Teilnehmer im Entwicklungsprozess. Sie generieren Code, schreiben Tests, führen Reviews durch
— doch sie haben keinen strukturierten, maschinell lesbaren Zugriff auf das *Warum* hinter
dem Code: auf Anforderungen, Akzeptanzkriterien, Testabdeckung und Traceability.

ReqFlow schließt diese Lücke. Es ist ein Requirements-Management-Tool, das über einen nativen
MCP Server (Model Context Protocol) AI-Agenten direkten, strukturierten Zugriff auf den
gesamten Anforderungskontext gibt. Ein Code-Generierungsagent kann damit zur Laufzeit fragen:
"Welche Anforderungen muss diese Komponente erfüllen?" Ein Test-Agent kann prüfen: "Welche
Requirements sind noch nicht durch Tests abgedeckt?" Ein Review-Agent kann validieren:
"Wurde die Anforderung korrekt implementiert?"

Gleichzeitig bleibt ReqFlow vollständig nutzbar als klassisches Requirements-Management-Tool
für menschliche Nutzer — mit einer klaren, schnellen React-Oberfläche und einer REST API,
die jedes Team integrieren kann.

### 1.3 Positionierung

```
                    Einfachheit / Agilität
                           ▲
                           │
          Linear ──────────┼────────── ReqFlow (Ziel)
          Notion           │
                           │
─────────────── AI-Add-on──┼──AI-nativ ──────────────
                           │
         Jira + AI-Plugin  │
                           │
    DOORS / Polarion ──────┼
    Codebeamer             │
                           ▼
                   Enterprise-Komplexität
```

ReqFlow besetzt den bisher leeren Quadranten: **AI-nativ + handhabbar** — ohne den
Enterprise-Overhead von DOORS oder Polarion, aber mit echtem Systems-Engineering-Rückgrat.

---

## 2. Für wen ist ReqFlow?

### 2.1 Primäre Zielgruppen (Hypothesen — zu validieren)

**Zielgruppe A: AI-first Development Teams**
Software-Teams, die bereits AI-Agenten (Cursor, Claude Code, GitHub Copilot Workspace) in
ihrem Entwicklungsprozess einsetzen und deren Agenten heute keinen strukturierten Zugriff auf
Anforderungen haben. Diese Teams bauen Produkte mit moderater Komplexität und leiden daran,
dass AI-generierter Code oft am Kontext vorbeigeht, weil der Kontext nirgends maschinenlesbar
vorliegt.

**Zielgruppe B: Produktteams in regulierten Umgebungen (Mid-Market)**
Teams, die mehr als "Jira-Tickets als Anforderungen" brauchen, aber nicht die
Implementation-Komplexität und Lizenzkosten von IBM DOORS, Siemens Polarion oder PTC
Codebeamer stemmen wollen. Beispiel: Medizintechnik-Startups, Automotive-Zulieferer der
zweiten Reihe, Industrieautomation-KMU.

**Zielgruppe C: Systems Engineers mit AI-Affinität**
Engineers, die klassische Systems-Engineering-Methodik (Artefakt-Hierarchien, Traceability,
Testabdeckung) mit modernen AI-Werkzeugen kombinieren wollen und aktuell zwischen zu simplen
Agile-Tools und zu komplexen Enterprise-ALM-Tools stecken.

### 2.2 Explizit NICHT für ReqFlow (v1)

- Teams ohne jegliche Requirements-Disziplin, die nur Issue-Tracking brauchen → Jira/Linear
- Hochregulierte Programme mit Compliance-Zertifizierungspflicht (z.B. DO-178C Level A,
  ISO 26262 ASIL-D) → Polarion, Codebeamer (in v1; mögliches späteres Ziel)
- Organisationen, die primär Dokument-Management brauchen → Confluence/SharePoint

---

## 3. Welches Problem löst ReqFlow?

### 3.1 Die fünf zentralen Pain Points

**Pain Point 1: AI-Agenten arbeiten blind**
Wenn ein AI-Coding-Agent Code generiert, hat er keinen strukturierten Zugriff auf die
zugehörigen Anforderungen. Er arbeitet aus Kommentaren, README-Dateien oder mündlich
weitergegebenen Informationen — und produziert Code, der die Anforderungen verfehlt oder
dubliziert.

**Pain Point 2: Traceability bricht beim Wachstum**
Manuelle Traceability funktioniert bis ca. 200-500 Anforderungen. Danach explodiert der
Aufwand für Change-Impact-Analysen, Coverage-Prüfungen und Review-Workflows. Existing tools
erzwingen entweder manuelles Pflegen oder kostspielige Enterprise-Lizenzen.

**Pain Point 3: Context-Switching zwischen Tools**
Requirements in Confluence, Tickets in Jira, Tests in TestRail, Code in GitHub — kein Tool
verbindet diese Ebenen nativ. Traceability über Systemgrenzen ist manuell, fehlerprone und
veraltet ständig.

**Pain Point 4: Enterprise-Tools sind zu schwer, Agile-Tools zu leicht**
DOORS/Polarion brauchen Monate für die Implementierung und erfordern dedizierte Admins.
Jira/Linear bieten keine echte Anforderungshierarchie, Baselines oder Traceability-Matrizen.
Der Mittelweg fehlt.

**Pain Point 5: Requirements als Wegwerfprodukt**
In vielen Teams werden Anforderungen einmal geschrieben und dann nie mehr gepflegt. Änderungen
im Code schlagen nicht zurück auf Requirements. Tests sind nicht mit Requirements verknüpft.
Die Anforderungsdokumentation spiegelt nie den aktuellen Systemzustand wider.

---

## 4. Was macht "AI-nativ" bei ReqFlow konkret aus?

### 4.1 MCP Server als First-Class Schnittstelle

ReqFlow stellt einen **nativen MCP Server** bereit — nicht als Erweiterung oder Plugin,
sondern als gleichrangige Schnittstelle neben der REST API. Das bedeutet:

| MCP Tool | Beschreibung | AI-Workflow |
|----------|-------------|-------------|
| `get_requirement(id)` | Einzelne Anforderung mit Kontext abrufen | Coding-Agent prüft vor Implementierung |
| `list_requirements(artifact, filter)` | Anforderungen eines Artefakts filtern | Test-Agent ermittelt Abdeckungslücken |
| `get_traceability(req_id)` | Trace-Links zu Tests, Sub-Reqs, Code abrufen | Review-Agent validiert Implementierung |
| `create_requirement(...)` | Neue Anforderung anlegen | Requirements-Agent strukturiert Interviews |
| `update_requirement(id, ...)` | Anforderung aktualisieren | Änderungs-Agent pflegt nach Change Request |
| `get_coverage_report(artifact)` | Testabdeckung je Artefakt abrufen | QA-Agent identifiziert untestete Bereiche |
| `search_requirements(query)` | Semantische Suche über alle Anforderungen | Duplikat-Erkennung, Impact-Analyse |

### 4.2 Konkrete AI-Workflows

**Workflow 1: Context-Aware Code Generation**
Ein Coding-Agent (z.B. Claude Code) ruft vor der Implementierung einer Komponente via MCP
alle zugehörigen Requirements ab. Code-Generierung erfolgt mit vollständigem Anforderungs-
kontext. Nach der Implementierung aktualisiert der Agent den Traceability-Link.

**Workflow 2: Automated Test Coverage Analysis**
Ein Test-Agent scannt via MCP alle Requirements eines Artefakts und vergleicht mit den
vorhandenen Tests. Er generiert einen Coverage-Report und legt automatisch Test-Lücken als
Tasks an.

**Workflow 3: Change Impact Analysis**
Bei einer Anforderungsänderung ruft ein Analyse-Agent alle abhängigen Requirements, Tests und
Code-Referenzen ab und erstellt einen Blast-Radius-Report — in Sekunden statt Stunden.

**Workflow 4: Requirements Elicitation Assistant**
Ein Interviewing-Agent führt Stakeholder-Gespräche und schreibt die Ergebnisse direkt als
strukturierte Requirements in ReqFlow, inklusive Kategorisierung und Traceability.

### 4.3 Was AI-Add-on anders macht

| Dimension | AI-Add-on (Jira/Confluence + KI-Plugin) | AI-nativ (ReqFlow) |
|-----------|----------------------------------------|---------------------|
| Zugriff | Über Webhooks/API-Wrapper, oft read-only | MCP-nativ, read/write |
| Kontext | Dokumentenebene (Text) | Strukturebene (Graph) |
| Workflow | KI hilft bei Texterstellung | KI ist Prozess-Teilnehmer |
| Traceability | Manuell, KI-Vorschläge als Text | Strukturiert, maschinenlesbar |
| Integration | Nachträglich aufgesetzt | Von Anfang eingeplant |

---

## 5. Abgrenzung zu Wettbewerbern

### 5.1 Wettbewerbs-Matrix

| Tool | Stärke | Schwäche | ReqFlow-Differenz |
|------|--------|----------|-------------------|
| **IBM DOORS Next** | Compliance, Skalierung, Baselines | Extrem komplex, teuer, kein AI-native | Leichtgewichtig, MCP-nativ, Open |
| **Siemens Polarion** | Vollständige ALM-Suite, ISO-Templates | Siemens-Ökosystem-Lock-in, steile Lernkurve | Herstellerunabhängig, AI-first |
| **PTC Codebeamer** | Vollständig ALM, erschwinglich für Enterprise | Komplex für kleinere Teams | Einfacher Einstieg, Django/React-Stack |
| **Jira** | Bekannt, flexibel, viele Plugins | Keine echte REQ-Hierarchie, keine Baselines | Strukturiertes Requirements-Modell |
| **Linear** | Schnell, modern, Developer-friendly | Kein Requirements-Engineering, kein SE | Artefakt-Hierarchie, Traceability |
| **Notion** | Flexibel, kollaborativ | Kein strukturiertes Requirements-Modell | Formale Struktur, MCP-Zugriff |
| **Jama Connect** | Kollaborativ, Compliance-ready | Teuer, SaaS-only, kein MCP | Self-Hosted-Option, AI-nativ |

### 5.2 ReqFlows einzigartiger Vorteil

ReqFlow ist das **einzige Requirements-Management-Tool**, das:
1. Einen nativen MCP Server als Produktions-Schnittstelle anbietet
2. AI-Agenten als Prozess-Teilnehmer (nicht nur Texthelfer) behandelt
3. Von einfachem Requirements-Management bis Systems Engineering skaliert
4. Open-Source-Stack (Django + React) ohne Vendor-Lock-in verwendet

---

## 6. Priorisiertes Kern-Feature-Set (MoSCoW)

### 6.1 Functional — Funktionale Anforderungen

**Must Have (MVP)**
- Artefakt-Hierarchie: Anforderungen in verschachtelten Artefakten (Projekte → Systeme →
  Subsysteme → Komponenten)
- Requirements CRUD: Erstellen, Lesen, Aktualisieren, Archivieren von Anforderungen
- Anforderungs-Kategorien: Functional, Non-Functional, API, UI/UX, Data, Integration, Test
- Traceability: Verknüpfung von Requirements untereinander (Parent-Child, Derives-From,
  Satisfies)
- Baselines: Snapshots von Anforderungsständen (für Vergleich und Audit)
- Volltextsuche über alle Anforderungen

**Should Have**
- Change History: Vollständige Änderungshistorie je Anforderung
- Anforderungs-Templates: Vordefinierte Strukturen für häufige Typen
- Bulk-Operationen: Mehrere Anforderungen gleichzeitig bearbeiten/verschieben
- Anforderungs-Import aus Markdown, CSV, Word

**Could Have**
- AI-gestützte Ambiguitätserkennung in Requirements-Texten
- Automatische Kategorisierungs-Vorschläge
- Anforderungs-Qualitätsscore (Vollständigkeit, Präzision, Testbarkeit)

---

### 6.2 Non-Functional — Nicht-funktionale Anforderungen

**Must Have**
- Performance: API-Antwortzeiten < 200ms für Standard-Queries (< 10.000 Requirements)
- Sicherheit: Authentifizierung, rollenbasierte Zugriffskontrolle (Admin, Editor, Viewer)
- Datenpersistenz: Keine Datenverluste, transaktionale Konsistenz

**Should Have**
- Skalierung: Unterstützung für 10.000+ Requirements ohne Performance-Degradation
- Auditierbarkeit: Jede Änderung ist nachvollziehbar (Wer, Wann, Was)
- Self-Hosted-Deployment: Docker Compose als primäres Deployment-Modell

**Could Have**
- Horizontale Skalierung für 100.000+ Requirements
- SaaS-Option (Managed Hosting)
- Daten-Verschlüsselung at-rest für Compliance-Anforderungen

---

### 6.3 API — REST API und MCP Server

**Must Have**
- REST API: Vollständige CRUD-Operationen für alle Entitäten
- MCP Server: Native MCP-Tool-Implementierungen für alle Kernoperationen
  (get, list, create, update, search, traceability, coverage)
- API-Authentifizierung: Token-basiert (Bearer Token / API Keys)
- OpenAPI-Spezifikation: Maschinenlesbare API-Dokumentation

**Should Have**
- Webhook-Support: Events bei Anforderungsänderungen
- GraphQL-Endpunkt: Für flexible Client-Queries
- Rate Limiting: Schutz vor Überlastung

**Could Have**
- SSO-Integration (SAML/OIDC)
- MCP über SSE (Server-Sent Events) für Streaming-Responses

---

### 6.4 UI/UX — Frontend und Benutzerinteraktion

**Must Have**
- Dashboard: Übersicht über Projekte, Artefakte, offene Issues
- Requirements-Editor: Inline-Editing mit Markdown-Support
- Artefakt-Navigation: Baumstruktur für Hierarchie-Navigation
- Traceability-Anzeige: Verknüpfte Requirements und Tests sichtbar

**Should Have**
- Traceability-Matrix: Tabellarische Übersicht über Coverage
- Such- und Filteroberfläche: Facettierte Suche mit Kategorien, Status, Tags
- Dark Mode
- Responsive Design für Tablet-Nutzung

**Could Have**
- Drag-and-Drop Restrukturierung von Artefakt-Hierarchien
- Echtzeit-Kollaboration (mehrere Nutzer gleichzeitig)
- Kommentare und Diskussionen je Anforderung

---

### 6.5 Data — Datenmodelle und Artefakt-Strukturen

**Must Have**
- Anforderungs-Entität: ID, Titel, Beschreibung, Kategorie, Status, Priorität, Tags,
  Ersteller, Timestamps
- Artefakt-Entität: Hierarchische Struktur, Beschreibung, Typ
- Trace-Link-Entität: Quell-REQ, Ziel-REQ/Test, Beziehungstyp
- Test-Entität: Titel, Beschreibung, Typ (Unit/Integration/System), Status, verknüpfte REQs

**Should Have**
- Baseline-Entität: Snapshot von Artefakt + Requirements zu einem Zeitpunkt
- Attribut-Schema: Anpassbare Felder je Artefakt-Typ (für domänenspezifische Metadaten)

**Could Have**
- Versionierung auf Anforderungsebene (Git-ähnlich mit Branches/Merges)
- Formale Constraint-Sprache für Requirements (strukturiert, nicht nur Freitext)

---

### 6.6 Integration — Externe Systeme und Import/Export

**Must Have**
- Export: JSON, CSV für alle Entitäten
- Import: CSV für Bulk-Import von Requirements

**Should Have**
- GitHub Integration: Anforderungen mit GitHub Issues/PRs verknüpfen
- Export: PDF-Reports (Anforderungsdokument, Traceability-Matrix)
- Import: Markdown-Dateien, Word-Dokumente (.docx)

**Could Have**
- Jira-Synchronisation: Bidirektional, konfigurierbar
- ReqIF-Import/Export (Standard-Format für Systems Engineering)
- CI/CD-Integration: GitHub Actions / GitLab CI kann Requirements-Status aktualisieren

---

### 6.7 Test — Testmanagement-Anforderungen

**Must Have**
- Test-Cases: Erstellen und Verknüpfen mit Requirements
- Coverage-Übersicht: Welche Requirements haben mindestens einen Test?
- Test-Status: Passed / Failed / Not Run je Test-Case

**Should Have**
- Test-Suiten: Gruppierung von Test-Cases
- Test-Runs: Ausführungs-Protokolle mit Ergebnissen
- Coverage-Report: Exportierbar als PDF/CSV

**Could Have**
- Automatisierte Test-Ergebnis-Ingestion aus pytest, JUnit, xUnit
- AI-gestützte Test-Case-Generierung aus Requirements
- Risk-based Testing: Priorisierung nach Anforderungs-Kritikalität

---

## 7. Offene Fragen und Entscheidungspunkte

Die folgenden Fragen sind für die Produktstrategie kritisch und müssen vor oder während
der formalen Anforderungsaufnahme beantwortet werden:

### 7.1 Zielgruppe und Markt

**F1: Primäre Zielgruppe — Software-Teams oder Systems Engineers?**
Beide Zielgruppen haben unterschiedliche Erwartungen an Terminologie, Workflow und Komplexität.
Software-Teams wollen schnelle Iteration und Git-Integration. Systems Engineers erwarten
formale Artefakt-Hierarchien, Baselines und ggf. Compliance-Features.
*Empfehlung: Software-Teams als v1-Primärzielgruppe, Systems Engineering in v2.*

**F2: Self-Hosted oder SaaS oder beides?**
Self-Hosted via Docker Compose ist im Stack angelegt. Für AI-Agenten-Workflows ist eine
öffentlich erreichbare Instanz (SaaS) attraktiver. Self-Hosted hat Vorteile bei Datenschutz
und regulierten Umgebungen.
*Empfehlung: Self-Hosted als v1-Deployment, SaaS-Option als v2.*

**F3: Open Source oder proprietär?**
Open Source würde Adoption in der Developer-Community beschleunigen (besonders für den
MCP-Integration-Anwendungsfall). Proprietär erlaubt direktere Monetarisierung.

### 7.2 AI-Integration

**F4: Welche AI-Agenten sollen ReqFlow via MCP konkret nutzen?**
Die MCP-Schnittstelle kann sehr unterschiedlich ausgestaltet sein je nach Antwort:
- Claude Code / Cursor (Code-Generierung mit Anforderungskontext)
- CI/CD-Agenten (automatische Coverage-Prüfung nach PR)
- Dedicated Requirements-Agenten (Elicitation, Review)
*Diese Frage bestimmt, welche MCP-Tools in v1 implementiert werden.*

**F5: Lokales LLM oder externe API für AI-Features?**
Wenn ReqFlow self-hosted in regulierten Umgebungen laufen soll, müssen AI-Features auch
mit lokalem LLM (Ollama, LM Studio) funktionieren — nicht nur mit OpenAI/Anthropic-APIs.

### 7.3 Systems Engineering Tiefe

**F6: Wie tief soll Systems Engineering in v1 gehen?**
Optionen:
- Minimal: Anforderungs-Hierarchie + Traceability (wie oben beschrieben)
- Mittel: + Artefakt-Typen (System, Subsystem, Interface), formale Beziehungstypen
- Vollständig: + SysML-Elemente, Modellverknüpfungen, MBSE-Workflow

**F7: Compliance-Anforderungen in der Roadmap?**
ISO 26262, IEC 61508, DO-178C erfordern spezifische Features (elektronische Signaturen,
Baseline-Freeze, auditierbare Review-Workflows). Ist das ein mittelfristiges Ziel?

### 7.4 Technologie und Deployment

**F8: Multi-Tenancy von Anfang an?**
Wenn SaaS geplant ist, muss Multi-Tenancy (Datentrennung zwischen Organisationen) von
Anfang an im Datenbankmodell berücksichtigt werden. Nachträgliche Migration ist aufwändig.

**F9: Internationalisierung und Mehrsprachigkeit?**
Ist die Benutzeroberfläche langfristig mehrsprachig geplant? Das beeinflusst Front-End-
Architektur-Entscheidungen (i18n-Framework) von Anfang an.

**F10: Wie wird Echtzeit-Kollaboration priorisiert?**
Gleichzeitige Bearbeitung (wie Google Docs / Notion) erfordert CRDT oder OT-Implementierung
(Operational Transformation) — erhebliche Komplexität. Ist das ein Must-Have für v1?

---

## 8. Zusammenfassung

### Kernidee
ReqFlow ist das erste Requirements-Management-Tool, das AI-Agenten als native Prozess-
Teilnehmer über MCP einbindet — nicht als Texthelfer, sondern als vollständige, strukturierte
Schnittstelle für den gesamten Anforderungslebenszyklus.

### Differenzierung
- Einziges RM-Tool mit nativem MCP Server
- Skaliert von Startup bis Systems Engineering
- Open Stack (Django + React), kein Vendor-Lock-in
- Self-Hosted als primäres Deployment-Modell

### Empfohlener MVP-Scope (v1)
- Artefakt-Hierarchie mit Requirements CRUD
- Traceability zwischen Requirements und Tests
- REST API + MCP Server (Basis-Tool-Set)
- Einfache React-UI für Navigation und Editing
- Docker Compose Deployment

### Nächste Schritte
1. Offene Fragen F1 (Zielgruppe), F4 (MCP-Agenten) und F6 (SE-Tiefe) mit Product Owner klären
2. Formale Anforderungsaufnahme durch requirements-Agenten (auf Basis dieses Dokuments)
3. Architektur-Entscheide für Datenmodell und MCP-Server-Design

---

*Erstellt durch den ideation-Agenten (ReqFlow). Quellen: Wettbewerbs-Recherche 2026,
Trace.space AI-vs-Traditional-Analyse, ReqSuite Market-Gap-Analyse, MCP-Dokumentation.*
