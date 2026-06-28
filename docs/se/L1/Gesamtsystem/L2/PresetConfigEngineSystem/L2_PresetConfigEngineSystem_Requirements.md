# L2 PresetConfigEngine Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** PresetConfigEngineSystem (ARCH-L1-008)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-007 (primär), REQ-L1-014 (primär), REQ-L1-002 (mitwirkend), REQ-L1-008 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-017 (mitwirkend), REQ-L1-019 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-PC-EXT-IN-001 | input | data | `get_preset(workspace_id)`, `is_feature_enabled(feature_key, workspace_id)` von ARCH-L1-002, 003, 004, 005, 006 |
| IF-PC-EXT-IN-002 | input | data | `get_terminology_profile(workspace_id)` von ARCH-L1-001, 004 |
| IF-PC-EXT-IN-003 | input | data | `switch_preset()`, `switch_terminology_profile()`, `validate_downgrade()` von ARCH-L1-004 |
| IF-PC-EXT-OUT-001 | output | data | Workspace-Konfiguration an PersistenceLayer (ARCH-L1-010) |

---

## Mandatory Requirements

### REQ-L2-PC-001: Preset-Verwaltung (Minimal / Standard / Extended)
Die PresetConfigEngine SHALL drei vordefinierte Workspace-Presets verwalten — Minimal, Standard und Extended — die zur Laufzeit bestimmen: Pflichtfelder, sichtbare Features, Baseline-Scope-Verfügbarkeit, Workflow-Konfigurierbarkeit und `change_reason`-Pflicht.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_preset(workspace_minimal)` → keine Baselines, keine Approval-Workflows, change_reason optional
- [ ] `get_preset(workspace_standard)` → Document-/Project-Baselines, einfacher Workflow
- [ ] `get_preset(workspace_extended)` → alle Baseline-Scopes inkl. Global, strikter Workflow, change_reason Pflicht
- [ ] Preset-Wechsel persistiert im Workspace-Objekt

**Interfaces:**
- Incoming: IF-PC-EXT-IN-001
- Outgoing: IF-PC-EXT-OUT-001, IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007
**Rationale:** Configurable Rigor ist das zentrale Differenzierungsmerkmal.


---

### REQ-L2-PC-002: Feature-Query-Interface
Die PresetConfigEngine SHALL das Interface `is_feature_enabled(feature_key, workspace_id)` bereitstellen. Feature-Keys: mindestens `baselines`, `global_baselines`, `approval_workflows`, `custom_workflows`, `change_reason_mandatory`.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `is_feature_enabled("baselines", workspace_minimal)` → `false`
- [ ] `is_feature_enabled("baselines", workspace_standard)` → `true`
- [ ] `is_feature_enabled("global_baselines", workspace_standard)` → `false`
- [ ] `is_feature_enabled("global_baselines", workspace_extended)` → `true`
- [ ] `is_feature_enabled("approval_workflows", workspace_extended)` → `true`
- [ ] `is_feature_enabled("change_reason_mandatory", workspace_extended)` → `true`
- [ ] Antwortzeit < 10ms pro Query

**Interfaces:**
- Incoming: IF-PC-EXT-IN-001
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007, REQ-L1-002 (mitwirkend), REQ-L1-008 (mitwirkend)
**Rationale:** Zentralisiertes Feature-Gating verhindert Duplizierung (ADR-04).


---

### REQ-L2-PC-003: Preset-Query-Interface
Die PresetConfigEngine SHALL `get_preset(workspace_id)` die vollständige Preset-Konfiguration zurückgeben: Pflichtfeld-Regeln, Feature-Flags, Baseline-Scope-Verfügbarkeit, Workflow-Konfigurierbarkeit, `change_reason`-Policy.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_preset(workspace_standard)` → `{preset: "standard", mandatory_fields: {...}, features: {...}, baseline_scopes: ["document", "project"], workflow_configurability: "partial", change_reason: "optional"}`
- [ ] `get_preset(workspace_extended)` → `baseline_scopes: ["document", "project", "global"], workflow_configurability: "full", change_reason: "mandatory"`
- [ ] ApplicationService kann alle Preset-Entscheidungen mit einem Call treffen

**Interfaces:**
- Incoming: IF-PC-EXT-IN-001
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007
**Rationale:** Vollständige Konfiguration reduziert Interface-Aufrufe.


---

### REQ-L2-PC-004: Pflichtfeld-Regeln pro Preset
Die PresetConfigEngine SHALL Pflichtfeld-Regeln pro Preset definieren. Minimal: nur `title`. Standard: + `description`, `acceptance_criteria`, `priority`. Extended: + `classification`, `traceability-target`, `change_reason`.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Create Requirement mit nur title in Minimal → akzeptiert
- [ ] Create Requirement mit nur title in Standard → Fehler `"missing mandatory fields"`
- [ ] Create Requirement in Extended ohne `classification` → Fehler

