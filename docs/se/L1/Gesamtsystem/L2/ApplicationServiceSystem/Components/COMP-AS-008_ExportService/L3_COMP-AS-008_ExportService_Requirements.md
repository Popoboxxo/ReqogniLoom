---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 ExportService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-008_ExportService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-006, REQ-L2-AppSvc-007, REQ-L2-AppSvc-016 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der ExportService erzeugt exportierbare Darstellungen (JSON, CSV, PDF) für Requirements, ArchitectureElements, TestCases und TraceLinks. Er arbeitet mit verschiedenen Scopes (Workspace, einzelnes Artefakt, Baseline) und bettet das aktive Terminologie-Profil als Metadatum ein. PDF-Exports enthalten zusätzlich formatierte Reports und Traceability-Matrizen.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | Export-Request vom ApplicationService (format, scope, workspace_id, artifact_id) |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer |
| IF-AS-EXT-OUT-004 | output | data | Präset-Profil abrufen von PresetConfigEngine |
| IF-AS-EXT-OUT-003 | output | data | TraceLink-Queries an TraceabilityEngine |

---

## L3 Component-Anforderungen

### REQ-L3-EXP-001: JSON-Export mit Terminologie-Metadatum

Der ExportService SHALL Requirements, ArchitectureElements und TestCases im JSON-Format exportieren mit eingebettetem aktiven Terminologie-Profil der Workspace.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] JSON-Export enthält `metadata.terminology_profile` als Top-Level-Feld
- [ ] Alle Entitäten in flacher oder verschachtelter Struktur verfügbar
- [ ] Export von 1.000 Anforderungen in ≤5s abgeschlossen
- [ ] Scope-Parameter (workspace / artifact) wird korrekt berücksichtigt
- [ ] Gültiges JSON ohne Encoding-Fehler

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007, IF-AS-EXT-OUT-004
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-006, REQ-L2-AppSvc-007
**Rationale:** JSON ist Standard für maschinelle Integration und Agenten-Anbindung.

---

### REQ-L3-EXP-002: CSV-Export mit Terminologie-Profil

Der ExportService SHALL Requirements, ArchitectureElements und TestCases im CSV-Format exportieren. Das aktive Terminologie-Profil SHALL als Kommentar in der ersten Zeile eingebettet sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] CSV-Header reflektiert Feldnamen korrekt
- [ ] Terminologie-Profil-Kommentar in Zeile 1: `# terminology_profile: <profile_name>`
- [ ] Spezielle Zeichen werden korrekt escaped (Kommata, Anführungszeichen, Zeilenumbrüche)
- [ ] Export von 1.000 Anforderungen in ≤5s abgeschlossen
- [ ] CSV-Datei ist mit Excel/LibreOffice öffnbar

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007, IF-AS-EXT-OUT-004
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-006, REQ-L2-AppSvc-007
**Rationale:** CSV ist Standard für Tabellenkalkulation und Massenimporte.

---

### REQ-L3-EXP-003: Scope-basierte Export-Filterung

Der ExportService SHALL exports auf Basis des scope-Parameters filtern:
- `scope: workspace` → alle Entitäten der Workspace
- `scope: artifact` → nur das angegebene Artefakt und seine Kinder

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Workspace-scope liefert alle Entitäten incl. Hierarchie
- [ ] Artifact-scope liefert nur subtree des angegebenen Artifacts
- [ ] Tenant-Isolation wird respektiert (kein Cross-Tenant-Export)
- [ ] Ungültiger Artifact-ID wird mit Error abgewiesen

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-006
**Rationale:** Granulare Kontrolle über Export-Umfang.

---

### REQ-L3-EXP-004: PDF-Report-Export

Der ExportService SHALL PDF-Reports für folgende Scopes erzeugen:
- Requirement-Dokument (formatiertes Dokument mit Metadata, Workflow-State, Audit-Geschichte)
- Traceability-Matrix (Tabelle mit Source→Target-Links)
- Coverage-Report (TestCase-Abdeckung nach Requirements)

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] PDF enthält Title-Page mit Workspace-Name, Baseline-Referenz, Datum
- [ ] Requirement-Dokument listet alle Requirements mit Eigenschaften
- [ ] Traceability-Matrix zeigt Source→Target-Links strukturiert
- [ ] Coverage-Report zeigt Prozentsatz abgedeckter Requirements
- [ ] PDF ist maschinenlesbar (Text, nicht Bild)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007, IF-AS-EXT-OUT-003
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-016
**Rationale:** PDF-Reports sind Standard für SE-Übergaben und Compliance.

---

### REQ-L3-EXP-005: TraceLink-Einbindung im Export

