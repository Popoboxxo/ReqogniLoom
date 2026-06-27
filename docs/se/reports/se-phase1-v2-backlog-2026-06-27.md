# SE-Phase 1 Report — V2/Optional-Backlog Klarstellung

> **Agent:** se-requirements
> **Datum:** 2026-06-27
> **Status:** Phase 1 abgeschlossen — bereit für se-critic Review
> **Quellen:** `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md`, `docs/se/L0/SN_Stakeholder_Needs_Backlog.md`

---

## 1. Zusammenfassung

| Metrik | Wert |
|--------|------|
| **REQs geklärt** | **9** (8 v2/optional + 1 PDF-Export) |
| **NEU mit `arch_impact: true`** | **5** (ReqIF, Kommentare, RAG, Item-RBAC, PDF) |
| **`arch_impact: false`** (keine Architekturentscheidung nötig) | **4** (Test-Run, Test-Ergebnis-API, Artefakt-Diff, Baseline-Diff) |
| **Mit L0-SN verknüpft** | **9 von 9** (alle haben Traceability zu REQ-L0) |
| **Scope: system** | **5** (ReqIF, Kommentare, RAG, Item-RBAC, PDF) |
| **Scope: component** | **4** (Test-Run, Test-Ergebnis-API, Artefakt-Diff, Baseline-Diff) |

---

## 2. Klarstellungstabelle

| REQ-ID | Titel | Version | Priorität | Domain | arch_impact | arch_trigger | Scope | L0-SN |
|--------|-------|---------|-----------|--------|-------------|--------------|-------|-------|
| REQ-L1-023 | PDF-Report-Export | v1.0 | desired | system | **true** | PDF rendering technology and template engine selection | system | REQ-L0-015 |
| REQ-L1-034 | ReqIF-Import/-Export | v2.0 | desired | software | **true** | ReqIF-Format-Parsing und Serialisierung | system | REQ-L0-023 |
| REQ-L1-035 | Test-Run-Protokollierung | v1.1 | desired | software | false | — | component | REQ-L0-024 |
| REQ-L1-036 | Test-Ergebnis-Einspeisung | v1.1 | desired | software | false | — | component | REQ-L0-024 |
| REQ-L1-037 | Kommentar-Threads @Mention | v2.0 | optional | software | **true** | Kommentar-Datenmodell, Notification-System | system | REQ-L0-025 |
| REQ-L1-038 | Semantische Vektorsuche RAG | v2.0 | optional | software | **true** | Vektordatenbank, Embedding-Pipeline | system | REQ-L0-026 |
| REQ-L1-039 | Item-Level-RBAC | v2.0 | optional | software | **true** | Feingranulare Berechtigungsprüfung auf Artefaktebene | system | REQ-L0-027 |
| REQ-L1-040 | Visuelles Artefakt-Diff | v1.1 | desired | software | false | — | component | REQ-L0-028 |
| REQ-L1-041 | Visuelles Baseline-Diff | v1.1 | desired | software | false | — | component | REQ-L0-028 |

---

## 3. Formalisierte Anforderungen (JSON)

