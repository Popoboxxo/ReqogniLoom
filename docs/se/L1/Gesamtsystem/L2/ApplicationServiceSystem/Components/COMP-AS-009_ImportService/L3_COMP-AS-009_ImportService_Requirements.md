---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 ImportService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-009_ImportService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-014 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der ImportService führt Bulk-Importe von Requirements, ArchitectureElements und TestCases aus CSV-Dateien durch. Er validiert jede Zeile gegen das Datenmodell, meldet Fehler mit Zeilennummern und garantiert atomare Transaktionssemantik: Entweder alle validen Zeilen werden importiert, oder keine.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | Import-Request vom ApplicationService (CSV-Datei, Entity-Typ, Workspace-ID) |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer (Django ORM) |
| IF-AS-EXT-OUT-006 | output | event | Domain-Event-Publikation für AuditLog (via DomainEventBus, batch) |

---

## L3 Component-Anforderungen

### REQ-L3-IMP-001: CSV-Datei-Parsing und Validierung

Der ImportService SHALL CSV-Dateien zeilenweise parsen und folgende Validierungen für jede Zeile durchführen:
1. Erforderliche Felder sind vorhanden (gemäß Entity-Typ-Schema)
2. Feldwerte passen zu definierten Typen (string, integer, enum, UUID)
3. Längenbeschränkungen werden eingehalten
4. Referenzierte Parent-Artefakte existieren (falls parent_id angegeben)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] CSV wird nach RFC4180 geparst
- [ ] Ungültige Zeilen werden identifiziert mit Zeilennummer
- [ ] Error-Report enthält Feldname und Fehlerbeschreibung pro Zeile
- [ ] Validierung blockiert nicht andere Zeilen (Full Report)

**Interfaces:** IF-AS-EXT-IN-001
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-014
**Rationale:** Benutzerfreundliche Fehlerberichte ermöglichen schnelle Korrekturen.

---

### REQ-L3-IMP-002: Atomare Transaktionssemantik

Der ImportService SHALL alle validen Zeilen in einer einzigen Datenbank-Transaktion importieren. Falls eine beliebige Zeile nach Validierung zu einem DB-Fehler führt, SHALL der gesamte Import zurückgerollt werden (Rollback). Entweder alle oder keine Zeilen werden persistent.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Einsatz von `transaction.atomic()` umhüllt alle INSERT-Operationen
- [ ] DB-Fehler während Insert triggert Rollback der gesamten Transaktion
- [ ] Nach Rollback ist Datenbank unverändert
- [ ] Import-Report zeigt "All-or-Nothing" Status

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-014
**Rationale:** Datenkonsistenz und Audit-Klarheit.

---

### REQ-L3-IMP-003: UUID-Zuordnung für neue Entitäten

Der ImportService SHALL alle neu erstellten Entitäten mit regulären UUIDs versehen (nicht Batch-Placeholders). Falls die CSV bereits UUIDs enthält (uuid-Spalte), können diese übernommen werden; andernfalls generiert der Service neue UUIDs.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Neue Entitäten erhalten valid UUIDs (v4 oder äquivalent)
- [ ] Existierende UUIDs aus CSV werden geprüft (keine Duplikate)
- [ ] Duplikat-UUID wird als Validierungsfehler zurückgewiesen
- [ ] UUID-Länge und Format validiert

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-014
**Rationale:** Eindeutige Identifikation und Traceability.

---

### REQ-L3-IMP-004: Unterstützte Entity-Typen und Felder

Der ImportService SHALL folgende Entity-Typen und Feldmappings unterstützen:

**Requirements:** title, description, parent_id (optional), artifact_type
**ArchitectureElements:** element_type, title, description, artifact_link (optional)
**TestCases:** test_type, title, description, expected_result

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Jeder Entity-Typ hat dokumentiertes CSV-Schema
- [ ] Unbekannte Spalten werden ignoriert (Forward-Kompatibilität)
- [ ] Erforderliche Felder sind definiert pro Typ
- [ ] Enum-Werte werden gegen Whitelisten validiert

**Interfaces:** IF-AS-EXT-IN-001
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-014
**Rationale:** Klare Schnittstellen für Batch-Operationen.

---

