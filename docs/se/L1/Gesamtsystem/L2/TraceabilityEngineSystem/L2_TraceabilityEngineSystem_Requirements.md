# L2 TraceabilityEngine Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** TraceabilityEngineSystem (ARCH-L1-007)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-003 (primär), REQ-L1-030 (primär), REQ-L1-001 (mitwirkend), REQ-L1-004 (mitwirkend), REQ-L1-008 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend), REQ-L1-015 (mitwirkend), REQ-L1-020 (mitwirkend), REQ-L1-025 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-TE-EXT-IN-001 | input | data | `query(artifact_id, direction, ctx)` von ApplicationService |
| IF-TE-EXT-IN-002 | input | data | `coverage(workspace_id, filters?, ctx)` von ApplicationService |
| IF-TE-EXT-IN-003 | input | data | TraceLink-CRUD von ApplicationService |
| IF-TE-EXT-IN-004 | input | data | `collect_trace_graph(workspace_id, ctx)` von BaselineService |
| IF-TE-EXT-OUT-001 | output | data | Daten-Persistenz-Interface an ARCH-L1-010 |

---

## L2 Subsystem-Anforderungen

### REQ-L2-TE-001: TraceLink-Verwaltung mit 6 Link-Typen
Die TraceabilityEngine SHALL TraceLinks zwischen Requirements, ArchitectureElements und TestCases verwalten. Unterstützte Link-Typen: `parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`. Source und Target MÜSSEN demselben Tenant angehören.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erstelle TraceLink (source=Req-A, target=Arch-B, type=`satisfies`) → TraceLink mit UUID
- [ ] TraceLink ohne Source → Fehler `"Source entity not found"`
- [ ] Cross-Tenant-Link → Fehler `"Cross-tenant link not allowed"`
- [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
- [ ] Delete → TraceLink entfernt

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-003, REQ-L1-015 (mitwirkend)
**Rationale:** TraceLink-CRUD mit 6 Link-Typen ist die Kernfunktion.

---

### REQ-L2-TE-002: Zyklenprävention für alle transitiven Link-Typen
Die TraceabilityEngine SHALL bei Single-Link-Operationen eine Eager-Zyklenprüfung vor der Persistenz durchführen. Die Prüfung MUSS alle 6 Link-Typen (`parent-child`, `derives-from`, `satisfies`, `implements`, `refines`, `verifies`) auf transitive Zyklen untersuchen. Bei Zyklus-Erkennung SHALL die Operation abgebrochen werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] A→B, B→C, dann C→A (parent-child) → Fehler `"Cycle detected in parent-child chain"`
- [ ] Req-A `derives-from` Req-B, Req-B `derives-from` Req-C, Req-C `derives-from` Req-A → Fehler `"Cycle detected in derives-from chain"`
- [ ] Nach abgelehntem Zyklus existieren die vorherigen Links weiterhin unverändert
- [ ] A→B, A→C (kein Zyklus, beliebiger Link-Typ) → beide OK
- [ ] Zyklenprüfung erfolgt vor der Persistenz (kein Zwischenzustand in der DB)

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-001
**Rationale:** REQ-L1-001 fordert hierarchische Strukturen „unter der Bedingung, dass Zyklen ausgeschlossen werden". Transitive Zyklen über andere Link-Typen als `parent-child` erzeugen dieselbe semantische Inkonsistenz.

---