```json
{
  "requirements": [
    {
      "req_id": "REQ-L1-023",
      "statement": "Das System SOLL Anforderungsdokumente und Traceability-Matrizen als PDF-Berichte exportieren können — inklusive Metadaten (Version, Baseline-Referenz, Workflow-State, Audit-History) — sodass Teams in regulierten Umgebungen audit-dokumentierbare Übergaben erzeugen können.",
      "domain": "system",
      "priority": "desired",
      "version_tag": "v1.0",
      "rationale": "PDF-Reports sind ein Should-Have in KONZEPT.md §4.6; die SE-Zielgruppe benötigt dokumentierbare Übergaben für Reviews und Compliance-Nachweise (§8.1).",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Report-Anfrage mit Scope (Workspace/Artefakt/Baseline), Report-Typ (Anforderungsdokument/Traceability-Matrix), Format (PDF)"},
        {"direction": "output", "type": "data", "description": "PDF-Datei mit formatiertem Bericht, Metadaten und Traceability-Matrix"}
      ],
      "arch_impact": true,
      "arch_trigger": "PDF rendering technology and template engine selection – cross-cutting concern spanning ApplicationService (COMP-AS-008) and TraceabilityEngine (COMP-TE-004)",
      "acceptance_criteria": [
        "API-Endpunkt POST /export/pdf mit Scope=workspace, type=requirement_document erzeugt gültige PDF (keine leere/nicht lesbare Datei)",
        "API-Endpunkt POST /export/pdf mit Scope=baseline, type=traceability_matrix erzeugt PDF mit formatierter Traceability-Matrix",
        "Exportierte PDF enthält Metadaten: Systemversion, Baseline-Referenz (falls zutreffend), Workflow-State der enthaltenen Artefakte, Audit-History-Zusammenfassung",
        "PDF-Export für Workspace mit 500 Artefakten ist innerhalb von 30 Sekunden abgeschlossen",
        "PDF-Export steht über UI (Download-Button) und REST-API zur Verfügung"
      ],
      "scope": "system",
      "traceability": ["REQ-L0-015", "REQ-L2-AS-016"]
    },
    {
      "req_id": "REQ-L1-034",
      "statement": "Das System muss Anforderungsstrukturen inklusive hierarchischer Beziehungen, Attributen und TraceLinks verlustfrei im ReqIF-Format (Requirements Interchange Format, aktuelle Spezifikation) importieren und exportieren können — unter der Bedingung, dass ein ReqIF-Dokument mindestens SpecObjects, SpecRelations und SpecHierarchies vollständig abbildet und Validierungsfehler mit Elementreferenz zurückgemeldet werden.",
      "domain": "software",
      "priority": "desired",
      "version_tag": "v2.0",
      "rationale": "CSV-Export (REQ-L1-019) reicht für hierarchische MBSE-Strukturen mit Trace-Links nicht aus. ReqIF ist in regulierten Industrien (Automotive, Avionik) zwingend erforderlich für den Austausch mit DOORS, Polarion und ähnlichen Werkzeugen.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "ReqIF-Datei-Upload (.reqif) mit SpecObjects, SpecRelations, SpecHierarchies"},
        {"direction": "output", "type": "data", "description": ".reqif-Datei-Download mit vollständiger Struktur und Attributen"}
      ],
      "arch_impact": true,
      "arch_trigger": "ReqIF-Format-Parsing und Serialisierung erfordert Entscheidung über XML-Verarbeitung, ReqIF-Schema-Abbildung auf internes Datenmodell und Roundtrip-Treue",
      "acceptance_criteria": [
        "Import einer ReqIF-Datei mit 100+ SpecObjects, SpecRelations und SpecHierarchies erzeugt korrespondierende Artefakte mit Hierarchie und TraceLinks",
        "Export eines Workspace als ReqIF enthält alle SpecObjects, SpecRelations und SpecHierarchies verlustfrei",
        "Re-Import des exportierten ReqIF erzeugt strukturgleiche Artefakte (Roundtrip-Test)",
        "ReqIF-Datei mit fehlerhafter Struktur wird mit spezifischer Fehlermeldung (Elementreferenz + Ursache) abgelehnt",
        "Import/Export über synchrone Web-API und UI triggerbar"
      ],
      "scope": "system",
      "traceability": ["REQ-L0-023"]
    },
    {
      "req_id": "REQ-L1-035",
      "statement": "Das System muss Testläufe (Test Runs) als eigenständige Entitäten verwalten, die einer definierten Menge von TestCases zugeordnet sind, wobei jeder Testlauf Ausführungsstatus (Passed / Failed / Blocked / Not Run) pro TestCase aufzeichnet und Gesamtlauf-Ergebnis, Zeitstempel sowie ausführende Instanz protokolliert — mit vollständigem CRUD via synchroner Web-API und MCP.",
      "domain": "software",
      "priority": "desired",
      "version_tag": "v1.1",
      "rationale": "REQ-L1-012 definiert Testfälle und deren Coverage. Ohne Test-Run-Protokollierung fehlt der Ausführungsnachweis auf der rechten Seite des V-Modells (Verification & Validation).",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Test-Run-Erstellungsanfrage mit TestCase-IDs und optionalem Zeitplan; Status-Update-Anfrage pro TestCase"},
        {"direction": "output", "type": "data", "description": "Test-Run-Entität mit aggregiertem Ergebnis (Passed/Failed/Partial), Coverage-Delta, Zeitstempel"}
      ],
      "arch_impact": false,
      "arch_trigger": null,
      "acceptance_criteria": [
        "TestRun kann mit 1..n TestCase-IDs erstellt werden — initialer Status aller Cases: 'Not Run'",
        "Jeder TestCase im Run kann einzeln auf Passed/Failed/Blocked/Not Run gesetzt werden",
        "Das aggregierte Lauf-Ergebnis wird automatisch berechnet (Passed = alle Passed, Failed = mindestens ein Failed, Partial = mindestens ein Blocked/Not Run)",
        "TestRun enthält Zeitstempel (Start, Ende) und ausführende Instanz (z.B. CI-Job-ID)",
        "TestRun ist via REST-API und MCP (test.create_run, test.update_result) vollständig CRUD-fähig"
      ],
      "scope": "component",
      "traceability": ["REQ-L0-024"]
    },
    {
      "req_id": "REQ-L1-036",
      "statement": "Das System muss automatisierten Pipelines und CI/CD-Systemen ermöglichen, Testergebnisse direkt als Test-Run-Ergebniseinträge über die synchrone Web-API und den MCP-Server (test.record_result) einzuspeisen — unter der Bedingung, dass die aufrufende Instanz mit einem gültigen API-Key authentifiziert ist und jede Einspeisung im Audit-Log mit Agent-Client-Identität erfasst wird.",
      "domain": "software",
      "priority": "desired",
      "version_tag": "v1.1",
      "rationale": "Manuelle Einspeisung von CI/CD-Ergebnissen erzeugt Medienbrüche und unterbricht die Traceability-Kette. Automatisierte Einspeisung schließt den V-Modell-Kreislauf ohne manuelle Intervention.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "API-Key-authentifizierter POST-Aufruf (API oder MCP test.record_result) mit TestCase-ID, Ergebnisstatus, Ausgabe-Payload"},
        {"direction": "output", "type": "data", "description": "Audit-Log-Eintrag mit Agent-Identität; aktualisierter Test-Run-Status; HTTP 200 bei Erfolg"}
      ],
      "arch_impact": false,
      "arch_trigger": null,
      "acceptance_criteria": [
        "CI/CD-System sendet POST /api/v1/test-runs/{id}/results mit API-Key → Ergebnis wird protokolliert, HTTP 200",
        "MCP-Tool test.record_result akzeptiert TestCase-ID + Status + optionaler Ausgabe-Payload",
        "Fehlender/ungültiger API-Key → HTTP 401; Einspeisung wird nicht protokolliert",
        "Jede Einspeisung erzeugt einen Audit-Log-Eintrag mit Client-Identität, TestRun-ID, Status und Zeitstempel",
        "Gleichzeitige Einspeisungen verschiedener Pipelines in denselben TestRun werden serialisiert verarbeitet"
      ],
      "scope": "component",
      "traceability": ["REQ-L0-024"]
    },
    {
      "req_id": "REQ-L1-037",
      "statement": "Das System muss pro Artefakt (Requirement, ArchitectureElement, TestCase) threaded Kommentare ermöglichen — mit @Mention-Syntax für registrierte Nutzer, Zeitstempel, Autor-Angabe und vollständigem Kommentar-History-Protokoll — wobei erwähnte Nutzer eine In-App-Benachrichtigung erhalten und alle Kommentare im Audit-Trail erfasst werden.",
      "domain": "software",
      "priority": "optional",
      "version_tag": "v2.0",
      "rationale": "Ohne integrierte Kommunikation finden Abstimmungen in externen Tools statt, wodurch der Entscheidungskontext für AI-Agenten und zukünftige Reviews verloren geht. Kommentar-Threads ermöglichen die kontextgebundene Dokumentation von Klärungen direkt am betroffenen Artefakt.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Kommentar-Erstellungsanfrage mit Artefakt-ID, Text (inkl. @Mention-Syntax), Autor-Kontext"},
        {"direction": "output", "type": "data", "description": "Kommentar-Thread mit UUID, Zeitstempel, Autor; In-App-Benachrichtigung an erwähnte Nutzer"}
      ],
      "arch_impact": true,
      "arch_trigger": "Kommentar-Datenmodell, Thread-Strukturierung, @Mention-Auflösung und In-App-Notification-System erfordern neue Infrastruktur-Komponenten",
      "acceptance_criteria": [
        "Kommentar kann zu Requirement, ArchitectureElement und TestCase erstellt werden — als Top-Level-Kommentar oder als Antwort in einem bestehenden Thread",
        "@Mention eines registrierten Nutzers löst eine In-App-Benachrichtigung für den genannten Nutzer aus",
        "Mention eines nicht registrierten Namens erzeugt einen Validierungshinweis, aber der Kommentar wird trotzdem gespeichert",
        "Kommentar-Änderungen werden versioniert in der Audit-History erfasst",
        "Kommentar-Threads sind via REST-API und MCP lesbar (artifact.get_comments)"
      ],
      "scope": "system",
      "traceability": ["REQ-L0-025"]
    },
    {
      "req_id": "REQ-L1-038",
      "statement": "Das System muss eine semantische, vektorbasierte Suche über alle Artefakttypen bereitstellen, die inhaltlich ähnliche Anforderungen, Duplikate und fehlende Verknüpfungen identifiziert — abfragbar via UI und MCP (artifact.semantic_search) — wobei Embeddings bei Artefakt-Erstellung und -Änderung automatisch aktualisiert und im selben Deployment persistiert werden.",
      "domain": "software",
      "priority": "optional",
      "version_tag": "v2.0",
      "rationale": "Volltextsuche (REQ-L1-020) skaliert bei tausenden Anforderungen semantisch nicht. Vektorbasierte Suche ist Grundlage für AI-gestützte Konsistenz- und Lückenanalysen. Infrastrukturaufwand (Embedding-Modell, Vektordatenbank) macht dies zu einem v2-Feature.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Semantische Suchanfrage (natürlichsprachlicher Query oder Artefakt-ID für Ähnlichkeitssuche)"},
        {"direction": "output", "type": "data", "description": "Gerankte Trefferliste mit Ähnlichkeits-Score; Duplikat-Warnungen; vorgeschlagene TraceLinks"}
      ],
      "arch_impact": true,
      "arch_trigger": "Vektordatenbank-Auswahl, Embedding-Pipeline (Modell, Aktualisierungsstrategie), Hybrid-Suche (Vektor + Volltext) und Deployment-Integration",
      "acceptance_criteria": [
        "Natürlichsprachliche Query ('Welche Anforderungen betreffen die Authentifizierung?') liefert rankierte Ergebnisse mit Ähnlichkeits-Score",
        "Query per Artefakt-ID liefert semantisch ähnliche Artefakte als 'Duplikat-Vorschläge'",
        "Embeddings werden automatisch bei Artefakt-Erstellung und -Bearbeitung aktualisiert (maximale Verzögerung 5 Minuten)",
        "Semantische Suche ist via UI-Suchfeld und MCP-Tool (artifact.semantic_search) nutzbar",
        "Suchlatenz ≤ 2s für Workspaces mit bis zu 10.000 Artefakten"
      ],
      "scope": "system",
      "traceability": ["REQ-L0-026"]
    },
    {
      "req_id": "REQ-L1-039",
      "statement": "Das System muss Projekt-Administratoren ermöglichen, Sichtbarkeits- und Bearbeitungsrechte auf Subsystem- oder Artefakt-Ebene zu konfigurieren — sodass externe Partner oder Zulieferer Lesezugriff auf definierte Teilmengen eines Projekts erhalten, ohne den gesamten Systemkontext einzusehen — unter der Bedingung, dass Item-Level-Regeln die Workspace-RBAC (REQ-L1-010) verfeinern und niemals überschreiben.",
      "domain": "software",
      "priority": "optional",
      "version_tag": "v2.0",
      "rationale": "Workspace-RBAC (REQ-L1-010) und Mandantenfähigkeit (REQ-L1-015) trennen Kunden vollständig. In großen Projekten müssen externe Partner am selben Projekt mitarbeiten, ohne den gesamten Systemkontext zu sehen — eine Anforderung, die feingranulare Zugriffslisten erfordert.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Zugriffsregel-Konfiguration mit Artefakt-ID oder Subsystem-ID, Nutzer/Gruppe, Berechtigungstyp (read/write)"},
        {"direction": "output", "type": "control", "description": "Gefilterte API-Antworten gemäß Item-Level-Regeln; HTTP 403 bei Regelverstoß"}
      ],
      "arch_impact": true,
      "arch_trigger": "Feingranulare Berechtigungsprüfung auf Artefaktebene erfordert Erweiterung des Autorisierungsmodells und potenziell der Datenzugriffsschicht (Query-Filtering, Permission-Caching)",
      "acceptance_criteria": [
        "Admin konfiguriert: 'Nutzer X hat Lesezugriff auf Subsystem Y' → Nutzer X sieht nur Artefakte in Subsystem Y",
        "Item-Level-Regel überschreibt keine Workspace-RBAC: Admin-Rechte auf Workspace-Ebene haben weiterhin Vorrang",
        "Item-Level-Regel wird bei API-Zugriffen ausgewertet (keine UI-only-Beschränkung)",
        "Konfiguration via UI (Berechtigungs-Editor) und API-Endpunkt",
        "Performance: max. 10 % Overhead auf API-Response-Zeiten für Workspaces mit ≤ 100 Item-Level-Regeln"
      ],
      "scope": "system",
      "traceability": ["REQ-L0-027"]
    },
    {
      "req_id": "REQ-L1-040",
      "statement": "Das System muss Änderungen an einem einzelnen Artefakt (Requirement, ArchitectureElement, TestCase) zwischen zwei beliebigen Versionen als visuellen Text-Diff darstellen — mit Hervorhebung von hinzugefügten, geänderten und gelöschten Feldinhalten — abrufbar in der Artefakt-Detailansicht der GUI und via synchroner Web-API.",
      "domain": "software",
      "priority": "desired",
      "version_tag": "v1.1",
      "rationale": "Das Audit-Log (REQ-L1-011) speichert alle Änderungen, ist aber für Menschen schwer lesbar. Ein visueller Diff pro Artefakt ist für formale Reviews und Freigabe-Entscheidungen unerlässlich.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Diff-Anfrage mit Artefakt-ID und zwei Versions-Referenzen (version_a, version_b)"},
        {"direction": "output", "type": "data", "description": "Strukturiertes Diff-Objekt mit Feld-Level-Änderungen; UI-Darstellung mit Syntaxhervorhebung"}
      ],
      "arch_impact": false,
      "arch_trigger": null,
      "acceptance_criteria": [
        "REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück",
        "Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder pro Vergleich",
        "GUI zeigt Diff mit visueller Hervorhebung (grün=hinzugefügt, rot=gelöscht, gelb=geändert)",
        "Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich",
        "Markdown-Felder werden als Text-Diff dargestellt (kein strukturelles AST-Diff)"
      ],
      "scope": "component",
      "traceability": ["REQ-L0-028"]
    },
    {
      "req_id": "REQ-L1-041",
      "statement": "Das System muss den Vergleich zweier benannter Baselines desselben oder kompatiblen Scopes als visuellen Diff darstellen — mit kategorisierten Änderungslisten (hinzugefügte, geänderte, gelöschte Artefakte inkl. Versions-Delta) — abrufbar in der GUI und als maschinenlesbarer API-Response.",
      "domain": "software",
      "priority": "desired",
      "version_tag": "v1.1",
      "rationale": "L2-BL-02 definiert den Baseline-Vergleich auf Datenebene. Diese Anforderung ergänzt die menschlesbare Darstellung, die für formale Reviews und Freigabe-Entscheidungen in regulierten Umgebungen zwingend erforderlich ist.",
      "external_interfaces": [
        {"direction": "input", "type": "data", "description": "Baseline-Diff-Anfrage mit baseline_id_a und baseline_id_b"},
        {"direction": "output", "type": "data", "description": "Diff-Report mit kategorisierten Artefakt-Änderungslisten (added/modified/deleted); GUI-Darstellung und maschinenlesbarer JSON-Response"}
      ],
      "arch_impact": false,
      "arch_trigger": null,
      "acceptance_criteria": [
        "REST-API-Endpoint GET /baselines/{id_a}/diff/{id_b} liefert kategorisiertes Diff (added, modified, deleted)",
        "Modified-Liste enthält Versions-Delta (Version in Baseline A → Version in Baseline B)",
        "GUI zeigt Diff mit kategorisierter Liste und Navigation zwischen Kategorien",
        "Vergleich kompatibler Scopes (document↔document, project↔project) ist möglich",
        "Vergleich inkompatibler Scopes (document↔project) liefert klaren Fehlerhinweis"
      ],
      "scope": "component",
      "traceability": ["REQ-L0-028"]
    }
  ]
}
```

