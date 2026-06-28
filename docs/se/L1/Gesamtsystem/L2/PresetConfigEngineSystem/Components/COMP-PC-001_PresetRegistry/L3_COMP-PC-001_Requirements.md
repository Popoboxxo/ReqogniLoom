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