### REQ-L2-TE-003: Atomare Batch-Operationen für TraceLinks mit globaler Zyklenprüfung
Die TraceabilityEngine SHALL Batch-Erstellung und Batch-Löschung in einer atomaren Persistenz-Transaktion unterstützen. Bei Teilfehler SHALL die gesamte Batch-Operation zurückgesetzt werden. Am Ende der Persistenz-Transaktion SHALL eine globale Zyklenprüfung den vollständigen Link-Graphen auf Zyklen über alle 6 Link-Typen prüfen. Bei erkanntem Zyklus SHALL die gesamte Transaktion zurückgesetzt werden und ein Fehlerbericht mit dem Zyklus-Pfad zurückgegeben werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Batch von 100 TraceLinks (zyklenfrei) → alle 100 persistiert
- [ ] Batch mit einem ungültigen Link → alle zurückgesetzt
- [ ] Batch von 100 TraceLinks in < 500ms
- [ ] Batch mit 100 Links, wobei der letzte Link einen Zyklus schließt → vollständiger Rollback mit Fehlerbericht, der den Zyklus-Pfad enthält (z.B. `"Cycle: Req-A → Req-B → Req-C → Req-A"`)
- [ ] Globale Zyklenprüfung wird einmalig am Ende der Persistenz-Transaktion ausgeführt (nicht pro Link)

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-003, REQ-L1-025 (mitwirkend)
**Rationale:** Decompose-Workflow erstellt mehrere parent-child-Links in einer Transaktion. Globale Zyklenprüfung am Transaktionsende ist effizienter als Eager-Prüfung pro Link bei Massenimporten und garantiert globale Zyklenfreiheit.

---

### REQ-L2-TE-004: Upstream/Downstream-Graph-Query
Die TraceabilityEngine SHALL Upstream- und Downstream-Queries für beliebige Artefakte unterstützen. Das Ergebnis SHALL alle direkt verbundenen Knoten mit Link-Typ-Annotation enthalten. Query SHALL in < 200ms (p95) bei bis zu 10.000 Items antworten.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `query_upstream(requirement_id)` → vollständiger Nachbar-Graph in ≤ 200ms (p95)
- [ ] `query_downstream(requirement_id)` → ≤ 200ms (p95)
- [ ] Ergebnis enthält Entity-ID, Entity-Typ, Link-Typ, Richtung
- [ ] Query-Timeout nach 5 Sekunden → Abbruch mit Fehler `"Query timeout"`

**Arch-Impact:** true
**Arch-Trigger:** "schnelle Graph-Traversal-Operationen (< 200ms) bei großen Datenmengen"

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-003, REQ-L1-026 (mitwirkend)
**Rationale:** REQ-L1-003 fordert Upstream/Downstream-Queries in < 200ms.

---

### REQ-L2-TE-005: Transitive Hüllen-Query (Impact-Analyse)
Die TraceabilityEngine SHALL transitive Hüllen berechnen — alle indirekt erreichbaren Knoten über mehrere Ebenen. Ergebnis SHALL Link-Typ, Richtung und Pfadtiefe enthalten. ≤ 200ms (p95) bei 10.000 Items.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Req-A `derives-from` Arch-B `implements` Comp-C → `query_downstream(Req-A, transitive=true)` → {Arch-B (depth=1), Comp-C (depth=2)}
- [ ] Transitive Query bei 10.000 Items → ≤ 200ms (p95)
- [ ] Query-Timeout nach 5 Sekunden → Abbruch mit Fehler `"Query timeout"`

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-003, REQ-L1-026 (mitwirkend)
**Rationale:** Impact-Analysen erfordern die vollständige Kette.

---

### REQ-L2-TE-006: Coverage-Berechnung (Requirement → Test-Abdeckung)
Die TraceabilityEngine SHALL die Test-Coverage berechnen: Prozentsatz der Requirements mit mindestens einem `verifies`-TraceLink zu einem TestCase. Ergebnis: Gesamtzahl, abgedeckte Anzahl, ungedeckte IDs, Prozent. ≤ 500ms bei 10.000 Requirements.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 10 Requirements, 7 mit verifies-Links → `{total: 10, covered: 7, uncovered: [...], percentage: 70.0}`
- [ ] Coverage für 10.000 Requirements → ≤ 500ms
- [ ] Leerer Workspace → `{total: 0, covered: 0, uncovered: [], percentage: 0.0}`

**Interfaces:**
- Incoming: IF-TE-EXT-IN-002
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-012, REQ-L1-003 (mitwirkend)
**Rationale:** REQ-L1-012 fordert Coverage-Tracking.

---