---

## 4. Cross-Reference Matrix: SN ↔ L1 ↔ L2 (geplant)

| SN | REQ-L0 | L1-REQ | L1-Titel | Geplantes L2-System | Status |
|:--:|:------:|:------:|----------|:-------------------:|:------:|
| SN-15 | REQ-L0-015 | REQ-L1-023 | PDF-Report-Export | ApplicationServiceSystem (AS) | v1, nicht impl. |
| SN-23 | REQ-L0-023 | REQ-L1-034 | ReqIF-Import/-Export | *Neu: ReqIFService* (vorschlag) | v2, nicht impl. |
| SN-24 | REQ-L0-024 | REQ-L1-035 | Test-Run-Protokollierung | *Erweiterung: TestMgmt* | v1.1, nicht impl. |
| SN-24 | REQ-L0-024 | REQ-L1-036 | Test-Ergebnis-Einspeisung | *Erweiterung: TestMgmt* | v1.1, nicht impl. |
| SN-25 | REQ-L0-025 | REQ-L1-037 | Kommentar-Threads | *Neu: CommentService* (vorschlag) | v2, nicht impl. |
| SN-26 | REQ-L0-026 | REQ-L1-038 | Semantische Vektorsuche | *Neu: VectorSearchService* (vorschlag) | v2, nicht impl. |
| SN-27 | REQ-L0-027 | REQ-L1-039 | Item-Level-RBAC | *Erweiterung: AuthAndTenancy* | v2, nicht impl. |
| SN-28 | REQ-L0-028 | REQ-L1-040 | Visuelles Artefakt-Diff | *Erweiterung: ApplicationService/RF* | v1.1, nicht impl. |
| SN-28 | REQ-L0-028 | REQ-L1-041 | Visuelles Baseline-Diff | *Erweiterung: BaselineService/RF* | v1.1, nicht impl. |

