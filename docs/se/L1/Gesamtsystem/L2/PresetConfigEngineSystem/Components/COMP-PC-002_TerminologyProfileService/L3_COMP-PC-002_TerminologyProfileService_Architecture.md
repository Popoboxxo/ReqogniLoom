---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:30:00Z"
schema_version: "1.0.0"
---
# L3 TerminologyProfileService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PC-002_TerminologyProfileService
> **Parent:** L2_PresetConfigEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der TerminologyProfileService verwaltet Terminologie-Profile für verschiedene Domänen (Dev-Modus, SE-Modus) und stellt vollständige Mappings von generischen Entity-Namen zu domänenspezifischen Labels bereit. REST API und MCP-Server verwenden immer generische Namen; nur die Präsentationsschicht (UI) nutzt die transformierten Labels. Profilwechsel erfolgt ohne Datenmigration in unter 1 Sekunde.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`TerminologyProfile` (Datenklasse):** Immutable Struktur mit vollständigem Label-Mapping.
- **`TerminologyProfileService` (Singleton):** Primäre API zur Abfrage und zum Wechsel von Profilen.
- **`TerminologyProfileLoader` (Klasse):** Lädt Profile aus Konfigurationsdatei (JSON/YAML).
- **`ProfileChangeEvent` (Event-Klasse):** Signalisiert Profilwechsel an andere Komponenten.
- **`IncompleteProfileError` (Exception):** Signalisiert unvollständiges Mapping.

### 2.2 Datenstrukturen

**TerminologyProfile Struktur:**
```python
@dataclass
class TerminologyProfile:
    profile_id: str  # "dev_mode", "se_mode"
    labels: Dict[str, str]  # {
        "artifact_l1": "Epic",           # dev_mode
        "artifact_l2": "Story",          # dev_mode
        "requirement": "Acceptance Criterion",
        "architecture_element": "Component",
        "trace_link": "Dependency",
        "baseline": "Release Plan",
        "workflow_state": "Status",
        "test_case": "Scenario",
        # ... all entity types mapped
    }
```

**Profile Definitions (in Loader):**
```python
TERMINOLOGY_PROFILES = {
    "dev_mode": {
        "profile_id": "dev_mode",
        "labels": {
            "artifact_l1": "Epic",
            "artifact_l2": "Story",
            "requirement": "Acceptance Criterion",
            "architecture_element": "Component",
            "trace_link": "Dependency",
            "baseline": "Release Plan",
            "workflow_state": "Status",
            "test_case": "Scenario",
        },
    },
    "se_mode": {
        "profile_id": "se_mode",
        "labels": {
            "artifact_l1": "System Requirement",
            "artifact_l2": "Function",
            "requirement": "Requirement",
            "architecture_element": "Subsystem",
            "trace_link": "Traceability Link",
            "baseline": "Baseline",
            "workflow_state": "Workflow State",
            "test_case": "Test Case",
        },
    },
}
```

**WorkspaceSettings (Django Model für Persistierung):**
```python
class WorkspaceSettings(TenantModel):
    workspace = ForeignKey(Workspace, ...)
    active_terminology_profile = CharField(
        choices=[("dev_mode", "Dev Mode"), ("se_mode", "SE Mode")],
        default="dev_mode"
    )
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PC002-001 (Vollständiges Label-Mapping pro Profil) | `get_terminology_profile(workspace_id) -> TerminologyProfile` liefert alle Entity-Typ-Mappings. Missing Keys werfen `IncompleteProfileError`. |
| REQ-L3-PC002-002 (Profil-Wechsel < 1 Sekunde ohne Datenmigration) | `switch_terminology_profile(workspace_id, target_profile)` aktualisiert nur `WorkspaceSettings.active_terminology_profile`. Keine Schema-Änderungen. API-Antworten unchanged. |
| REQ-L3-PC002-003 (Profil-Persistenz pro Workspace) | Aktive Profile werden in `WorkspaceSettings.active_terminology_profile` persistiert. Neustart stellt letzte Einstellung wieder her. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PC-EXT-IN-002:** ApplicationService ruft `get_terminology_profile(workspace_id)` auf.
- **IF-PC-EXT-IN-003:** ApplicationService ruft `switch_terminology_profile(workspace_id, target_profile)` auf.

**Ausgänge (Outbound):**
- **IF-PC-EXT-OUT-001:** PersistenceLayer speichert/liest WorkspaceSettings via Django ORM.
- **IF-PC-INT-002:** FeatureGateService ruft ggf. `get_terminology_profile()` auf (indirekt über ApplicationService).

---

## 5. Architectural Rationale

**ADR-L3-PC-002 — Terminologie als UI-Layer-Transformation, nicht API-Level**

*Entscheidung:* REST API und MCP-Server verwenden immer generische Entity-Namen. Nur die UI-Schicht (Frontend) transformiert Labels via TerminologyProfileService.

*Alternative (abgelehnt):* API-Response ändern basierend auf Profil. Grund: Würde API-Kontrakte zerstören, Cross-Domain-Kommunikation kompliziert machen.

*Rationale:* REQ-L3-PC002-001 und REQ-L3-PC002-002 funktionieren transparent, wenn API unveränderlich ist. Transformation ist lokalisiert (Frontend).

---

**ADR-L3-PC-003 — Profil-Wechsel als Settings-Update, nicht Migration**

*Entscheidung:* Profilwechsel aktualisiert nur `WorkspaceSettings.active_terminology_profile`. Keine Datenmigration, keine Schema-Änderung.

*Alternative (abgelehnt):* Aktuelle Entity-Labels in der DB speichern. Grund: Komplexer, redundant, Synchronisierungsprobleme.

*Rationale:* REQ-L3-PC002-002 fordert < 1 Sekunde und "ohne Datenmigration". Settings-Update ist O(1) und sofort konsistent.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
