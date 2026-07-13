# L3 FeatureGateService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PC-003 — FeatureGateService
> **Parent-System:** PresetConfigEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Laufzeit-Entscheidungen über sichtbare Endpunkte und Felder, Preset-Downgrade-Validierung sowie Cache-Verwaltung für < 10ms-Queries. Primäre Eintrittspforte für alle externen Feature-Anfragen — delegiert intern an PresetRegistry (IF-PC-INT-001) und TerminologyProfileService (IF-PC-INT-002).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PC-002 | Feature-Query-Interface: `is_feature_enabled(feature_key, workspace_id)` |
| REQ-L2-PC-008 | Preset-Wechsel aufsteigend ohne Datenmigration, < 1 Sekunde |
| REQ-L2-PC-011 | Preset-Downgrade-Validierung mit konfigurierbarer Policy |
| REQ-L2-PC-013 | Preset-Query-Performance: p95 < 10ms bei 50 parallelen Workspaces |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PC-INT-001 | eingehend (als Aufrufer) | COMP-PC-001 (PresetRegistry) | `get_preset_config(workspace_id) -> PresetConfig` |
| IF-PC-INT-002 | eingehend (als Aufrufer) | COMP-PC-002 (TerminologyProfileService) | `get_terminology_profile(workspace_id) -> TerminologyMapping` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| ID | Richtung | Gegenstelle | Typ | Beschreibung |
|----|----------|-------------|-----|--------------|
| IF-PC-EXT-IN-001 | eingehend | RestApiAdapter / McpServer / ApplicationService / WorkflowEngine / BaselineService | In-Process Python | `get_preset(workspace_id)`, `is_feature_enabled(feature_key, workspace_id)` |
| IF-PC-EXT-IN-003 | eingehend | ApplicationService | In-Process Python | `switch_preset(workspace_id, target_preset)`, `validate_downgrade(workspace_id, target_preset)` |
| IF-PC-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM | Schreiben des neuen Preset-Zustands nach Wechsel |

---

## L3 Komponenten-Anforderungen

### REQ-L3-PC003-001: Feature-Enabled-Query mit korrektem Preset-Mapping


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der FeatureGateService SHALL `is_feature_enabled(feature_key, workspace_id)` implementieren und die Antwort ausschließlich aus der Preset-Konfiguration der Workspace ableiten. Feature-Keys müssen mindestens `baselines`, `global_baselines`, `approval_workflows`, `custom_workflows`, `change_reason_mandatory` umfassen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `is_feature_enabled("baselines", workspace_minimal)` returns `False`
- [ ] `is_feature_enabled("baselines", workspace_standard)` returns `True`
- [ ] `is_feature_enabled("global_baselines", workspace_standard)` returns `False`
- [ ] `is_feature_enabled("global_baselines", workspace_extended)` returns `True`
- [ ] `is_feature_enabled("change_reason_mandatory", workspace_extended)` returns `True`
- [ ] Unknown feature_key raises `UnknownFeatureKeyError`

---

### REQ-L3-PC003-002: Query-Performance p95 unter 10ms mit Cache


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der FeatureGateService SHALL Preset-Queries in unter 10ms (p95) beantworten. Caching per Workspace-ID ist zulässig. Nach einem Preset-Wechsel muss der Cache für den betroffenen Workspace innerhalb von 100ms invalidiert sein.

**Priority:** desired

**Acceptance Criteria:**
- [ ] 50 concurrent workspaces, 100 preset queries each → p95 latency < 10ms
- [ ] Cache invalidation completes within 100ms after `switch_preset()` call
- [ ] Queries after cache invalidation return the new preset configuration
- [ ] Cache hit rate > 90% under sustained load (same workspace queried repeatedly)

---

### REQ-L3-PC003-003: Preset-Downgrade-Validierung mit konfigurierbarer Policy


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der FeatureGateService SHALL bei `validate_downgrade(workspace_id, target_preset)` inkompatible Daten prüfen (z.B. vorhandene Global-Baselines bei Downgrade von Extended auf Standard). Bei Inkompatibilität muss der Downgrade blockiert werden, wenn die konfigurierte Policy `block` ist.

**Priority:** desired

**Acceptance Criteria:**
- [ ] Extended workspace with 1 global baseline → `validate_downgrade(ws, "standard")` raises `DowngradeBlockedError("1 global baseline exists")`
- [ ] After deleting the global baseline → `validate_downgrade(ws, "standard")` succeeds
- [ ] Downgrade policy "warn" → returns warnings without raising an error
- [ ] Downgrade policy "allow" → always passes validation regardless of data state

---

### REQ-L3-PC003-004: Aufsteigender Preset-Wechsel ohne Datenmigration


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der FeatureGateService SHALL aufsteigende Preset-Wechsel (Minimal → Standard → Extended) via `switch_preset(workspace_id, target_preset)` ohne Datenmigration, Datenverlust oder Schema-Änderungen vollziehen. Der Wechsel muss bei 10.000 Artefakten in unter 1 Sekunde abgeschlossen sein.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Minimal workspace with 50 requirements → switch to Standard → all requirements unchanged, baselines feature now enabled
- [ ] Standard workspace with 100 requirements + 2 baselines → switch to Extended → all data unchanged
- [ ] No DB migration script is triggered by `switch_preset()`
- [ ] `switch_preset()` with 10,000 artifacts completes in < 1 second wall-clock time
- [ ] New preset is queryable immediately after successful switch

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