**Legende:**
- *Kursiv* = L2-System existiert noch nicht als formale Architektur-Entscheidung (Vorschlag für se-architect)
- **Fett** = L2-System existiert bereits

**Status aller 6 SN aus Backlog (REQ-L0-023..028):**
- Alle 6 SNs sind via promoted_to_l1 auf L1-REQs verlinkt
- Kein SN hat `status: needs_promotion` — alle sind bereits in L1 abgebildet
- 3 SNs splitten auf 2 L1-REQs (SN-24 → L1-035/036, SN-28 → L1-040/041)

---

## 5. Offene Punkte für se-architect

Die folgenden Punkte müssen vor der L2-Zerlegung durch den se-architect geklärt werden:

### OP-1: PDF-Rendering-Architektur (REQ-L1-023)
**Problem:** PDF-Export betrifft zwei L2-Systeme (ApplicationService COMP-AS-008 für Requirement-Dokumente, TraceabilityEngine COMP-TE-004 für VCRM-Matrix). Soll eine gemeinsame PDF-Rendering-Engine (= neues Subsystem) oder je L2-System eine eigene Implementierung entstehen?
**Auswirkung:** Anzahl L2-Systeme, Deployment-Dependencies (reportlab/weasyprint/prawn), Template-Strategie.
**Betroffene REQs:** REQ-L1-023, REQ-L2-AS-016

