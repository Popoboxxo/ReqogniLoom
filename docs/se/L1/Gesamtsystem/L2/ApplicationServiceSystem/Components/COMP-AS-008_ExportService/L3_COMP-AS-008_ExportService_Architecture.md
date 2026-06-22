---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 ExportService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-008_ExportService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der ExportService erzeugt exportierbare Darstellungen (JSON, CSV, PDF) für alle Artefakt-Typen (Requirements, ArchitectureElements, TestCases, Baselines, TraceLinks). Er arbeitet mit verschiedenen Scopes (Workspace, Artefakt, Baseline) und bettet das aktive Terminologie-Profil als Metadatum ein. PDF-Exports werden formatiert mit Reports und Traceability-Matrizen. Der Service implementiert Streaming-Parsing für große Exporte (>10.000 Items).

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ExportService` (Klasse):** Orchestrator für Export-Operationen (`export(format, scope, workspace_id, artifact_id=None, baseline_id=None) → Stream|File`).
  - Validiert Export-Parameter (scope, workspace_id)
  - Lädt Artefakte aus PersistenceLayer (gefiltert nach Scope)
  - Lädt aktives Terminologie-Profil von PresetConfigEngine
  - Delegiert Rendering an spezifische Exporter (JSONExporter, CSVExporter, PDFExporter)
  - Streamt Ausgabe (nicht vollständiges Laden in RAM)

- **`JSONExporter` (Klasse):** Serialisiert Artefakte und TraceLinks zu JSON mit Terminologie-Metadatum. Streaming JSON-Array-Ausgabe.

- **`CSVExporter` (Klasse):** Erzeugt CSV mit Header und Terminologie-Kommentar in Zeile 1. RFC4180-konform mit Escaping.

- **`PDFExporter` (Klasse):** Erzeugt formatierte PDF-Reports (Title-Page, Requirement-Dokument, Traceability-Matrix, Coverage-Report). Nutzt extern verfügbare PDF-Library (z.B. reportlab, weasyprint).

- **`ExportRequest` (DTO):** format, scope, workspace_id, artifact_id (optional), baseline_id (optional).

- **`ExportMetadata` (DTO):** terminology_profile, baseline_snapshot (optional), export_timestamp.

### 2.2 Datenstrukturen

- **Export-Stream-Buffer:** Streaming-Puffer für JSON/CSV (nicht vollständiges Laden in RAM). Pufferblock-Größe: 10 MB.

- **TraceLink-Entity-Referenzen:** Für Traceability-Matrix: source_id, target_id, link_type, artifact_types.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-EXP-001 (JSON-Export mit Terminologie) | JSONExporter.export(): Querie alle Artefakte nach Scope, laden Terminologie-Profil von PresetConfigEngine, serialisieren zu JSON mit `metadata.terminology_profile` Top-Level-Feld. Streaming: iteriere über Artefakte, schreibe blockweise. Export von 1.000 Items in ≤5s. |
| REQ-L3-EXP-002 (CSV-Export mit Terminologie) | CSVExporter.export(): Schreibe Terminologie-Kommentar in Zeile 1, dann CSV-Header. RFC4180-Escaping (Anführungszeichen, Kommata, Zeilenumbrüche). Streaming iteriert über Zeilen. Export von 1.000 Items in ≤5s. |
| REQ-L3-EXP-003 (Scope-basierte Filterung) | Methode `_build_query(scope, workspace_id, artifact_id)`: Bei scope='workspace' → alle Entitäten; bei scope='artifact' → Subtree des angegebenen Artifacts (via parent_id Hierarchie). Tenant-Isolation: WHERE tenant_id = current_tenant. Ungültig artifact_id → Error. |
| REQ-L3-EXP-004 (PDF-Report-Export) | PDFExporter.export(): Erzeugt Struktur (Title-Page mit Workspace-Name/Baseline/Datum), Requirement-Dokument (alle Requirements mit Eigenschaften), Traceability-Matrix (Source→Target-Links), Coverage-Report (TestCase-Abdeckung %). PDFExporter nutzt externe Lib. Output: maschinenlesbarer Text (nicht Bild). |
| REQ-L3-EXP-005 (TraceLink-Einbindung) | Methode `_include_tracelinks()`: JSON enthält `tracelinks` Array mit source_id, target_id, link_type. CSV hat separate Zeilen für TraceLinks (mit Spalten source_id, target_id, link_type). PDF-Matrix zeigt alle Link-Typen mit Count. Query von TraceabilityEngine. |
| REQ-L3-EXP-006 (Baseline-Referenzen) | Wenn baseline_id Parameter: Lade Baseline-Snapshot aus DB, embed in `metadata.baseline_snapshot`. Baseline-Metadaten (Creator, Datum, Anmerkungen) included. Non-existent baseline → Error. |
| REQ-L3-EXP-007 (Performance und Ressourcen-Limiting) | Streaming für CSV/JSON (nicht Ganzes in RAM). Timeout 30s max. Max Export-Größe 500MB (Oversized-Export abgewiesen). Für 10.000+ Items: Streaming-Parser (iteriere über Chunks), Memory-Peak < 500MB. |
| REQ-L3-EXP-008 (Fehlerbehandlung) | Bei Fehler (DB-Timeout, ungültiger Scope): Strukturierten Error mit Nachricht zurückgeben. Kein partieller Export. HTTP-Status reflektiert Fehler (400, 404, 500). Keine internen Stack-Traces in Response. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API Endpoint `/export` mit ExportRequest-Payload (format, scope, workspace_id, artifact_id, baseline_id).

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-007:** SELECT Queries an PersistenceLayer für Artefakte, TraceLinks, Baseline-Snapshots.
  - **IF-AS-EXT-OUT-004:** Anfrage an PresetConfigEngine für Terminologie-Profil (`get_active_profile(workspace_id)`).
  - **IF-AS-EXT-OUT-003:** Query-Aufrufe an TraceabilityEngine für TraceLinks (`query_tracelinks(workspace_id)`).

---

## 5. Architectural Rationale

**ADR-L3-EXP-01 — Streaming-Exporte für Ressourcen-Effizienz**

*Entscheidung:* JSON/CSV werden gestreamt (blockweise in ~10 MB Chunks), nicht vollständig in RAM gepuffert. PDF wird gepuffert (komplexere Rendering-Anforderungen).

*Rationale:* Exporte können >10.000 Items mit 500MB+ Größe erreichen. In-Memory-Pufferung würde OOM-Fehler verursachen. Streaming garantiert konstante Memory-Auslastung und schnelle API-Antworten. Alternative: Vollständiges Laden in RAM → Risiko von Out-Of-Memory; Batch-Export mit Polling → Komplexität und längere Latenz. **Abgelehnt**: Resource-Limiting ist kritisch für Skalierbarkeit.

*Erfüllt Trigger:* REQ-L3-EXP-007 (Performance und Ressourcen-Limiting).

---

**ADR-L3-EXP-02 — Terminologie-Profil als Metadatum statt Transformation**

*Entscheidung:* Das aktive Terminologie-Profil wird als Metadatum (nicht als Datentransformation) in den Export eingebettet. Externe Systeme können das Profil konsultieren, um Feldnamen zu interpretieren.

*Rationale:* Terminologie-Profile können sich ändern; die geltende Version zum Export-Zeitpunkt muss dokumentiert sein für Compliance und Vergleichbarkeit. Geebnete Alternative: Feldnamen im Export transformieren (z.B. title → requirement_statement basierend auf Profil) → Komplexität und mögliche Datenverluste. **Abgelehnt**: Metadatum-Ansatz ist sauberer und flexibler.

*Erfüllt Trigger:* REQ-L3-EXP-001, REQ-L3-EXP-002 (Terminologie-Einbettung).

---

**ADR-L3-EXP-03 — Scope-Filter in Query statt Post-Processing**

*Entscheidung:* Scope-Filter (workspace vs. artifact) werden als WHERE-Klauseln in die PersistenceLayer-Query eingefügt, nicht als Post-Processing.

*Rationale:* Query-Filter reduziert Datentransfer und Memory-Footprint. Alternative: Alle Artefakte laden, dann in Memory filtern → Ineffizient bei großen Workspaces. **Abgelehnt**: Performance-Anforderung REQ-L3-EXP-007 erfordert Query-basierte Filterung.

*Erfüllt Trigger:* REQ-L3-EXP-003 (Scope-basierte Filterung).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
