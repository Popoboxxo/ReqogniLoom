---
step: se-requirements
agent: se-requirements
iteration: 1
status: draft
timestamp: 2026-06-27T17:45:00Z
schema_version: 1
---

# L1-Klarstellungen (Iteration 1) — V2/Optional-Backlog + PDF-Export

> **Level:** L1 (System-Anforderungen)
> **System:** Gesamtsystem (ReqFlow)
> **Quelle:** `L1_Gesamtsystem_Requirements.md` (REQ-L1-034..041, REQ-L1-023)
> **Datum:** 2026-06-27
> **Status:** Draft — Phase 1 abgeschlossen, wartet auf User-Approval

---

## Klarstellung: REQ-L1-023 — PDF-Report-Export (v1, priorisiert)

**Neu bewertet:**
- `arch_impact: true` — PDF-Rendering-Engine und Template-Selection sind Architekturentscheidungen
- `arch_trigger`: "PDF rendering technology and template engine selection – cross-cutting concern spanning ApplicationService (COMP-AS-008) and TraceabilityEngine (COMP-TE-004)"
- `scope`: system (betrifft zwei L2-Systeme)
- `traceability`: REQ-L0-015, REQ-L2-AS-016

**Akzeptanzkriterien (neu):**
1. API-Endpunkt POST /export/pdf mit Scope=workspace, type=requirement_document erzeugt gültige PDF
2. API-Endpunkt POST /export/pdf mit Scope=baseline, type=traceability_matrix erzeugt PDF mit formatierter Matrix
3. Exportierte PDF enthält Metadaten: Systemversion, Baseline-Referenz, Workflow-State, Audit-History-Zusammenfassung
4. PDF-Export für Workspace mit 500 Artefakten ist innerhalb von 30 Sekunden abgeschlossen
5. PDF-Export steht über UI (Download-Button) und REST-API zur Verfügung

---

## Klarstellung: REQ-L1-034 — ReqIF-Import/-Export (v2.0)

**Neu bewertet:**
- `arch_impact: true` — ReqIF-Parsing und -Serialisierung erfordert Technologieentscheidung
- `arch_trigger`: "ReqIF-Format-Parsing und Serialisierung erfordert Entscheidung über XML-Verarbeitung, ReqIF-Schema-Abbildung auf internes Datenmodell und Roundtrip-Treue"
- `scope`: system — neuer Subsystem-Bedarf (ReqIF-Konverter)
- `priority`: desired (unverändert)

**Akzeptanzkriterien (neu):**
1. Import einer ReqIF-Datei mit 100+ SpecObjects, SpecRelations und SpecHierarchies erzeugt korrespondierende Artefakte mit Hierarchie und TraceLinks
2. Export eines Workspace als ReqIF enthält alle SpecObjects, SpecRelations und SpecHierarchies verlustfrei
3. Re-Import des exportierten ReqIF erzeugt strukturgleiche Artefakte (Roundtrip-Test)
4. ReqIF-Datei mit fehlerhafter Struktur wird mit spezifischer Fehlermeldung (Elementreferenz + Ursache) abgelehnt
5. Import/Export über synchrone Web-API und UI triggerbar

---

## Klarstellung: REQ-L1-035 — Test-Run-Protokollierung (v1.1)

**Neu bewertet:**
- `arch_impact: false` — Erweiterung des bestehenden Testmanagement-Subsystems, folgt etablierten Patterns
- `scope`: component — Verfeinerung von REQ-L1-012
- `priority`: desired (unverändert)

**Akzeptanzkriterien (neu):**
1. TestRun kann mit 1..n TestCase-IDs erstellt werden — initialer Status aller Cases: 'Not Run'
2. Jeder TestCase im Run kann einzeln auf Passed/Failed/Blocked/Not Run gesetzt werden
3. Das aggregierte Lauf-Ergebnis wird automatisch berechnet (Passed = alle Passed, Failed = mindestens ein Failed, Partial = mindestens ein Blocked/Not Run)
4. TestRun enthält Zeitstempel (Start, Ende) und ausführende Instanz (z.B. CI-Job-ID)
5. TestRun ist via REST-API und MCP (test.create_run, test.update_result) vollständig CRUD-fähig

---

## Klarstellung: REQ-L1-036 — Test-Ergebnis-Einspeisung via API/MCP (v1.1)

**Neu bewertet:**
- `arch_impact: false` — Nutzt bestehende API-/MCP-Infrastruktur und Audit-Log; keine neue Architekturentscheidung
- `scope`: component — Verfeinerung von REQ-L1-012/035
- `priority`: desired (unverändert)

**Akzeptanzkriterien (neu):**
1. CI/CD-System sendet POST /api/v1/test-runs/{id}/results mit API-Key → Ergebnis wird protokolliert, HTTP 200
2. MCP-Tool test.record_result akzeptiert TestCase-ID + Status + optionaler Ausgabe-Payload
3. Fehlender/ungültiger API-Key → HTTP 401; Einspeisung wird nicht protokolliert
4. Jede Einspeisung erzeugt einen Audit-Log-Eintrag mit Client-Identität, TestRun-ID, Status und Zeitstempel
5. Gleichzeitige Einspeisungen verschiedener Pipelines in denselben TestRun werden serialisiert verarbeitet

---

## Klarstellung: REQ-L1-037 — Kommentar-Threads mit @Mention (v2.0)