### REQ-L2-TE-007: Coverage-Filterung nach Artefakttyp und Link-Typ
Die TraceabilityEngine SOLLTE Coverage-Queries optional nach Artefakttyp und Link-Typ filterbar gestalten.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `coverage(workspace_id, artifact_type='ArchitectureElement', link_type='satisfies')` → gefilterter Report
- [ ] Performance: ≤ 500ms bei 10.000 Items

**Interfaces:**
- Incoming: IF-TE-EXT-IN-002
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-004 (mitwirkend), REQ-L1-012 (mitwirkend)
**Rationale:** Differenzierte Coverage-Reports für verschiedene Artefakttypen.

---

### REQ-L2-TE-008: Trace-Graph-Sammlung für Baseline-Snapshot
Die TraceabilityEngine SHALL auf Anfrage des BaselineService den vollständigen Trace-Graph eines Workspaces sammeln und serialisierbar zurückgeben. ≤ 500ms bei 10.000 Items.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Workspace mit 50 TraceLinks → Graph mit exakt 50 Links
- [ ] Graph maschinenlesbar serialisierbar
- [ ] Leerer Workspace → leerer Graph
- [ ] ≤ 500ms bei 10.000 Items
- [ ] Memory-Limit-Schutz: Bei zu großem Graph (z.B. > 100k Items) → strukturierter Fehler `"Payload too large"` statt Out-of-Memory-Absturz

**Interfaces:**
- Incoming: IF-TE-EXT-IN-004
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-008 (mitwirkend)
**Rationale:** BaselineService benötigt den Trace-Zustand für Snapshots.

---

### REQ-L2-TE-009: Referentielle Integrität bei Artefakt-Löschung
Die TraceabilityEngine SHALL bei Löschung eines Artefakts automatisch alle zugehörigen TraceLinks löschen (CASCADE). Atomar innerhalb derselben Transaktion.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Lösche Requirement mit 3 TraceLinks → alle 3 gelöscht
- [ ] Kein Query zeigt orphaned TraceLinks
- [ ] CASCADE Teil der Artefakt-Löschungstransaktion

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-003, REQ-L1-025 (mitwirkend)
**Rationale:** Orphaned TraceLinks würden Reports und Queries verfälschen.

---

### REQ-L2-TE-010: TraceLink-Audit-Metadaten
Jeder TraceLink SHALL Audit-Felder (`created_by`, `created_at`, `modified_by`, `modified_at`) besitzen. Für MCP-Operationen SHALL Agent-Client-Identität und API-Key (gehashed) erfasst werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLink via Standard-API → `created_by` = User-ID
- [ ] TraceLink via MCP → `created_by` = Agent-Client-ID
- [ ] Änderung → `modified_by`/`modified_at` aktualisiert, `created_by`/`created_at` unverändert

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-011 (mitwirkend), REQ-L1-003 (mitwirkend)
**Rationale:** Vollständige Protokollierung aller Änderungen.

---

### REQ-L2-TE-011: Tenant-Isolation für alle TraceLink-Operationen
Die TraceabilityEngine SHALL für alle Operationen sicherstellen, dass ausschließlich TraceLinks des aktiven Tenants sichtbar und manipulierbar sind.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant-1 erstellt TraceLink → Tenant-2 query → nicht sichtbar
- [ ] Tenant-2 versucht Delete → Fehler `"TraceLink not found"`
- [ ] Coverage-Report enthält nur Tenant-eigene TraceLinks

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001, IF-TE-EXT-IN-002, IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001

**Arch-Impact:** true
**Arch-Trigger:** "strikte logische Mandantenisolation für alle Lese- und Schreibzugriffe"


**Traceability:** REQ-L1-015, REQ-L1-003 (mitwirkend)
**Rationale:** Mandantenfähigkeit erfordert strikte Isolation aller Daten pro Tenant.

---

