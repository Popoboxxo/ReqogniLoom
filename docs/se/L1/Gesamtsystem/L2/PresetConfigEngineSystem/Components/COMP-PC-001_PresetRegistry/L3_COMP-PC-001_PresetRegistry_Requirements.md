decomposition_status: terminal

# L3 PresetRegistry Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PC-001 — PresetRegistry
> **Parent-System:** PresetConfigEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Preset-Definitionen und -Defaults (Minimal / Standard / Extended), Feature-Flags, Baseline-Scope-Verfügbarkeit, Workflow-Konfigurierbarkeit und `change_reason`-Policy. Statische Konfigurationsquelle für alle Preset-Regeln; datengetrieben (konfigurationsbasiert, nicht code-embedded).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PC-001 | Preset-Verwaltung: Minimal / Standard / Extended zur Laufzeit |
| REQ-L2-PC-003 | Preset-Query-Interface: vollständige Konfiguration per `get_preset()` |
| REQ-L2-PC-004 | Pflichtfeld-Regeln pro Preset |
| REQ-L2-PC-005 | Baseline-Scope-Verfügbarkeit pro Preset |
| REQ-L2-PC-006 | Workflow-Konfigurierbarkeits-Regeln pro Preset |
| REQ-L2-PC-007 | Change-Reason-Pflicht-Regeln pro Preset |
| REQ-L2-PC-012 | Default-Preset-Immutabilität |
| REQ-L2-PC-014 | Benutzerdefinierte Presets (Extended-Modus, optional) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PC-INT-001 | ausgehend | COMP-PC-003 (FeatureGateService) | `get_preset_config(workspace_id) -> PresetConfig` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| ID | Richtung | Gegenstelle | Typ | Beschreibung |
|----|----------|-------------|-----|--------------|
| IF-PC-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM | Lesen/Schreiben von PresetConfig-Objekten (Workspace, WorkspaceSettings) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-PC001-001: Vollständige Preset-Konfigurationsdaten pro Tier


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die PresetRegistry SHALL für jeden der drei Tier-Werte (Minimal, Standard, Extended) eine vollständige, atomar lesbare Konfigurationsstruktur bereitstellen, die Pflichtfelder, Feature-Flags, erlaubte Baseline-Scopes, Workflow-Konfigurierbarkeit und Change-Reason-Policy beinhaltet.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `get_preset_config("minimal")` returns a complete PresetConfig with all required fields populated
- [ ] `get_preset_config("standard")` returns mandatory_fields including description, acceptance_criteria, priority
- [ ] `get_preset_config("extended")` returns change_reason policy "mandatory" and global baseline scope enabled
- [ ] Any missing key in PresetConfig raises a ConfigurationError, not a KeyError

---

### REQ-L3-PC001-002: Baseline-Scope-Verfügbarkeit konfigurierbar pro Tier


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die PresetRegistry SHALL für jeden Tier die Liste erlaubter Baseline-Scopes definieren: Minimal → leer, Standard → `["document", "project"]`, Extended → `["document", "project", "global"]`.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `get_preset_config("minimal").baseline_scopes` returns an empty list or `[]`
- [ ] `get_preset_config("standard").baseline_scopes` returns exactly `["document", "project"]`
- [ ] `get_preset_config("extended").baseline_scopes` returns exactly `["document", "project", "global"]`
- [ ] Querying an unknown scope key raises ScopeNotAvailableError

---

### REQ-L3-PC001-003: Default-Preset-Immutabilität


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die PresetRegistry SHALL sicherstellen, dass die drei Default-Presets (Minimal, Standard, Extended) weder modifiziert noch gelöscht werden können. Jeder Versuch gibt einen expliziten Fehler zurück.

**Priority:** desired

**Acceptance Criteria:**
- [ ] Attempt to modify a default preset raises `ImmutablePresetError("Default presets are immutable")`
- [ ] Attempt to delete a default preset raises `ImmutablePresetError("Default presets cannot be deleted")`
- [ ] Custom presets (if supported) are not affected by this constraint

---

### REQ-L3-PC001-004: Benutzerdefinierte Presets als Ableitung von Default-Presets


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die PresetRegistry KANN im Extended-Modus die Erstellung benutzerdefinierter Presets erlauben, die auf einem der drei Default-Presets basieren und einzelne Felder überschreiben. Im Minimal- und Standard-Modus ist die Erstellung benutzerdefinierter Presets abzulehnen.

**Priority:** optional

**Acceptance Criteria:**
- [ ] Create custom preset "Compliance-Lite" cloning Standard in Extended workspace → accepted, persisted
- [ ] Create custom preset in Minimal workspace → rejected with `"Custom presets require Extended mode"`
- [ ] Delete custom preset → workspace falls back to its default tier preset without data loss

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*

---

### REQ-L3-PC001-005: L3 Context Generators Implementation

Derives from REQ-L2-PRE-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-PC001-006: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-PRE-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.


## Derived L3 Requirements for Unmapped L2

### REQ-L3-PC001-U000: Auto-derived from REQ-L2-PRE-014
Abgeleitet von: REQ-L2-PRE-014

### REQ-L3-PC001-U001: Auto-derived from REQ-L2-PRE-004
Abgeleitet von: REQ-L2-PRE-004

### REQ-L3-PC001-U002: Auto-derived from REQ-L2-PRE-006
Abgeleitet von: REQ-L2-PRE-006

### REQ-L3-PC001-U003: Auto-derived from REQ-L2-PRE-012
Abgeleitet von: REQ-L2-PRE-012

### REQ-L3-PC001-U004: Auto-derived from REQ-L2-PRE-005
Abgeleitet von: REQ-L2-PRE-005

### REQ-L3-PC001-U005: Auto-derived from REQ-L2-PRE-011
Abgeleitet von: REQ-L2-PRE-011

### REQ-L3-PC001-U006: Auto-derived from REQ-L2-PRE-001
Abgeleitet von: REQ-L2-PRE-001

### REQ-L3-PC001-U007: Auto-derived from REQ-L2-PRE-010
Abgeleitet von: REQ-L2-PRE-010

### REQ-L3-PC001-U008: Auto-derived from REQ-L2-PRE-002
Abgeleitet von: REQ-L2-PRE-002

### REQ-L3-PC001-U009: Auto-derived from REQ-L2-PRE-007
Abgeleitet von: REQ-L2-PRE-007

### REQ-L3-PC001-U010: Auto-derived from REQ-L2-PRE-009
Abgeleitet von: REQ-L2-PRE-009

### REQ-L3-PC001-U011: Auto-derived from REQ-L2-PRE-003
Abgeleitet von: REQ-L2-PRE-003

### REQ-L3-PC001-U012: Auto-derived from REQ-L2-PRE-013
Abgeleitet von: REQ-L2-PRE-013

### REQ-L3-PC001-U013: Auto-derived from REQ-L2-PRE-008
Abgeleitet von: REQ-L2-PRE-008