### OP-2: Vektordatenbank für semantische Suche (REQ-L1-038)
**Problem:** Die semantische Suche erfordert eine Vektordatenbank und Embedding-Pipeline. Soll eine eingebettete Lösung (sqlite-vss/pgvector) oder ein externer Service (Qdrant/Milvus) verwendet werden? Wie wird das Embedding-Modell deployed (Lokal via LLM-Adapter oder externer API)?
**Auswirkung:** Deployment-Topologie, Betriebskomplexität, Self-Hosted-Kompatibilität.
**Betroffene REQs:** REQ-L1-038, REQ-L1-018 (Self-Hosted)

### OP-3: Item-Level-RBAC vs. bestehendes Auth-Modell (REQ-L1-039)
**Problem:** Workspace-RBAC (REQ-L1-010) ist auf Workspace-Ebene implementiert (AuthAndTenancySystem). Item-Level-Berechtigungen erfordern Query-Level-Filtering auf Artefaktebene. Wie wird die Permission-Evaluierung in die bestehende Datenzugriffsschicht integriert, ohne bestehende Queries zu verlangsamen?
**Auswirkung:** Datenzugriffsschicht, AuthAndTenancy-Erweiterung, Performance-Impact auf bestehende API-Endpunkte.
**Betroffene REQs:** REQ-L1-039, REQ-L1-010, REQ-L1-026 (Performance)