### REQ-L2-TE-012: TraceLink-Query-Performance-SLA
Die TraceabilityEngine SHALL Performance-SLAs einhalten: ≤ 200ms (p95) für Graph-Queries, ≤ 500ms (p95) für Coverage-Reports und Graph-Sammlungen — bei bis zu 10.000 Items und 50.000 TraceLinks.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Upstream/Downstream-Query: ≤ 200ms (p95)
- [ ] Transitive Query: ≤ 200ms (p95)
- [ ] Coverage-Report: ≤ 500ms (p95)
- [ ] Graph-Sammlung: ≤ 500ms (p95)
- [ ] Timeout-Strategie für alle Queries implementiert (z.B. Abbruch nach 5s) → strukturierter Fehler statt endlosem Blockieren

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001, IF-TE-EXT-IN-002, IF-TE-EXT-IN-004
- Outgoing: IF-TE-EXT-OUT-001

**Arch-Impact:** true
**Arch-Trigger:** "Performance-SLA-Garantien bei großem Datenbestand"


**Traceability:** REQ-L1-026, REQ-L1-003 (mitwirkend)
**Rationale:** Bündelt alle Performance-Aspekte der TraceabilityEngine.

---

### REQ-L2-TE-013: Verification Cross Reference Matrix (VCRM) Report-Generator
Die TraceabilityEngine SOLLTE einen VCRM-Report-Generator bereitstellen. Der Generator SHALL eine flache Matrix mit den Spalten `requirement_id`, `component_id`, `test_case_id`, `test_result` (Passed / Failed / Not Run) ausgeben. Die Matrix SHALL nach Baseline (Snapshot-Zeitpunkt) und Workspace filterbar sein. Export als CSV ist Pflicht; Export als PDF ist optional.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Geprüft von se-verifier. Traceability Tests (ohne PDF) erfolgreich.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `generate_vcrm(workspace_id, baseline_id?)` → Matrix mit korrekten Zeilen je Requirement-Component-TestCase-Kombination
- [ ] Zeile ohne TestCase-Verknüpfung → `test_result = "Not Run"`
- [ ] `baseline_id` angegeben → Matrix spiegelt Zustand zum Snapshot-Zeitpunkt wider
- [ ] Export als CSV → gültige CSV-Datei, herunterladbar
- [ ] Export als PDF → PDF-Datei (wenn implementiert)
- [ ] Leerer Workspace → leere Matrix (keine Fehler)

**Interfaces:**
- Incoming: IF-TE-EXT-IN-002
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-003 (primär), REQ-L1-012 (mitwirkend)
**Rationale:** SE-Reviewer benötigen eine kompakte Übersicht der vollständigen V&V-Abdeckung. Die VCRM ist etabliertes Werkzeug in ISO-15288-Projekten.

---

### REQ-L2-TE-014: Cross-Projekt-Link-CRUD
Die TraceabilityEngine SOLLTE TraceLinks erstellen, lesen, aktualisieren und löschen (CRUD) können, deren Source und Target unterschiedlichen Workspaces (Projekten) innerhalb desselben Tenants angehören.

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. Bestätigt als nicht implementiert.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] TraceLink mit Source in Workspace A und Target in Workspace B erfolgreich erstellt
- [ ] Link-Richtung und Typ bleiben domänen-übergreifend gültig
- [ ] Löschen eines der verknüpften Artefakte entfernt den Cross-Projekt-Link (CASCADE)

**Interfaces:**
- Incoming: IF-TE-EXT-IN-003
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-030
**Rationale:** Ermöglicht projektübergreifende Verknüpfungen (z.B. Core-Bibliothek-Requirement zu Produkt-Requirement).

---

### REQ-L2-TE-015: Cross-Projekt-Graph-Query
Die TraceabilityEngine SOLLTE Upstream-, Downstream- und Coverage-Queries über Projektgrenzen hinweg auflösen. Wenn Cross-Projekt-Links existieren, SHALL die Query die Artefakte des verknüpften Workspaces einbeziehen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Geprüft von se-verifier. Code vorhanden, aber keine Tests gefunden.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Upstream-Query für Artefakt in Workspace A gibt verknüpfte Artefakte aus Workspace B zurück
- [ ] Graph-Resultate kennzeichnen den Workspace jedes Knotens eindeutig
- [ ] Performance ≤ 300ms (p95) für Cross-Projekt-Queries
- [ ] Query-Timeout nach 5 Sekunden → Abbruch mit Fehler `"Query timeout"`

