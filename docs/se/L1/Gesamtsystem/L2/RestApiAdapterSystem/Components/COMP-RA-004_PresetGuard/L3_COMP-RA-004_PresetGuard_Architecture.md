---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:15:00Z"
schema_version: "1.0.0"
---

# L3 PresetGuard Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RA-004_PresetGuard
> **Parent:** L2_RestApiAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der PresetGuard ist der Runtime-Gatekeeper für Preset-basierte API-Visibility und Feld-Filterung. Er konsultiert die PresetConfigEngine zur Bestimmung der für einen Workspace aktiven Feature-Set, entscheidet über Endpunkt-Sichtbarkeit (visible/invisible) und generiert präzise Feld-Filteranweisungen (permitted_fields, required_fields) für den DataSerializer.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`PresetGuard` (Klasse):** Hauptklasse mit Methoden `check_endpoint_visible(endpoint_id, workspace_id, method) -> PresetDecision | PresetError` und `generate_field_filter(endpoint_id, workspace_id, entity_type) -> FieldFilter | PresetError`.
- **`PresetFeatureResolver` (Klasse):** Utility, das PresetConfigEngine-Abfragen orchestriert. Cacht `is_feature_enabled()` Ergebnisse pro Request (in-Memory, kurze TTL).
- **`FieldFilterBuilder` (Klasse):** Baut `FieldFilter` aus Preset-Definition zusammen. Kombiniert permitted_fields und required_fields je nach Endpoint und Entity-Type.

### 2.2 Datenstrukturen

- **`PresetDecision` (Pydantic Model):** {visible: bool, reason?: str}.
- **`FieldFilter` (Pydantic Model):** {permitted_fields: List[str], required_fields: List[str]}.
- **`PresetError` (Exception):** {error_code: "preset_config_unavailable"|"unknown_preset", message, http_status: 503}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RA004-001 (Endpunkt-Sichtbarkeitsprüfung) | check_endpoint_visible() ruft PresetConfigEngine.is_feature_enabled(endpoint_id, workspace_id) auf. Antwortet mit PresetDecision(visible=true|false). Nicht sichtbare → HTTP 404/403 vom Controller. PresetConfigEngine-Fehler → HTTP 503. |
| REQ-L3-RA004-002 (Feld-Filteranweisung) | Nach positiver PresetDecision: generate_field_filter() erzeugt FieldFilter mit permitted_fields und required_fields basierend auf Preset-Konfiguration. |
| REQ-L3-RA004-003 (Keine eigenständige Logik) | PresetGuard enthält keine hardcodierten Feature-Flags oder lokalen Preset-Definitionen. Alle Entscheidungen via is_feature_enabled(). |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RA-INT-002:** Von COMP-RA-001 (HttpEndpointController): `check_endpoint_visible(endpoint_id, workspace_id, method) -> PresetDecision | PresetError`.

**Ausgänge (Outbound):**
- **IF-RA-INT-004:** Zu COMP-RA-002 (DataSerializer): `get_field_filter(endpoint_id, workspace_id) -> FieldFilter`.
- **IF-RA-EXT-OUT-006:** Zu PresetConfigEngine (ARCH-L1-008): `is_feature_enabled(key, workspace_id) -> bool`.

---

## 5. Architectural Rationale

**ADR-L3-RA4-01 — PresetConfigEngine als Single Source of Truth**

*Entscheidung:* Alle Preset-Entscheidungen kommen ausschließlich von PresetConfigEngine. PresetGuard delegiert, cacht nicht.

*Rationale:* Erfüllt REQ-L3-RA004-003 ("Changing a preset in PresetConfigEngine propagates to API behavior without code change in PresetGuard"). Verhindert Daten-Inkonsistenzen. Caching erfolgt auf Request-Ebene (kurze TTL) für Performance, nicht persistent.

---

**ADR-L3-RA4-02 — Separate Endpoints für Visibility und Field-Filter**

*Entscheidung:* check_endpoint_visible() und generate_field_filter() sind separate Operationen mit unterschiedlichen Input/Output.

*Rationale:* Ermöglicht granulare Fehlerbehandlung und unabhängige Unit-Tests (REQ-L3-RA004-002 "Unit test: two different presets produce two distinct, non-overlapping FieldFilter sets"). Alternative: Kombiniert → würde Single-Responsibility-Prinzip verletzen.

---

**ADR-L3-RA4-03 — PresetError → HTTP 503, nicht 404**

*Entscheidung:* PresetConfigEngine-Fehler (unavailable, timeout) → PresetError → HTTP 503 vom Controller. Nicht "Preset nicht gefunden" (das ist Business-Logic).

*Rationale:* Unterscheidet Infrastruktur-Fehler (503) von Logik-Entscheidungen (404 sichtbar=false). Akzeptanzkriterium: "PresetConfigEngine unavailable → PresetError → HTTP 503, not silent pass-through".

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