**Neu bewertet:**
- `arch_impact: true` — Kommentar-Datenmodell, Thread-Struktur und @Mention-Notification erfordern neue Infrastruktur
- `arch_trigger`: "Kommentar-Datenmodell, Thread-Strukturierung, @Mention-Auflösung und In-App-Notification-System erfordern neue Infrastruktur-Komponenten"
- `scope`: system — neuer Subsystem-Bedarf (CommentService/NotificationService)
- `priority`: optional (unverändert)

**Akzeptanzkriterien (neu):**
1. Kommentar kann zu Requirement, ArchitectureElement und TestCase erstellt werden — als Top-Level-Kommentar oder als Antwort in einem bestehenden Thread
2. @Mention eines registrierten Nutzers löst eine In-App-Benachrichtigung für den genannten Nutzer aus
3. @Mention eines nicht registrierten Namens erzeugt einen Validierungshinweis, aber der Kommentar wird trotzdem gespeichert
4. Kommentar-Änderungen werden versioniert in der Audit-History erfasst
5. Kommentar-Threads sind via REST-API und MCP lesbar (artifact.get_comments)

---

## Klarstellung: REQ-L1-038 — Semantische Vektorsuche / RAG (v2.0)

**Neu bewertet:**
- `arch_impact: true` — Vektordatenbank, Embedding-Pipeline und Hybrid-Suche sind substantielle Infrastrukturentscheidungen
- `arch_trigger`: "Vektordatenbank-Auswahl, Embedding-Pipeline (Modell, Aktualisierungsstrategie), Hybrid-Suche (Vektor + Volltext) und Deployment-Integration"
- `scope`: system — neuer Subsystem-Bedarf (VectorSearchService)
- `priority`: optional (unverändert)

**Akzeptanzkriterien (neu):**
1. Natürlichsprachliche Query ('Welche Anforderungen betreffen die Authentifizierung?') liefert rankierte Ergebnisse mit Ähnlichkeits-Score
2. Query per Artefakt-ID liefert semantisch ähnliche Artefakte als 'Duplikat-Vorschläge'
3. Embeddings werden automatisch bei Artefakt-Erstellung und -Bearbeitung aktualisiert (maximale Verzögerung 5 Minuten)
4. Semantische Suche ist via UI-Suchfeld und MCP-Tool (artifact.semantic_search) nutzbar
5. Suchlatenz ≤ 2s für Workspaces mit bis zu 10.000 Artefakten

---

## Klarstellung: REQ-L1-039 — Item-Level-RBAC (v2.0)

**Neu bewertet:**
- `arch_impact: true` — Feingranulare Berechtigungsprüfung auf Artefaktebene erfordert Erweiterung des Autorisierungsmodells
- `arch_trigger`: "Feingranulare Berechtigungsprüfung auf Artefaktebene erfordert Erweiterung des Autorisierungsmodells und potenziell der Datenzugriffsschicht (Query-Filtering, Permission-Caching)"
- `scope`: system — erweitert AuthAndTenancySystem
- `priority`: optional (unverändert)

**Akzeptanzkriterien (neu):**
1. Admin konfiguriert: 'Nutzer X hat Lesezugriff auf Subsystem Y' → Nutzer X sieht nur Artefakte in Subsystem Y
2. Item-Level-Regel überschreibt keine Workspace-RBAC: Admin-Rechte auf Workspace-Ebene haben weiterhin Vorrang
3. Item-Level-Regel wird bei API-Zugriffen ausgewertet (keine UI-only-Beschränkung)
4. Konfiguration via UI (Berechtigungs-Editor) und API-Endpunkt
5. Performance: max. 10 % Overhead auf API-Response-Zeiten für Workspaces mit ≤ 100 Item-Level-Regeln

---

## Klarstellung: REQ-L1-040 — Visuelles Artefakt-Diff (v1.1)

**Neu bewertet:**
- `arch_impact: false` — Baut auf bestehender Versionierung und Audit-Infrastruktur auf; UI-Darstellung ist Implementierungsdetail
- `scope`: component — Verfeinerung von REQ-L1-011 (Audit-Trail) und REQ-L2-AS-? (Versionierung)
- `priority`: desired (unverändert)

**Akzeptanzkriterien (neu):**
1. REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
2. Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder pro Vergleich
3. GUI zeigt Diff mit visueller Hervorhebung (grün=hinzugefügt, rot=gelöscht, gelb=geändert)
4. Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
5. Markdown-Felder werden als Text-Diff dargestellt (kein strukturelles AST-Diff)

---

## Klarstellung: REQ-L1-041 — Visuelles Baseline-Diff (v1.1)

**Neu bewertet:**
- `arch_impact: false` — Baut auf L2-BL-02 (Baseline-Vergleich auf Datenebene) und bestehender API-Infrastruktur auf
- `scope`: component — Verfeinerung von REQ-L1-008 (Baselines)
- `priority`: desired (unverändert)

**Akzeptanzkriterien (neu):**
1. REST-API-Endpoint GET /baselines/{id_a}/diff/{id_b} liefert kategorisiertes Diff (added, modified, deleted)
2. Modified-Liste enthält Versions-Delta (Version in Baseline A → Version in Baseline B)
3. GUI zeigt Diff mit kategorisierter Liste und Navigation zwischen Kategorien
4. Vergleich kompatibler Scopes (document↔document, project↔project) ist möglich
5. Vergleich inkompatibler Scopes (document↔project) liefert klaren Fehlerhinweis

---

*Erstellt durch se-requirements-Agent | 2026-06-27*
*Phase 1 abgeschlossen — Übergabe an se-critic zur Qualitätsprüfung*