**Interfaces:**
- Incoming: IF-TE-EXT-IN-001, IF-TE-EXT-IN-002
- Outgoing: IF-TE-EXT-OUT-001


**Traceability:** REQ-L1-030
**Rationale:** Traceability- und Impact-Analysen müssen Systemgrenzen überschreiten können, wenn Abhängigkeiten existieren.

---

## Traceability-Matrix: REQ-L2-TE → REQ-L1

| REQ-L2-TE | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-TE-001 | REQ-L1-003 | REQ-L1-015 |
| REQ-L2-TE-002 | REQ-L1-001 | — |
| REQ-L2-TE-003 | REQ-L1-003 | REQ-L1-025 |
| REQ-L2-TE-004 | REQ-L1-003 | REQ-L1-026 |
| REQ-L2-TE-005 | REQ-L1-003 | REQ-L1-026 |
| REQ-L2-TE-006 | REQ-L1-012 | REQ-L1-003 |
| REQ-L2-TE-007 | REQ-L1-004 | REQ-L1-012 |
| REQ-L2-TE-008 | REQ-L1-008 | — |
| REQ-L2-TE-009 | REQ-L1-003 | REQ-L1-025 |
| REQ-L2-TE-010 | REQ-L1-011 | REQ-L1-003 |
| REQ-L2-TE-011 | REQ-L1-015 | REQ-L1-003 |
| REQ-L2-TE-012 | REQ-L1-026 | REQ-L1-003 |
| REQ-L2-TE-013 | REQ-L1-003 | REQ-L1-012 |
| REQ-L2-TE-014 | REQ-L1-030 | — |
| REQ-L2-TE-015 | REQ-L1-030 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-TE | 15 |
| Mandatory | 11 |
| Desired | 4 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 10 |
| Abgedeckte REQ-L1 (mitwirkend) | 3 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Trace → REQ-L2-TE, Template-Standardisierung*
*Designation: component (terminal) — decomposition_status: terminal*

---

## Erweiterung v2 — REQ-L2-TE-016..017 (aus REQ-L1-043 und REQ-L1-047)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-030 → REQ-L1-043, REQ-L0-035 → REQ-L1-047

---

### REQ-L2-TE-016: Suspect-Link-Propagation Engine

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent. Die TraceabilityEngine hat aktuell keinen Event-basierten Änderungslistener.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. Bestätigt als nicht implementiert.

Die TraceabilityEngine MUSS beim Empfang eines `requirement.updated`-Events automatisch
alle direkt und transitiv via `derives-from`- und `parent-child`-Links verbundenen
Artefakte (Requirements, TestCases, Architecture Elements) mit dem Status `suspect` markieren.
Die Propagierung MUSS über den gesamten TraceLink-Graphen erfolgen (transitiv, Ebenen-übergreifend).
Der `suspect`-Status MUSS in der Datenbank persistiert und über die API abfragbar sein.
Ein separater Endpunkt MUSS die Bestätigung des `suspect`-Status (→ `reviewed`) ermöglichen.

**Schnittstellen:**
- Input: `requirement.updated`-Event (intern, via Message-Bus)
- Output: Batch-Update aller abhängigen Artefakte auf `suspect`
- API: `PATCH /tracelinks/{id}/confirm-review` → Status `reviewed`
- API: `GET /requirements?suspect=true` → gefilterte Liste

**Akzeptanzkriterien:**
- AC1: `requirement.updated`-Event löst Propagierung in < 2 s aus (für Graphen bis 1000 Knoten)
- AC2: Transitiver Graph wird vollständig traversiert (Tiefensuche oder BFS)
- AC3: Zirkuläre Abhängigkeiten werden erkannt und nicht infinit traversiert
- AC4: `suspect`-Bestätigung schreibt Audit-Log-Eintrag (Nutzer, Zeitstempel, REQ-ID)
- AC5: API-Filter `?suspect=true` gibt nur suspect-Artefakte zurück

**Verifikationsmethode:** Integrationstest — Anforderung ändern, Graph-Traversierung prüfen
**Verifikiert durch:** L2-TE-Test-016
**Abgeleitet von:** REQ-L1-043
**Übergeordnete REQ-L0:** REQ-L0-030