### OP-4: CommentService — eigenständiges L2-System oder Component? (REQ-L1-037)
**Problem:** Kommentar-Threads mit @Mention und In-App-Notification benötigen ein Datenmodell, Notification-Dispatch und Audit-Integration. Ist dies ein eigenständiges L2-System (CommentService) oder ein Component innerhalb eines bestehenden Systems (z.B. ApplicationService)?
**Auswirkung:** L2-Architektur, Notification-Infrastruktur.
**Betroffene REQs:** REQ-L1-037, REQ-L1-011 (Audit)

### OP-5: ReqIF-Konverter — new L2 system or component? (REQ-L1-034)
**Problem:** ReqIF-Import/Export erfordert bidirektionale Konvertierung zwischen ReqIF-XML und dem internen Datenmodell. Soll dies ein eigenständiges L2-System werden (ReqIFService) oder in ApplicationService (COMP-AS-008 ExportService) integriert werden?
**Auswirkung:** L2-System-Grenzen, Testbarkeit der Konvertierung.
**Betroffene REQs:** REQ-L1-034, REQ-L1-019 (Export)

---

## 6. Nächste Schritte

1. **Phase 2: User-Approval** — Präsentation der geklärten Anforderungen an Stakeholder
2. **Phase 3: Formalization** — Validierung durch se-critic
3. **Handoff an se-architect** — L2-Zerlegung der 5 neuen/geänderten system-scope REQs

---

*Erstellt durch se-requirements-Agent | 2026-06-27*
*Nächster Schritt: se-critic Review (review_target: "requirements")*