**Interfaces:**
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007, REQ-L1-002 (mitwirkend)
**Rationale:** Pflichtfeld-Steuerung ist der Kernmechanismus von Configurable Rigor.


---

### REQ-L2-PC-005: Baseline-Scope-Verfügbarkeit pro Preset
Die PresetConfigEngine SHALL Baseline-Scope-Verfügbarkeit bestimmen: Minimal → keine. Standard → `document`, `project`. Extended → alle drei.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `is_scope_allowed(workspace_minimal, "document")` → `false`
- [ ] `is_scope_allowed(workspace_standard, "project")` → `true`
- [ ] `is_scope_allowed(workspace_standard, "global")` → `false`
- [ ] `is_scope_allowed(workspace_extended, "global")` → `true`

**Interfaces:**
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007, REQ-L1-008 (mitwirkend)
**Rationale:** Scope-Staffelung differenziert Presets.


---

### REQ-L2-PC-006: Workflow-Konfigurierbarkeits-Regeln pro Preset
Die PresetConfigEngine SHALL Workflow-Konfigurierbarkeit bestimmen: Minimal → `fixed`. Standard → `partial`. Extended → `full`.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_workflow_configurability(workspace_minimal)` → `"fixed"`
- [ ] `get_workflow_configurability(workspace_standard)` → `"partial"`
- [ ] `get_workflow_configurability(workspace_extended)` → `"full"`
- [ ] Custom Workflow im Minimal-Preset → abgelehnt

**Interfaces:**
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007, REQ-L1-009 (mitwirkend)
**Rationale:** Einfache Teams werden nicht überfordert, SE-Teams erhalten volle Kontrolle.


---

### REQ-L2-PC-007: Change-Reason-Pflicht-Regeln pro Preset
Die PresetConfigEngine SHALL `change_reason`-Pflicht bestimmen: Minimal/Standard → optional. Extended → Pflicht.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Transition in Minimal ohne change_reason → akzeptiert
- [ ] Transition in Standard ohne change_reason → akzeptiert
- [ ] Transition in Extended ohne change_reason → Fehler `"change_reason is mandatory"`

**Interfaces:**
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007, REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend)
**Rationale:** Change-Reason-Pflicht ist essentiell für Audit-Trail in regulierten Umgebungen.


---

### REQ-L2-PC-008: Preset-Wechsel aufsteigend ohne Datenmigration
Die PresetConfigEngine SHALL aufsteigende Preset-Wechsel (Minimal → Standard → Extended) ohne Datenmigration, Datenverlust oder Schema-Änderungen erlauben. ≤ 1 Sekunde bei 10.000 Artefakten.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal mit 50 Requirements → Wechsel zu Standard → alle Requirements unverändert, neue Features verfügbar
- [ ] Standard mit 100 Requirements + 2 Baselines → Wechsel zu Extended → alles unverändert
- [ ] Kein DB-Migrationsscript nach Wechsel
- [ ] Wechsel bei 10.000 Artefakten < 1 Sekunde

**Interfaces:**
- Incoming: IF-PC-EXT-IN-003
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007
**Rationale:** Aufsteigender Wechsel ist die primäre Wachstumsstrategie.


---

### REQ-L2-PC-009: Terminologie-Profil-Verwaltung (Dev-Modus / SE-Modus)
Die PresetConfigEngine SHALL mindestens zwei Terminologie-Profile verwalten. Jedes Profil definiert ein vollständiges Mapping von generischen Entity-Namen zu domänenspezifischen Labels. REST API und MCP nutzen immer generische Namen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Dev-Mode: `{artifact_l1: "Epic", artifact_l2: "Story", requirement: "Acceptance Criterion"}`
- [ ] SE-Mode: `{artifact_l1: "System Requirement", artifact_l2: "Function", architecture_element: "Subsystem"}`
- [ ] REST API Response identisch unabhängig vom aktiven Profil
- [ ] MCP Response identisch unabhängig vom aktiven Profil

**Interfaces:**
- Incoming: IF-PC-EXT-IN-002
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-014
**Rationale:** Terminologie-Flexibilität ohne Datenverlust ist das Fundament der Dual-Zielgruppen-Strategie (ADR-05).


---

### REQ-L2-PC-010: Terminologie-Profil-Wechsel ohne Datenmigration
Die PresetConfigEngine SHALL Profilwechsel ohne Datenmigration, Schema-Änderungen oder API-Strukturänderungen erlauben. ≤ 1 Sekunde.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Wechsel Dev → SE → API-Response identisch, UI-Labels geändert
- [ ] Kein DB-Migrationsscript nach Wechsel
- [ ] Wechsel < 1 Sekunde
- [ ] Alle Requirements inhaltlich unverändert

**Interfaces:**
- Incoming: IF-PC-EXT-IN-003
- Outgoing: IF-PC-EXT-OUT-001, IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-014
**Rationale:** Profilwechsel muss sofort und ohne Risiko sein.


---

## Desired Requirements

### REQ-L2-PC-011: Preset-Downgrade-Validierung
Die PresetConfigEngine SOLLTE Preset-Downgrades validieren, indem sie inkompatible Daten prüft (Global-Baselines, Approval-States). Bei Inkompatibilitäten SHALL der Downgrade blockiert werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Extended mit Global-Baseline → Downgrade zu Standard → Fehler `"Downgrade blocked: 1 global baseline exists"`
- [ ] Nach Löschen der Baseline → Downgrade erfolgreich
- [ ] Downgrade-Policy konfigurierbar (`block`/`warn`/`allow`)

**Interfaces:**
- Incoming: IF-PC-EXT-IN-003
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007
**Rationale:** Adressiert OP-02 aus L1 Requirements.


---

### REQ-L2-PC-012: Default-Preset-Immutabilität
Die drei Default-Presets (Minimal, Standard, Extended) SOLLTEN unveränderlich sein.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Versuch Default-Preset zu modifizieren → `"Default presets are immutable"`
- [ ] Versuch Default-Preset zu löschen → `"Default presets cannot be deleted"`

**Interfaces:**
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007
**Rationale:** Garantiert konsistentes Verhalten über alle Deployments.


---

### REQ-L2-PC-013: Preset-Query-Performance
Preset-Queries SOLLTEN innerhalb von 10ms (p95) antworten. Caching MAY verwendet werden.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] 50 gleichzeitige Workspaces, 100 Preset-Queries → p95 < 10ms
- [ ] Cache-Invalidation nach Preset-Wechsel funktioniert

**Interfaces:**
- Incoming: IF-PC-EXT-IN-001, IF-PC-EXT-IN-001, IF-PC-EXT-IN-002
- Outgoing: IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-026 (mitwirkend)
**Rationale:** PresetConfigEngine wird von fast jedem Request konsultiert.


---

## Optional Requirements

### REQ-L2-PC-014: Benutzerdefinierte Presets (Extended-Modus)
Im Extended-Preset KANN die PresetConfigEngine benutzerdefinierte Presets erlauben (Clone eines Default-Presets mit Modifikationen).

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Domain:** software
**Priority:** optional
**Acceptance Criteria:**
- [ ] Custom Preset "Compliance-Lite" basierend auf Standard → akzeptiert im Extended
- [ ] Custom Preset im Minimal → abgelehnt
- [ ] Delete Custom Preset → Fallback auf Default

**Interfaces:**
- Incoming: IF-PC-EXT-IN-003
- Outgoing: IF-PC-EXT-OUT-001, IF-PC-EXT-OUT-001


**Traceability:** REQ-L1-007
**Rationale:** Feingranulare Rigor-Konfiguration für spezialisierte Compliance-Szenarien. v2-Enhancement.


---

## Traceability-Matrix: REQ-L2-PC → REQ-L1

| REQ-L2-PC | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-PC-001 | REQ-L1-007 | — |
| REQ-L2-PC-002 | REQ-L1-007 | REQ-L1-002, REQ-L1-008 |
| REQ-L2-PC-003 | REQ-L1-007 | — |
| REQ-L2-PC-004 | REQ-L1-007 | REQ-L1-002 |
| REQ-L2-PC-005 | REQ-L1-007 | REQ-L1-008 |
| REQ-L2-PC-006 | REQ-L1-007 | REQ-L1-009 |
| REQ-L2-PC-007 | REQ-L1-007 | REQ-L1-009, REQ-L1-011 |
| REQ-L2-PC-008 | REQ-L1-007 | — |
| REQ-L2-PC-009 | REQ-L1-014 | — |
| REQ-L2-PC-010 | REQ-L1-014 | — |
| REQ-L2-PC-011 | REQ-L1-007 | — |
| REQ-L2-PC-012 | REQ-L1-007 | — |
| REQ-L2-PC-013 | REQ-L1-026 | — |
| REQ-L2-PC-014 | REQ-L1-007 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-PC | 14 |
| Mandatory | 10 |
| Desired | 3 |
| Optional | 1 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-007, REQ-L1-014 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, REQ-L1-008, REQ-L1-009, REQ-L1-017, REQ-L1-019, REQ-L1-026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Preset → REQ-L2-PC, Template-Standardisierung*
*Designation: component (terminal) — decomposition_status: terminal*