---

### REQ-L2-TE-017: Cross-Level-TraceLink-Typ mit Begründungspflicht

**Implementation State:** Not Implemented
**Review Findings:** TraceLink-Datenmodell kennt aktuell keinen `link_type`-Wert `cross-level`. Erweiterung des Enums erforderlich.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. Bestätigt als nicht implementiert.

Die TraceabilityEngine MUSS einen neuen TraceLink-Typ `cross-level` unterstützen,
der Artefakte direkt über mehr als eine Kaskaden-Ebene verbindet (z. B. L0 → L2 ohne L1).
Ein `cross-level`-Link MUSS bei der Erstellung eine Pflichtbegründung (Freitext,
min. 20 Zeichen) enthalten — andernfalls wird die Anfrage abgelehnt (HTTP 422).
`cross-level`-Links MÜSSEN in API-Responses mit einem Marker-Feld `is_cross_level: true`
ausgewiesen sein, damit UI und AI-Agenten sie distinkt darstellen können.
Ein Report-Endpunkt MUSS alle `cross-level`-Links eines Workspaces ohne Begründung auflisten.

**Schnittstellen:**
- `POST /tracelinks` — Körper: `{ "link_type": "cross-level", "justification": "..." }`
- Validierung: `justification` Pflicht wenn `link_type == "cross-level"`, sonst HTTP 422
- `GET /tracelinks?type=cross-level` — gefilterte Liste
- `GET /reports/cross-level-links?workspace_id=...` — Report fehlender Begründungen

**Akzeptanzkriterien:**
- AC1: `cross-level`-Link ohne Begründung → HTTP 422 mit klarem Fehlertext
- AC2: `cross-level`-Link mit Begründung → HTTP 201, `is_cross_level: true` in Response
- AC3: Report-Endpunkt listet alle `cross-level`-Links ohne oder mit leerer Begründung
- AC4: Standard-Links sind unverändert (kein Breaking Change)

**Verifikationsmethode:** API-Test (positiv + negativ) + Report-Test
**Verifikiert durch:** L2-TE-Test-017
**Abgeleitet von:** REQ-L1-047
**Übergeordnete REQ-L0:** REQ-L0-035

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-TE-016..017 aus REQ-L1-043, REQ-L1-047)*

---

## Erweiterung v8 — REQ-L2-TE-018 (Ebenen-Modell)

> **Datum:** 2026-07-02 | **Quelle:** REQ-L1-060

---

### REQ-L2-TE-018: TraceLink allocated-to + Allocation-Coverage Reporter

Die TraceabilityEngine MUSS den neuen Link-Typ `allocated-to` (Requirement → ArchitectureElement, 1:1) unterstützen. Der Typ MUSS über den Enum-Validator registriert werden. Das System MUSS einen Allocation-Coverage Report generieren, der den Zuweisungsstatus von Anforderungen gruppiert nach Level liefert.

**Akzeptanzkriterien:**
- AC1: `allocated-to` als gültiger link_type registriert
- AC2: API GET /requirements/{id}/allocation liefert Owner-Architektur-Element
- AC3: Coverage Report generiert Metriken (covered, uncovered) pro Level

**Verifikationsmethode:** Unit-Test + Integrationstest
**Abgeleitet von:** REQ-L1-060
**Implementation State:** Backlog
**Review Findings:** Nicht implementiert.
**Test Status:** Missing

---

### REQ-L2-TE-019: TraceLink Read-Model mit rekursiven CTE-Abfragen

Die `traceability/models.py`-Schicht MUSS ein Read-Modell für Traceability-Abfragen bereitstellen. Dieses Read-Modell MUSS drei dedizierte Query-Methoden via rekursiver PostgreSQL-CTEs implementieren: (a) Impact-Analyse (welche Artefakte sind betroffen, wenn sich X ändert?), (b) Vorwärts- und Rückwärtspfadsuche über den TraceLink-Graphen, (c) Zykluserkennung im Trace-Graphen. Alle drei Methoden MÜSSEN über einen REST-Endpunkt und ein MCP-Tool aufrufbar sein.

