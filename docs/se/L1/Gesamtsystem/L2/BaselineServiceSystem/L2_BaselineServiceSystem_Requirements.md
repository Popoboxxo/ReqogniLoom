# L2 BaselineService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** BaselineServiceSystem (ARCH-L1-006)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** LEAF (terminal, keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-008 (primär), REQ-L1-003 (mitwirkend), REQ-L1-007 (mitwirkend), REQ-L1-025 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-BL-EXT-IN-001 | input | data | `build(scope, workspace_id, ctx)` / `diff()` / `get()` / `list()` von ApplicationService |
| IF-BL-EXT-IN-002 | input | data | Preset-Regeln von PresetConfigEngine (ARCH-L1-008) |
| IF-BL-EXT-IN-003 | input | data | Trace-Graph von TraceabilityEngine (ARCH-L1-007) |
| IF-BL-EXT-OUT-001 | output | data | Persistenz an PersistenceLayer (ARCH-L1-010) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-BL-001: Baseline Scope Resolution and Delta Storage

Der BaselineService SHALL den angeforderten Scope (`document`, `project`, `global`) auflösen und alle betroffenen Item-IDs mit exakter Revisions-Nummer (`version`) ermitteln. TraceLinks SHALL über die TraceabilityEngine gesammelt werden. Der Snapshot SHALL als Menge von `(item_id, version)`-Tupeln plus zugehörigen TraceLink-Referenzen atomar persistiert werden. Der vollständige Item-Payload (title, description, content) DARF NICHT in der Baseline gespeichert werden.

- **Scope-Semantik:**
  - `document`: Ein Artefakt + alle Nachkommen (rekursiv) inkl. zugehöriger Items und TraceLinks.
  - `project`: Alle Items eines Workspaces.
  - `global`: Alle Items aller Workspaces des Tenants.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Baseline scope=project mit 10 Requirements, 3 ArchElements → Baseline enthält 13 `(item_id, version)`-Einträge
- [ ] Baseline-Eintrag enthält keinen title/description/content-Payload (nur item_id + version)
- [ ] Nachträgliche Änderung eines Requirements → gespeicherte `(item_id, version)`-Tupel unverändert
- [ ] Baseline scope=document für Artefakt A mit 2 Kindern → Snapshot enthält A + Kinder + TraceLink-Referenzen

**Interfaces:**
- Incoming: IF-BL-EXT-IN-001, IF-BL-EXT-IN-003
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008, REQ-L1-003 (mitwirkend)
**Rationale:** Delta-Storage (nur item_id + version statt vollständiger Payload) verhindert massives DB-Wachstum und OOM-Risiko bei großen Projekten. Atomare, unveränderliche Referenzen bleiben Voraussetzung für reproduzierbare Anforderungsstände.

---

### REQ-L2-BL-002: Baseline Immutability

Der BaselineService SHALL strenge Unveränderlichkeit nach der Erstellung erzwingen. Ein persistierter Baseline-Snapshot DARF NICHT modifiziert, gelöscht oder überschrieben werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] UPDATE des Snapshot-Felds → Fehler `"Baselines are immutable"`
- [ ] DELETE der Baseline → Fehler `"Baselines are immutable"`
- [ ] INSERT mit identischer Baseline-ID → Fehler `"Duplicate baseline ID"`

**Interfaces:**
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008
**Rationale:** Unveränderliche Baselines sind Voraussetzung für Compliance-Nachweise.

---

### REQ-L2-BL-003: Baseline Diff (Vergleich)

Der BaselineService SHALL den Vergleich zweier Baselines desselben Scopes unterstützen. Das Diff SHALL drei Kategorien enthalten: added, removed, changed (mit old/new Version). Baselines unterschiedlichen Scopes SÜLLEN mit Fehler abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Diff(A, B) → `{added: [...], removed: [...], changed: [{id, old_version, new_version}]}`
- [ ] Diff unterschiedlicher Scopes → Fehler `"Cannot diff baselines of different scopes"`

**Interfaces:**
- Incoming: IF-BL-EXT-IN-001
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008
**Rationale:** Baseline-Vergleiche sind das operative Werkzeug für Reviews und Change-Management.

---

### REQ-L2-BL-004: Preset Gate — Scope Availability

Der BaselineService SHALL die PresetConfigEngine konsultieren, um die Scope-Verfügbarkeit zu prüfen:
- Minimal: keine Baselines
- Standard: `document` und `project`, kein `global`
- Extended: alle drei Scopes

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal → `create_baseline(scope="document")` → Fehler
- [ ] Standard → `scope="document"` OK, `scope="project"` OK, `scope="global"` → Fehler
- [ ] Extended → alle drei Scopes erlaubt

**Interfaces:**
- Incoming: IF-BL-EXT-IN-002

**Traceability:** REQ-L1-008, REQ-L1-007 (mitwirkend)
**Rationale:** Baseline-Scope-Staffelung ist ein zentrales Differenzierungsmerkmal.

---

### REQ-L2-BL-005: Baseline Naming and Metadata

