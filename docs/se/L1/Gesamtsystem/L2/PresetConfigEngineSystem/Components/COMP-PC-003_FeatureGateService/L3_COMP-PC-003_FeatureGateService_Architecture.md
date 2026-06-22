---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:35:00Z"
schema_version: "1.0.0"
---
# L3 FeatureGateService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PC-003_FeatureGateService
> **Parent:** L2_PresetConfigEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der FeatureGateService ist das primäre Zugangstor für alle Feature-Queries und Preset-Management-Operationen. Er delegiert intern an PresetRegistry (IF-PC-INT-001) und TerminologyProfileService (IF-PC-INT-002). Er implementiert Caching für Query-Performance (< 10ms p95), Preset-Downgrade-Validierung, und aufsteigenden Preset-Wechsel ohne Datenmigration.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`FeatureGateService` (Singleton):** Primäre API für Feature-Queries und Preset-Operationen.
- **`PresetCache` (Klasse):** In-Memory-Cache mit TTL (Time-To-Live) für Workspace-Presets.
- **`DowngradeValidator` (Klasse):** Prüft Kompatibilität bei Preset-Downgrades.
- **`PresetSwitch` (Event-Klasse):** Signalisiert Preset-Wechsel.
- **`UnknownFeatureKeyError`, `DowngradeBlockedError`, `DowngradePolicyError` (Exceptions).**

### 2.2 Datenstrukturen

**PresetCache Struktur:**
```python
class PresetCache:
    _cache: Dict[UUID, Tuple[PresetConfig, float]]  # (preset_config, timestamp)
    _ttl_seconds: int = 300  # 5 Minuten TTL

    def get(self, workspace_id: UUID) -> Optional[PresetConfig]:
        # Prüft TTL, gibt None zurück wenn abgelaufen

    def set(self, workspace_id: UUID, config: PresetConfig):
        # Speichert mit Timestamp

    def invalidate(self, workspace_id: UUID):
        # Löscht Entry sofort
```

**DowngradeValidator Logik:**
```python
class DowngradeValidator:
    DOWNGRADE_CHECKS = {
        ("extended", "standard"): [
            "check_global_baselines",  # Keine globalen Baselines erlaubt nach Downgrade
            "check_custom_workflows",  # Keine custom Workflows
        ],
        ("standard", "minimal"): [
            "check_any_baselines",  # Keine Baselines in Minimal
            "check_approval_workflows",
        ],
    }

    def validate_downgrade(
        self,
        workspace_id: UUID,
        target_tier: str,
        policy: str = "block"
    ) -> ValidationResult:
        # policy: "block" (raise error), "warn" (log, return warnings), "allow" (skip)
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PC003-001 (Feature-Enabled-Query) | `is_feature_enabled(feature_key, workspace_id)` ruft PresetRegistry auf, mappt Feature-Keys zu Preset-Features. Unbekannte Keys werfen `UnknownFeatureKeyError`. |
| REQ-L3-PC003-002 (Query-Performance < 10ms) | PresetCache mit 5-Minuten TTL. Cache-Hit-Rate > 90%. Invalidation nach Wechsel < 100ms. |
| REQ-L3-PC003-003 (Downgrade-Validierung) | `validate_downgrade()` prüft Kompatibilität. Policy "block" wirft `DowngradeBlockedError`, "warn" logged, "allow" überspringt. |
| REQ-L3-PC003-004 (Aufsteigender Preset-Wechsel) | `switch_preset()` für Aufsteiger (minimal→standard, standard→extended) ohne Datenmigration < 1 Sekunde bei 10.000 Artefakten. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PC-INT-001:** Ruft `get_preset_config(workspace_id)` auf PresetRegistry auf.
- **IF-PC-INT-002:** Ruft `get_terminology_profile(workspace_id)` auf TerminologyProfileService auf.
- **IF-PC-EXT-IN-001:** External Services (RestApiAdapter, MCP, ApplicationService, WorkflowEngine, BaselineService) rufen `get_preset()` und `is_feature_enabled()` auf.
- **IF-PC-EXT-IN-003:** ApplicationService ruft `switch_preset()` und `validate_downgrade()` auf.

**Ausgänge (Outbound):**
- **IF-PC-EXT-OUT-001:** Schreibt neuen Preset-Zustand via PersistenceLayer nach Wechsel.

---

## 5. Architectural Rationale

**ADR-L3-PC-003 — In-Memory-Cache mit TTL für Query-Performance**

*Entscheidung:* Preset-Konfigurationen werden nach erstem Abruf gecacht (TTL 5 Minuten). Nach Preset-Wechsel wird Cache invalidiert.

*Alternative (abgelehnt):* Jedes Mal von PresetRegistry abrufen (direkt). Grund: REQ-L3-PC003-002 fordert < 10ms p95 bei 50 parallelen Workspaces. Direkter Abruf zu langsam.

*Rationale:* Cache ist einfach, Cache-Hit-Rate wird hoch (> 90%), und Invalidierung ist atomare DB-Update → fast.

---

**ADR-L3-PC-004 — Drei-Stufen-Downgrade-Validierung (block/warn/allow)**

*Entscheidung:* Downgrade-Policy ist konfigurierbar: "block" (Error), "warn" (Log), "allow" (Skip). Ermöglicht flexible Governance.

*Alternative (abgelehnt):* Immer blockieren. Grund: REQ-L3-PC003-003 fordert "konfigurierbare Policy". Manchmal wollen Admins degradieren (Daten-Cleanup zuerst).

*Rationale:* Drei Optionen decken Governance-Spektrum ab: Strict (block), Advisory (warn), Lenient (allow).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