**Implementation State:** Not Implemented
**Review Findings:** `traceability/models.py` ist ein leerer Stub ohne Read-Modell. Impact-Analyse, Pfadsuche und Zykluserkennung fehlen vollständig.
**Test Status:** Missing
**Remarks:** Neu aufgenommen 2026-07-10.

**Domain:** software
**Priority:** must
**Acceptance Criteria:**
- [ ] `TraceabilityReadService.impact(artifact_id, max_depth=5)` gibt alle transitiv betroffenen Artefakte zurück (rekursive CTE, Tiefenlimit konfigurierbar)
- [ ] `TraceabilityReadService.path(source_id, target_id, direction)` gibt den kürzesten Pfad zwischen zwei Artefakten zurück (`direction` ∈ {forward, backward, both})
- [ ] `TraceabilityReadService.detect_cycles(workspace_id)` gibt alle zyklischen TraceLink-Ketten zurück; bei einem zyklusfreien Graphen ist das Ergebnis leer
- [ ] REST-Endpunkt `GET /workspaces/{id}/traceability/impact/{artifact_id}` liefert Impact-Analyse als JSON
- [ ] MCP-Tool `traceability.impact` und `traceability.path` sind registriert und nutzbar
- [ ] Alle drei Methoden sind performant bei bis zu 10.000 TraceLinks (p95 < 500 ms)

**Traceability:** REQ-L1-003
**Rationale:** Ohne Read-Modell und CTE-basierte Graphabfragen ist Impact-Analyse und Zykluserkennung nur durch ineffiziente ORM-Iterationen möglich, die bei realen Trace-Graphen versagen.

---

### REQ-L2-TE-020: ADR ↔ ArchitectureElement TraceLink

Das System MUSS einen TraceLink-Typ zwischen ADR und ArchitectureElement unterstützen (Erweiterung der bestehenden 8 Typen oder neuer Typ); UI-Integration in AdrEditor und ArchitectureEditor; REST und MCP exponiert.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** should
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3b.

**Traceability:** REQ-L1-003


## Master Traceability Matrix

| REQ-L2 | Abgeleitet von REQ-L1 |
|---------|----------------------|
| REQ-L2-TE-001 | REQ-L1-003, REQ-L1-015 (mitwirkend) |
| REQ-L2-TE-002 | REQ-L1-001 |
| REQ-L2-TE-003 | REQ-L1-003, REQ-L1-025 (mitwirkend) |
| REQ-L2-TE-004 | REQ-L1-003, REQ-L1-026 (mitwirkend) |
| REQ-L2-TE-005 | REQ-L1-003, REQ-L1-026 (mitwirkend) |
| REQ-L2-TE-006 | REQ-L1-012, REQ-L1-003 (mitwirkend) |
| REQ-L2-TE-007 | REQ-L1-004 (mitwirkend), REQ-L1-012 (mitwirkend) |
| REQ-L2-TE-008 | REQ-L1-008 (mitwirkend) |
| REQ-L2-TE-009 | REQ-L1-003, REQ-L1-025 (mitwirkend) |
| REQ-L2-TE-010 | REQ-L1-011 (mitwirkend), REQ-L1-003 (mitwirkend) |
| REQ-L2-TE-011 | REQ-L1-015, REQ-L1-003 (mitwirkend) |
| REQ-L2-TE-012 | REQ-L1-026, REQ-L1-003 (mitwirkend) |
| REQ-L2-TE-013 | REQ-L1-003 (primär), REQ-L1-012 (mitwirkend) |
| REQ-L2-TE-014 | REQ-L1-030 |
| REQ-L2-TE-015 | REQ-L1-030 |
| REQ-L2-TE-016 | REQ-L1-043 |
| REQ-L2-TE-017 | REQ-L1-047 |
| REQ-L2-TE-018 | REQ-L1-060 |
| REQ-L2-TE-019 | REQ-L1-003 |
| REQ-L2-TE-020 | REQ-L1-003 |