### REQ-L3-IMP-005: Error-Report mit Zeilennummern

Nach Validierung und Rollback-Szenarien SHALL der ImportService einen detaillierten Error-Report zurückgeben mit:
- Zeilennummer (1-basiert) für jede fehlgeschlagene Zeile
- Feldname der Validierung fehlschlug
- Fehlerbeschreibung (z.B. "Invalid parent_id: UUID not found")
- Count: erfolgreiche vs. fehlgeschlagene Zeilen

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Report-Format ist strukturiert (JSON oder tabular)
- [ ] Zeilennummern sind präzise (Header nicht gezählt)
- [ ] Fehlerbeschreibungen sind aussagekräftig
- [ ] Report enthält Summary (z.B. "0/100 rows imported, 100 errors")

**Interfaces:** IF-AS-EXT-IN-001
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-014
**Rationale:** Benutzerfreundliche Fehleranalyse.

---

### REQ-L3-IMP-006: Batch-AuditLog-Einträge

Nach erfolgreichem Import SHALL der ImportService ein einziges batch-AuditLog-Event publikzieren (via DomainEventBus), das die Anzahl importierter Entitäten pro Typ und Workspace dokumentiert. Nicht einzelne Einträge pro Zeile (Aggregation zur Performance).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ein AuditLog-Event pro Import-Vorgang (nicht pro Zeile)
- [ ] Event enthält: entity_type, count, workspace_id, actor, timestamp
- [ ] AuditLog wird auch bei Rollback nicht geschrieben
- [ ] Batch-Aggregation reduziert AuditLog-Einträge um ≥99%

**Interfaces:** IF-AS-EXT-OUT-006
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-019
**Rationale:** Audit-Effizienz bei Bulk-Operationen.

---

### REQ-L3-IMP-007: Tenant-Isolation beim Import

Der ImportService SHALL garantieren, dass alle importierten Entitäten dem aktuellen Tenant zugeordnet werden. Falls die CSV Tenant-IDs enthält, werden diese ignoriert (Tenant wird von Auth-Context bestimmt).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant-ID wird aus Auth-Context extrahiert
- [ ] Alle importierten Entitäten erhalten diese Tenant-ID
- [ ] CSV-Tenant-Spalten werden überschrieben (nicht importiert)
- [ ] Keine Cross-Tenant-Imports möglich

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Multi-Tenancy.

---

### REQ-L3-IMP-008: Performance und Sizing-Limits

Der ImportService SHALL Importe mit bis zu 10.000 Zeilen handhaben:
- Max Import-Größe: 10.000 Zeilen
- Max Dateigrößse: 50MB
- Timeout: 60s pro Import
- Memory: ≤200MB Peak während Import

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 10.000-Zeilen-Import in ≤60s abgeschlossen
- [ ] Memory-Peak unter 200MB
- [ ] Oversized-Import wird mit Error abgewiesen
- [ ] Streaming-Parsing für große Dateien

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-023
**Rationale:** Skalierbarkeit und Zuverlässigkeit.

---

---

### REQ-L3-IMP-009: Workflow State Transitions (S-06)

Der ImportService MUSS alle Workflow-Statusübergänge (wie z.B. bei Requirements) über eine zentrale State-Machine (ApplicationService) leiten. Er DARF den Status (`status`) NICHT durch direkte Feldzuweisung ändern, da dies Policies und Audit-Logs umgehen würde.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von S-06.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-AS-043

---

## Traceability-Matrix: REQ-L3-IMP → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-IMP-001 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-002 | REQ-L2-AppSvc-014, REQ-L2-AppSvc-018 |
| REQ-L3-IMP-003 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-004 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-005 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-006 | REQ-L2-AppSvc-019 |
| REQ-L3-IMP-007 | REQ-L2-AppSvc-022 |
| REQ-L3-IMP-008 | REQ-L2-AppSvc-023 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-IMP-001 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-002 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-003 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-004 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-005 | REQ-L2-AppSvc-014 |
| REQ-L3-IMP-006 | REQ-L2-AppSvc-019 |
| REQ-L3-IMP-007 | REQ-L2-AppSvc-022 |
| REQ-L3-IMP-008 | REQ-L2-AppSvc-023 |

