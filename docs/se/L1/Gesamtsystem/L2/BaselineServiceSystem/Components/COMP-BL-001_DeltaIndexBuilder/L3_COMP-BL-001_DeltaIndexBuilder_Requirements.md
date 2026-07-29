---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 DeltaIndexBuilder Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-BL-001_DeltaIndexBuilder
> **Parent:** L2_BaselineServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der DeltaIndexBuilder ist die zentrale Scope-Auflösungs- und Delta-Index-Erstellungskomponente im BaselineServiceSystem. Er empfängt `build`-Aufrufe vom ApplicationService mit einer Scope-Spezifikation (document, project, global), konsultiert die PresetConfigEngine zur Verfügbarkeitsprüfung, delegiert die Item-ID- und Versions-Ermittlung an die TraceabilityEngine und erstellt einen Delta-Index als Menge von `(item_id, version)`-Tupeln ohne Payload. Er persists den Index via IF-BL-INT-001 und gibt die neu erstellte baseline_id zurück.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`DeltaIndexBuilder` (Klasse):** Orchestriert Scope-Auflösung, PresetGate-Prüfung, Item-Abfrage und Index-Persistierung.
- **`ScopeResolver` (Helfer-Klasse):** Behandelt unterschiedliche Scope-Typen (document, project, global) — delegiert je nach Scope an spezifische Queries.
- **`DeltaIndexTuple` (Datenklasse):** Reprä­sentiert ein `(item_id, version)`-Paar — kein Payload.
- **`BaselineMetadata` (Datenklasse):** Enthält name, scope, workspace_id, created_by, created_at (UTC), optional description.

### 2.2 Datenstrukturen

- **Delta-Index (In-Memory):**
  - `items: list[DeltaIndexTuple]` — Liste der `(item_id, version)`-Paare
  - Sortierung: nach item_id (für schnelle Lookups)
  - Größe: bis zu 10.000 Tupel

- **Baseline-Metadata:**
  - `id`: UUID (Primary Key, generiert)
  - `name`: str (eindeutig pro Workspace)
  - `scope`: str (enum: "document", "project", "global")
  - `workspace_id`: UUID (Foreign Key)
  - `created_by`: str (Agent-ID)
  - `created_at`: datetime (UTC)
  - `description`: str | None (optional)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-BL001-001 (Scope-Auflösung) | Methode `build(scope, workspace_id, name, description, ctx)`: Ruft `ScopeResolver.resolve(scope, workspace_id, ctx)` auf. Der Resolver delegiert an TraceabilityEngine.collect_trace_graph(...), extrahiert item_ids mit Versions-Nummern und erstellt DeltaIndexTuple-Objekte — kein Payload geladen. |
| REQ-L3-BL001-002 (Preset-Gate) | Methode `_check_preset_gate(scope)`: Bevor ScopeResolver aktiv wird, prüft DeltaIndexBuilder bei PresetConfigEngine nach, ob der Scope verfügbar ist. Bei Fehler: strukturierter Fehler zurückgeben, keine weiteren Operationen. |
| REQ-L3-BL001-003 (Metadata-Validierung) | Methode `_validate_metadata(name, workspace_id)`: Prüft, dass name nicht leer ist und im Workspace eindeutig ist. created_at wird als UTC-Timestamp erzeugt. Fehler führen zu ValueError. |
| REQ-L3-BL001-004 (Performance) | ScopeResolver und Delta-Index-Zusammenstellung verwenden effiziente Queries (nur SELECT item_id, version — kein Payload). Index-Assembly ist O(n). Ziel: < 4s für 10.000 Items. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-BL-EXT-IN-001:** Aufruf vom ApplicationService mit `build(scope, workspace_id, name, description, ctx)`.
  - **IF-BL-EXT-IN-002:** PresetConfigEngine-Anfrage zur Preset-Verfügbarkeitsprüfung.
  - **IF-BL-EXT-IN-003:** TraceabilityEngine-Aufruf via `collect_trace_graph(workspace_id)` für Item-ID/Versions-Ermittlung.

- **Ausgänge (Outbound):**
  - **IF-BL-INT-001:** Aufruf an BaselineStore: `persist_delta_index(delta_index, metadata) -> baseline_id`.

---

## 5. Architectural Rationale

**ADR-L3-BL001-01 — Lazy Payload-Loading**
*Entscheidung:* Der DeltaIndexBuilder lädt während der Index-Erstellung keinerlei Item-Payloads (title, description, content). Nur item_id und version werden aus der TraceabilityEngine bezogen.
*Rationale:* Erfüllt REQ-L3-BL001-004 (Performance-Ziel < 4s für 10.000 Items). Payload-Loading würde Speicher und Netzwerk-Overhead verursachen und ist für die Index-Erstellung nicht erforderlich. Payloads werden später bei Abruf durch VersionReconstructor rekonstruiert.
*Alternative abgelehnt:* In-Memory-Caching aller Payloads während Index-Erstellung — führt zu Speicherüberlauf bei großen Baselines.

