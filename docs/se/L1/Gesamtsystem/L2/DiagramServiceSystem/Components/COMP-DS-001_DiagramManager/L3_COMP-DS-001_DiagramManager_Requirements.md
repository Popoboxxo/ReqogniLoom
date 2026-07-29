---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-21T23:20:00Z"
schema_version: "1.0.0"
---
# L3 DiagramManager Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-DS-001_DiagramManager
> **Parent:** L2_DiagramServiceSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der DiagramManager ist die zentrale Steuerungskomponente im DiagramServiceSystem. Er verarbeitet alle CRUD-Trigger vom ApplicationService, delegiert die Typprüfung an den DiagramValidator, das Rendering an den DiagramRenderer und das Verlinken an den TraceabilityConnector. Zudem speichert er die Ergebnisse via PersistenceLayer und AuditLog.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`DiagramManager` (Klasse):** Orchestriert die Anwendungsfälle (`create`, `update`, `get`, `list_versions`).
- **`DiagramDTO` / `DiagramVersionDTO`:** Datenstrukturen (Data Transfer Objects) zur Übergabe an externe und interne Schnittstellen.

### 2.2 Datenstrukturen

- **Diagram-Entity:**
  - `id`: UUID (Primary Key)
  - `created_at`: DateTime
- **DiagramVersion-Entity:**
  - `id`: UUID
  - `diagram_id`: UUID (Foreign Key)
  - `version_number`: Integer
  - `payload`: String (Raw Content, z.B. Mermaid Syntax)
  - `type`: String (z.B. "mermaid")
  - `created_at`: DateTime

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-DM-001 (Diagramm Erstellung) | Methode `create(type, payload)`: Ruft `DiagramValidator.validate_payload` auf. Bei Erfolg wird ein neues Diagram-Entity sowie Version 1 persistiert. Schreibt einen Audit-Eintrag. Gibt UUID zurück. |
| REQ-L3-DM-002 (Diagramm Aktualisierung) | Methode `update(id, payload)`: Validiert den Payload. Lädt höchste Versionsnummer, inkrementiert sie und erzeugt neues DiagramVersion-Entity. Alte Versionen bleiben unverändert in der DB (Append-Only). |
| REQ-L3-DM-003 (Diagramm Abruf) | Methode `get(id, version=None)`: Lädt Daten aus DB. Ruft `DiagramRenderer.prepare_renderable` auf, um RenderableDiagram an den Aufrufer (z.B. Frontend oder MCP) zurückzugeben. |
| REQ-L3-DM-004 (Version-Historie Abruf) | Methode `list_versions(id)`: Query gegen PersistenceLayer, die nach `created_at` oder `version_number` sortierte Liste von DiagramVersionDTOs liefert. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-L1-032:** REST API oder ApplicationService-Methoden (`create_diagram`, `update_diagram`, etc.).
  - **Internal:** Aufruf durch `McpArtifactProvider` (Python Method Call).
- **Ausgänge (Outbound):**
  - **IF-DS-INT-001:** Aufruf an `COMP-DS-002` (Python Function Call `validate_payload`).
  - **IF-DS-INT-002:** Aufruf an `COMP-DS-003` (Python Function Call `prepare_renderable`).
  - **IF-DS-INT-003:** Aufruf an `COMP-DS-004` (Python Function Call `create_document_link`).
  - **IF-L1-035:** ORM-Aufrufe an den PersistenceLayer (z.B. Django ORM).
  - **IF-L1-036:** Aufruf der AuditLog-API.

---

## 5. Architectural Rationale

**ADR-L3-DM-01 — Append-Only Historisierung**
*Entscheidung:* Diagrammaktualisierungen erzeugen stets neue Datensätze (`DiagramVersion`), niemals ein Update des `payload`-Felds.
*Rationale:* Erfüllt REQ-L3-DM-002 strikt. Dies garantiert Auditierbarkeit und verhindert den Verlust alter Stände. Der Speicherbedarf bei Text-Payloads ist vernachlässigbar.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
*Designation: component (terminal) — decomposition_status: terminal*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-DS001-U000: Auto-derived from REQ-L2-DIA-011
Abgeleitet von: REQ-L2-DIA-011

### REQ-L3-DS001-U001: Auto-derived from REQ-L2-DIA-010
Abgeleitet von: REQ-L2-DIA-010

### REQ-L3-DS001-U002: Auto-derived from REQ-L2-DIA-003
Abgeleitet von: REQ-L2-DIA-003

### REQ-L3-DS001-U003: Auto-derived from REQ-L2-DIA-012
Abgeleitet von: REQ-L2-DIA-012

### REQ-L3-DS001-U004: Auto-derived from REQ-L2-DIA-014
Abgeleitet von: REQ-L2-DIA-014

### REQ-L3-DS001-U005: Auto-derived from REQ-L2-DIA-013
Abgeleitet von: REQ-L2-DIA-013

### REQ-L3-DS001-U006: Auto-derived from REQ-L2-DIA-005
Abgeleitet von: REQ-L2-DIA-005

### REQ-L3-DS001-U007: Auto-derived from REQ-L2-DIA-006
Abgeleitet von: REQ-L2-DIA-006

### REQ-L3-DS001-U008: Auto-derived from REQ-L2-DIA-009
Abgeleitet von: REQ-L2-DIA-009

### REQ-L3-DS001-U009: Auto-derived from REQ-L2-DIA-004
Abgeleitet von: REQ-L2-DIA-004

### REQ-L3-DS001-U010: Auto-derived from REQ-L2-DIA-002
Abgeleitet von: REQ-L2-DIA-002

### REQ-L3-DS001-U011: Auto-derived from REQ-L2-DIA-008
Abgeleitet von: REQ-L2-DIA-008

### REQ-L3-DS001-U012: Auto-derived from REQ-L2-DIA-001
Abgeleitet von: REQ-L2-DIA-001

### REQ-L3-DS001-U013: Auto-derived from REQ-L2-DIA-007
Abgeleitet von: REQ-L2-DIA-007