Der BaselineService SHALL einen eindeutigen, nicht-leeren Namen pro Workspace verlangen. Metadata: `name`, `scope`, `workspace_id`, `description` (optional), `created_by`, `created_at` (UTC). Doppelte Namen im selben Workspace SÜLLEN abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Name "Release 1.0" → OK
- [ ] Zweite Baseline "Release 1.0" im selben Workspace → Fehler `"Baseline name must be unique"`
- [ ] Leerer Name → Fehler `"Baseline name must not be empty"`
- [ ] Gleicher Name in anderem Workspace → OK

**Interfaces:**
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008
**Rationale:** REQ-L1-008 spezifiziert „benannte Baselines".

---

### REQ-L2-BL-006: Baseline Retrieval and Listing

Der BaselineService SHALL Einzelabruf (mit vollständigem Snapshot) und Listen (optional nach Scope gefiltert, sortiert nach created_at DESC) unterstützen. Listen SOLLTEN den Snapshot nicht enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `list(workspace_id=W)` → alle Baselines, sortiert nach created_at DESC
- [ ] `list(workspace_id=W, scope="project")` → nur Project-Baselines
- [ ] `get(baseline_id)` → vollständiger Snapshot
- [ ] `get(nonexistent_id)` → Fehler `"Baseline not found"`

**Interfaces:**
- Incoming: IF-BL-EXT-IN-001
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008
**Rationale:** Baselines müssen identifizierbar und nachschlagbar sein.

---

### REQ-L2-BL-007: Atomic Creation with Transactional Guarantees

Der BaselineService SHALL Baselines atomar erstellen: entweder der komplette Snapshot wird persistiert oder keine Daten (vollständiges Rollback).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] DB-Fehler während Snapshot → Rollback: keine Baseline in DB
- [ ] Baseline mit 1000 Items → entweder alle 1000 oder keine

**Interfaces:**
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008, REQ-L1-025 (mitwirkend)
**Rationale:** ACID-Konsistenz verhindert inkonsistente Anforderungsstände.

---

### REQ-L2-BL-009: Baseline-Rekonstruktion aus Versionshistorie

Der BaselineService SHALL in der Lage sein, den Zustand eines Items zum Baseline-Zeitpunkt zu rekonstruieren. Dazu greift er auf die Versionshistorie (AuditLog oder `RequirementVersion`-Tabelle) zurück und liefert den Payload der gespeicherten `version` zurück. Die Funktion `get_item_at_baseline(baseline_id, item_id)` SHALL den vollständigen Item-Payload zur zum Baseline-Zeitpunkt gespeicherten Version zurückgeben.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_item_at_baseline(bl_id, item_id)` → gibt Payload (title, description, content) des Items in der gespeicherten Version zurück
- [ ] Item wurde nach Baseline-Erstellung geändert → Funktion liefert dennoch den alten Stand
- [ ] item_id nicht in Baseline enthalten → Fehler `"Item not part of this baseline"`
- [ ] version nicht in Versionshistorie vorhanden → Fehler `"Version not found in history"`

**Interfaces:**
- Incoming: IF-BL-EXT-IN-001
- Outgoing: IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-008, REQ-L1-011 (mitwirkend, AuditLog als Versionsquelle)
**Rationale:** Da der Payload nicht mehr in der Baseline direkt gespeichert wird (Delta-Storage, REQ-L2-BL-001), muss der BaselineService die Rekonstruktion aus der Versionshistorie übernehmen, um Baseline-Inhalte weiterhin lesbar zu machen.

---

### REQ-L2-BL-008: Baseline Creation Performance

Der BaselineService SHALL Baseline-Erstellung für bis zu 10.000 Items innerhalb von 5 Sekunden abschließen. Diff-Operationen zwischen zwei Baselines SOLLTEN innerhalb von 2 Sekunden abgeschlossen sein.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `create_baseline(scope="project")` bei 10.000 Items → < 5s (p95)
- [ ] `diff(A, B)` bei je 10.000 Items → < 2s (p95)

**Interfaces:**
- Incoming: IF-BL-EXT-IN-001, IF-BL-EXT-IN-001
- Outgoing: IF-BL-EXT-OUT-001, IF-BL-EXT-OUT-001

**Traceability:** REQ-L1-026, REQ-L1-008 (mitwirkend)
**Rationale:** Baseline-Erstellung ist komplex, muss aber benutzerakzeptabel bleiben.

---

## Traceability-Matrix: REQ-L2-BL → REQ-L1

| REQ-L2-BL | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-BL-001 | REQ-L1-008 | REQ-L1-003 |
| REQ-L2-BL-002 | REQ-L1-008 | — |
| REQ-L2-BL-003 | REQ-L1-008 | — |
| REQ-L2-BL-004 | REQ-L1-008 | REQ-L1-007 |
| REQ-L2-BL-005 | REQ-L1-008 | — |
| REQ-L2-BL-006 | REQ-L1-008 | — |
| REQ-L2-BL-007 | REQ-L1-008 | REQ-L1-025 |
| REQ-L2-BL-008 | REQ-L1-008 | REQ-L1-026 |
| REQ-L2-BL-009 | REQ-L1-008 | REQ-L1-011 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-BL | 9 |
| Mandatory | 8 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-008 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-003, REQ-L1-007, REQ-L1-011, REQ-L1-025, REQ-L1-026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Baseline → REQ-L2-BL, Template-Standardisierung*
*Designation: LEAF (terminal, keine L3-Zerlegung)*