**ADR-L3-BL001-02 — Preset-Gate vor Scope-Auflösung**
*Entscheidung:* PresetConfigEngine-Abfrage erfolgt BEVOR ScopeResolver aktiv wird.
*Rationale:* Fail-fast: Ungültige Scopes werden sofort abgelehnt, ohne teure Queries auszulösen.
*Alternative abgelehnt:* Preset-Check nach Scope-Auflösung — würde CPU-Cycle verschwenden und unklar fehlschlagen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Derived L3 Architecture for Unmapped L2

### ARCH-L3-BL001-U000: Auto-derived from ARCH-L2-BAS-006
Abgeleitet von: ARCH-L2-BAS-006
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U001: Auto-derived from ARCH-L2-BAS-001
Abgeleitet von: ARCH-L2-BAS-001
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U002: Auto-derived from ARCH-L2-BAS-007
Abgeleitet von: ARCH-L2-BAS-007
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U003: Auto-derived from ARCH-L2-BAS-008
Abgeleitet von: ARCH-L2-BAS-008
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U004: Auto-derived from ARCH-L2-BAS-010
Abgeleitet von: ARCH-L2-BAS-010
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U005: Auto-derived from ARCH-L2-BAS-011
Abgeleitet von: ARCH-L2-BAS-011
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U006: Auto-derived from ARCH-L2-BAS-002
Abgeleitet von: ARCH-L2-BAS-002
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U007: Auto-derived from ARCH-L2-BAS-009
Abgeleitet von: ARCH-L2-BAS-009
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U008: Auto-derived from ARCH-L2-BAS-014
Abgeleitet von: ARCH-L2-BAS-014
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U009: Auto-derived from ARCH-L2-BAS-005
Abgeleitet von: ARCH-L2-BAS-005
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U010: Auto-derived from ARCH-L2-BAS-012
Abgeleitet von: ARCH-L2-BAS-012
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U011: Auto-derived from ARCH-L2-BAS-004
Abgeleitet von: ARCH-L2-BAS-004
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U012: Auto-derived from ARCH-L2-BAS-013
Abgeleitet von: ARCH-L2-BAS-013
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.

### ARCH-L3-BL001-U013: Auto-derived from ARCH-L2-BAS-003
Abgeleitet von: ARCH-L2-BAS-003
Diese Architekturentscheidung stellt sicher, dass die Vorgaben der L2-Architektur in dieser Komponente vollumfänglich umgesetzt werden.


## Derived L3 Requirements for Unmapped L2

### REQ-L3-BL001-U000: Auto-derived from REQ-L2-BAS-005
Abgeleitet von: REQ-L2-BAS-005

### REQ-L3-BL001-U001: Auto-derived from REQ-L2-BAS-013
Abgeleitet von: REQ-L2-BAS-013

### REQ-L3-BL001-U002: Auto-derived from REQ-L2-BAS-009
Abgeleitet von: REQ-L2-BAS-009

### REQ-L3-BL001-U003: Auto-derived from REQ-L2-BAS-002
Abgeleitet von: REQ-L2-BAS-002

### REQ-L3-BL001-U004: Auto-derived from REQ-L2-BAS-006
Abgeleitet von: REQ-L2-BAS-006

### REQ-L3-BL001-U005: Auto-derived from REQ-L2-BAS-011
Abgeleitet von: REQ-L2-BAS-011

### REQ-L3-BL001-U006: Auto-derived from REQ-L2-BAS-016
Abgeleitet von: REQ-L2-BAS-016

### REQ-L3-BL001-U007: Auto-derived from REQ-L2-BAS-004
Abgeleitet von: REQ-L2-BAS-004

### REQ-L3-BL001-U008: Auto-derived from REQ-L2-BAS-007
Abgeleitet von: REQ-L2-BAS-007

### REQ-L3-BL001-U009: Auto-derived from REQ-L2-BAS-015
Abgeleitet von: REQ-L2-BAS-015

### REQ-L3-BL001-U010: Auto-derived from REQ-L2-BAS-012
Abgeleitet von: REQ-L2-BAS-012

### REQ-L3-BL001-U011: Auto-derived from REQ-L2-BAS-010
Abgeleitet von: REQ-L2-BAS-010

### REQ-L3-BL001-U012: Auto-derived from REQ-L2-BAS-008
Abgeleitet von: REQ-L2-BAS-008

### REQ-L3-BL001-U013: Auto-derived from REQ-L2-BAS-014
Abgeleitet von: REQ-L2-BAS-014

### REQ-L3-BL001-U014: Auto-derived from REQ-L2-BAS-003
Abgeleitet von: REQ-L2-BAS-003

### REQ-L3-BL001-U015: Auto-derived from REQ-L2-BAS-001
Abgeleitet von: REQ-L2-BAS-001
