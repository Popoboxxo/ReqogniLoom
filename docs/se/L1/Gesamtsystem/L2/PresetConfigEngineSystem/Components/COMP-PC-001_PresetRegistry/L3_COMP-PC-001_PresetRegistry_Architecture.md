---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:25:00Z"
schema_version: "1.0.0"
---
# L3 PresetRegistry Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PC-001_PresetRegistry
> **Parent:** L2_PresetConfigEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die PresetRegistry ist die zentrale Konfigurationsquelle für alle Preset-Definitionen (Minimal, Standard, Extended). Sie verwaltet Feature-Flags, Baseline-Scope-Verfügbarkeit, Workflow-Konfigurierbarkeit, Change-Reason-Policy und benutzerdefinierte Preset-Erweiterungen (Extended-Modus). Sie ist datengetrieben und keine Code-Embedding-Quelle.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`PresetConfig` (Datenklasse):** Immutable Struktur mit allen Konfigurationsfeldern eines Presets.
- **`PresetRegistry` (Singleton):** Primäre API zur Abfrage von Preset-Definitionen.
- **`PresetConfigLoader` (Klasse):** Lädt Preset-Definitionen aus Datenbank oder Konfigurationsdatei (JSON/YAML).
- **`ImmutablePresetError` (Exception):** Signalisiert Versuch, Default-Presets zu ändern.
- **`CustomPreset` (Model):** Django-Modell für benutzerdefinierte Presets im Extended-Modus (optional).

### 2.2 Datenstrukturen

**PresetConfig Struktur:**
```python
@dataclass
class PresetConfig:
    tier: str  # "minimal", "standard", "extended"
    mandatory_fields: List[str]  # ["title"], ["title", "description", ...], etc.
    baseline_scopes: List[str]  # [], ["document", "project"], ["document", "project", "global"]
    features_enabled: Dict[str, bool]  # {"baselines": True, "global_baselines": False, ...}
    workflow_configurable: bool  # False, False, True
    change_reason_policy: str  # "optional", "optional", "mandatory"
    immutable: bool  # True (for default presets)
    custom_preset_allowed: bool  # False, False, True
```

**Preset Defaults (in Loader):**
```python
PRESET_DEFINITIONS = {
    "minimal": {
        "tier": "minimal",
        "mandatory_fields": ["title"],
        "baseline_scopes": [],
        "features_enabled": {
            "baselines": False,
            "global_baselines": False,
            "approval_workflows": False,
            "custom_workflows": False,
            "change_reason_mandatory": False,
        },
        "workflow_configurable": False,
        "change_reason_policy": "optional",
        "immutable": True,
    },
    "standard": {
        "tier": "standard",
        "mandatory_fields": ["title", "description", "acceptance_criteria"],
        "baseline_scopes": ["document", "project"],
        "features_enabled": {
            "baselines": True,
            "global_baselines": False,
            "approval_workflows": False,
            "custom_workflows": False,
            "change_reason_mandatory": False,
        },
        "workflow_configurable": False,
        "change_reason_policy": "optional",
        "immutable": True,
    },
    "extended": {
        "tier": "extended",
        "mandatory_fields": ["title", "description", "acceptance_criteria", "priority"],
        "baseline_scopes": ["document", "project", "global"],
        "features_enabled": {
            "baselines": True,
            "global_baselines": True,
            "approval_workflows": True,
            "custom_workflows": True,
            "change_reason_mandatory": True,
        },
        "workflow_configurable": True,
        "change_reason_policy": "mandatory",
        "immutable": True,
        "custom_preset_allowed": True,
    },
}
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PC001-001 (Vollständige Preset-Konfigurationsdaten pro Tier) | `get_preset_config(tier: str) -> PresetConfig` liefert alle Felder: mandatory_fields, baseline_scopes, features_enabled, workflow_configurable, change_reason_policy. Missing Keys werfen `ConfigurationError`. |
| REQ-L3-PC001-002 (Baseline-Scope-Verfügbarkeit pro Tier) | `baseline_scopes` Feld differenziert korrekt: minimal=[], standard=[document, project], extended=[document, project, global]. |
| REQ-L3-PC001-003 (Default-Preset-Immutabilität) | Versuche, Default-Presets zu modifizieren oder zu löschen, werfen `ImmutablePresetError`. Prüfung via `immutable` Flag. |
| REQ-L3-PC001-004 (Benutzerdefinierte Presets) | Extended-Modus erlaubt Custom-Presets via `CustomPreset`-Modell. Minimal/Standard-Modus lehnt ab. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PC-EXT-OUT-001:** PersistenceLayer bietet Django ORM für Workspace- und Preset-Verwaltung.

**Ausgänge (Outbound):**
- **IF-PC-INT-001:** FeatureGateService ruft `get_preset_config(workspace_id)` auf.

---

## 5. Architectural Rationale

**ADR-L3-PC-001 — Preset-Definition als Code + Optional Database**

*Entscheidung:* Default-Presets sind hardcoded in `PRESET_DEFINITIONS`. Custom-Presets (Extended-Modus) werden in DB gespeichert (CustomPreset-Modell).

*Alternative (abgelehnt):* Alle Presets in DB. Grund: Mehr Komplexität, Default-Presets sollten nicht veränderlich sein.

*Rationale:* REQ-L3-PC001-003 fordert Immutabilität von Defaults. Code-Definitionen sind immutable; DB erlaubt Custom-Variationen.

---

**ADR-L3-PC-002 — Tier-basierte Feature-Komposition statt Feature-Liste**

*Entscheidung:* Features sind als Zusammensetzung von Tier-Ebenen organisiert (Minimal < Standard < Extended), nicht als freie Kombination.

*Alternative (abgelehnt):* Beliebige Feature-Combination pro Workspace. Grund: Zu viele Kombinationen, zu schwer zu testen/dokumentieren.

*Rationale:* REQ-L3-PC001-001 und REQ-L3-PC001-002 funktionieren einfacher mit strikten Tiers. Montage-Logik ist klar.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
