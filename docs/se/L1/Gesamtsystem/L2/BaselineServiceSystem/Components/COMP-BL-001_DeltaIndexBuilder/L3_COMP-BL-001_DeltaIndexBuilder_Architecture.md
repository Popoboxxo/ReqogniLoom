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