Der ExportService SHALL TraceLinks im JSON- und CSV-Export einbeziehen und im PDF-Report als separate Traceability-Matrix rendern.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] JSON-Export enthält `tracelinks` als Array mit source_id, target_id, link_type
- [ ] CSV-Export hat separate Zeilen für TraceLinks (mit Spalten: source_id, target_id, link_type)
- [ ] PDF-Matrix zeigt alle Link-Typen mit Count
- [ ] TraceLinks werden von TraceabilityEngine abgefragt

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007, IF-AS-EXT-OUT-003
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-006
**Rationale:** Traceability ist kernaler Bestandteil von Requirements-Management-Exports.

---

### REQ-L3-EXP-006: Baseline-Referenzen im Export

Falls der Export über eine Baseline-ID referenziert wird, SHALL der ExportService das Snapshot-JSON aus der Baseline einfügen und als Vergleich-Baseline im Metadatum verfügbar machen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Baseline-ID wird akzeptiert als optionaler Parameter
- [ ] Baseline-Snapshot wird im JSON als `metadata.baseline_snapshot` eingebettet
- [ ] Baseline-Metadaten (Ersteller, Datum, Anmerkungen) sind included
- [ ] Non-existent-Baseline wird mit Error abgewiesen

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-011
**Rationale:** Versionsvergleich und Compliance-Nachweise.

---

### REQ-L3-EXP-007: Performance und Ressourcen-Limiting

Der ExportService SHALL Exports mit großen Mengen (>10.000 Entitäten) handhaben ohne Server-Absturz oder Out-Of-Memory:
- Streaming für CSV und JSON (nicht vollständiges Laden in RAM)
- Timeout: 30s max für einen Export
- Max Export-Größe: 500MB

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] CSV/JSON wird gestreamt, nicht als Ganzes gepuffert
- [ ] Export >10.000 Items schließt in ≤30s ab
- [ ] Server-Memory bleibt unter 500MB Peak bei 500MB Export
- [ ] Oversized-Export wird mit Error abgewiesen

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-023
**Rationale:** Skalierbarkeit und Zuverlässigkeit.

---

### REQ-L3-EXP-008: Fehlerbehandlung und Reporting

Bei Export-Fehlern (z.B. Datenbank-Timeout, ungültiger Scope) SHALL der ExportService:
- Strukturierten Error mit Fehlermeldung zurückgeben
- Kein partieller Export zurückgeben
- Optional: Error-Log mit Kontext schreiben

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Fehler enthalten aussagekräftige Nachricht
- [ ] Keine Rückgabe von Halb-Exports
- [ ] HTTP-Statuscode reflektiert Fehler (400, 404, 500)
- [ ] Error-Details enthalten keine internen Stack-Traces

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-006
**Rationale:** Benutzerfreundlichkeit und Debugging-Unterstützung.

---

---

### REQ-L3-EXP-009: Soft-Delete Filtering & Pagination (S-07, S-16, S-17)

Der ExportService MUSS beim Iterieren über Entitäten sicherstellen, dass als `deleted_at != null` markierte Entitäten strikt aus dem Export ausgeschlossen werden. Zudem MÜSSEN interne Felder und Secrets herausgefiltert werden, bevor exportiert wird. Die Datenbankabfragen MÜSSEN paginiert erfolgen (`OFFSET`/`LIMIT`), um Memory-OOMs zu vermeiden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von S-07, S-16, S-17.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-AS-043, REQ-L2-AS-045

---

## Traceability-Matrix: REQ-L3-EXP → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-EXP-001 | REQ-L2-AppSvc-006, REQ-L2-AppSvc-007 |
| REQ-L3-EXP-002 | REQ-L2-AppSvc-006, REQ-L2-AppSvc-007 |
| REQ-L3-EXP-003 | REQ-L2-AppSvc-006 |
| REQ-L3-EXP-004 | REQ-L2-AppSvc-016 |
| REQ-L3-EXP-005 | REQ-L2-AppSvc-006 |
| REQ-L3-EXP-006 | REQ-L2-AppSvc-011 |
| REQ-L3-EXP-007 | REQ-L2-AppSvc-023 |
| REQ-L3-EXP-008 | REQ-L2-AppSvc-006 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-EXP-001 | REQ-L2-AppSvc-006, REQ-L2-AppSvc-007 |
| REQ-L3-EXP-002 | REQ-L2-AppSvc-006, REQ-L2-AppSvc-007 |
| REQ-L3-EXP-003 | REQ-L2-AppSvc-006 |
| REQ-L3-EXP-004 | REQ-L2-AppSvc-016 |
| REQ-L3-EXP-005 | REQ-L2-AppSvc-006 |
| REQ-L3-EXP-006 | REQ-L2-AppSvc-011 |
| REQ-L3-EXP-007 | REQ-L2-AppSvc-023 |
| REQ-L3-EXP-008 | REQ-L2-AppSvc-006 |

