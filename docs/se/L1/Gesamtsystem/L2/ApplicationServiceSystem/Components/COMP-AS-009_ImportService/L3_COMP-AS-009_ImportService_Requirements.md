---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 ImportService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-009_ImportService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der ImportService führt Bulk-Importe von Artefakten (Requirements, ArchitectureElements, TestCases) aus CSV-Dateien durch. Er validiert jede Zeile gegen das Entity-Datenmodell und meldet Fehler mit Zeilennummern. Der Service garantiert atomare Transaktionssemantik: Entweder alle validen Zeilen werden importiert, oder keine. Benutzerdefinierte UUIDs werden akzeptiert; andernfalls werden neue UUIDs generiert. Batch-AuditLog-Events werden nach erfolgreichem Import publiziert.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ImportService` (Klasse):** Orchestrator für Bulk-Importe (`import_csv(csv_file, entity_type, workspace_id, auth_context) → ImportReport`).
  - Parsed CSV nach RFC4180
  - Validiert jede Zeile gegen Entity-Schema
  - Sammelt Error-Report für fehlgeschlagene Zeilen
  - Führt valide Zeilen in atomarer Transaktion aus
  - Publiziert Batch-AuditLog-Event bei Erfolg
  - Gibt ImportReport mit Summary und Fehlerliste zurück

- **`CSVParser` (Klasse):** RFC4180-konformer CSV-Parser mit Zeilennummer-Tracking.

- **`EntityValidator` (Klasse):** Validiert einzelne Zeilen gegen Entity-Typ-Schema (Requirements, ArchitectureElements, TestCases). Prüft: erforderliche Felder, Feldtypen, Längenbeschränkungen, UUID-Referenzen.

- **`ImportReport` (DTO):** summary (total_rows, successful, failed), errors (list of {row_number, field_name, error_message}), import_status (success/failure).

- **`CSVRow` (DTO):** Repräsentation einer CSV-Zeile mit Feldwerten und Zeilennummer.

### 2.2 Datenstrukturen

- **Entity-Schema-Definition:** Dokumentiert erforderliche Felder, Typen (string, integer, enum, UUID), Längenbeschränkungen pro Entity-Typ (Requirements, ArchitectureElements, TestCases).

- **Fehler-Sammler:** Liste von {row_number, field_name, error_message} für jeden Validierungsfehler.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-IMP-001 (CSV-Parsing und Validierung) | CSVParser.parse() zeilenweise gemäß RFC4180. Für jede Zeile: EntityValidator.validate(row, entity_type) prüft (1) erforderliche Felder vorhanden, (2) Feldwerte passen zu Typ/Enum, (3) Längenbeschränkungen, (4) Parent-Artefakte existieren. Error-Report mit Zeilennummer und Feldname für jeden Fehler. Validierung blockiert nicht andere Zeilen (Full Report). |
| REQ-L3-IMP-002 (Atomare Transaktionssemantik) | `transaction.atomic()` umhüllt alle INSERT-Operationen. Nach Validierung aller Zeilen: Falls Fehler gefunden → kein INSERT, Rollback. Falls valide Zeilen → alle in einer Transaktion insertten. Bei DB-Fehler: Rollback der gesamten Transaktion. Status: All-or-Nothing. |
| REQ-L3-IMP-003 (UUID-Zuordnung) | Falls CSV hat uuid-Spalte: nutze diese UUID (geprüft auf Duplikate). Andernfalls: generiere neue UUID (v4). Duplikat-UUID → Validierungsfehler, Zeile blockiert. UUID-Format validiert (36 Zeichen, RFC4122). |
| REQ-L3-IMP-004 (Unterstützte Entity-Typen) | Dokumentierte CSV-Schemata für: Requirements (title, description, parent_id, artifact_type); ArchitectureElements (element_type, title, description, artifact_link); TestCases (test_type, title, description, expected_result). Unbekannte Spalten ignoriert (Forward-Kompatibilität). Enum-Werte gegen Whitelist validiert. |
| REQ-L3-IMP-005 (Error-Report) | Nach Validierung: Report mit {row_number [1-basiert], field_name, error_description}. Format: strukturiertes JSON oder Tabelle. Summary: "0/100 rows imported, 100 errors" oder "100/100 rows imported, 0 errors". Zeilennummern sind präzise (Header nicht gezählt). |
| REQ-L3-IMP-006 (Batch-AuditLog-Events) | Bei erfolgreichen Import: single AuditLog-Event via DomainEventBus mit (entity_type, count, workspace_id, actor, timestamp). Event wird nach Commit publiziert (post_commit Hook). Ein Event pro Import-Vorgang (nicht pro Zeile). AuditLog wird bei Rollback nicht geschrieben. |
| REQ-L3-IMP-007 (Tenant-Isolation) | Tenant-ID wird aus Auth-Context extrahiert. Alle Artefakte erhalten diese Tenant-ID (unabhängig von CSV-Inhalt). CSV-Tenant-Spalten werden ignoriert/überschrieben. Keine Cross-Tenant-Imports möglich. |
| REQ-L3-IMP-008 (Performance und Sizing) | Streaming-CSV-Parser für große Dateien (nicht vollständiges Laden in RAM). Max 10.000 Zeilen, Max 50MB Dateigröße. Timeout 60s pro Import. Memory-Peak < 200MB. 10.000-Zeilen-Import in ≤60s. Oversized-Import → Error. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API Endpoint `/import` mit multipart form (csv_file, entity_type, workspace_id).

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-007:** INSERT/SELECT Queries an PersistenceLayer (Django ORM) für Entitäten und Parent-ID-Validierung.
  - **IF-AS-EXT-OUT-006:** Publikation Batch-AuditLog-Event via DomainEventBus nach erfolgreichem Import.

---

## 5. Architectural Rationale

**ADR-L3-IMP-01 — Zwei-Pass-Validierung (Full Report vor Insert)**

*Entscheidung:* Zuerst alle Zeilen validieren und Error-Report sammeln, dann (bei 0 Fehlern) alle validen Zeilen insertten.

*Rationale:* Benutzer erhält vollständigen Error-Report auf einmal, kann alle Fehler korrigieren und erneut importieren. Alternative: Zeile-für-Zeile-Validierung mit Insert → bei Fehler in Zeile 500 sind Zeilen 1-499 bereits inserted; Rollback notwendig, Benutzer sieht aber nur einen Fehler auf einmal (iteratives Debugging). **Abgelehnt**: User Experience ist schlecht und Rollback-Overhead ist hoch.

*Erfüllt Trigger:* REQ-L3-IMP-001, REQ-L3-IMP-005 (Full Error Report).

---

**ADR-L3-IMP-02 — Atomare Transaktion mit All-or-Nothing-Semantik**

*Entscheidung:* Alle validen Zeilen werden in einer einzigen Datenbank-Transaktion insertted. Fehler in einer Zeile (z.B. Unique-Constraint-Verletzung nach Validierung) triggert Rollback aller Inserts.

*Rationale:* Verhindert Partial-Import-Zustand. Wenn z.B. Zeilen 1-499 erfolgreich inserted sind, aber Zeile 500 fehlschlägt → Datenbank ist in inkonsistentem Zustand (Hierarchie unterbrochen, wenn parent_id-Constraints vorhanden). All-or-Nothing garantiert Datenintegrität. Alternative: Partial Import akzeptieren → Benutzer muss manuell Cleanup durchführen. **Abgelehnt**: Datenkonsistenz ist kritisch.

*Erfüllt Trigger:* REQ-L3-IMP-002 (atomare Transaktionssemantik).

---

**ADR-L3-IMP-03 — Batch-AuditLog statt Per-Row-Audit**

*Entscheidung:* Ein einziges AuditLog-Event wird nach erfolgreichem Import publiziert, nicht ein Event pro Zeile.

*Rationale:* 10.000-Zeilen-Import würde 10.000 AuditLog-Events erzeugen → Datenbank-Überlastung. Batch-AuditLog (ein Event mit count=10.000) ist effizienter. Detailanforderungen (welche exakten Zeilen?) können über Import-Report oder Transaktions-ID geprüft werden. Alternative: Pro-Row-Audit für maximale Granularität → 99%+ AuditLog-Einträge sind Imports, nicht operationale Probleme. **Abgelehnt**: Batch-Aggregation ist praktischer für Compliance ohne Overhead.

*Erfüllt Trigger:* REQ-L3-IMP-006 (Batch-AuditLog).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
