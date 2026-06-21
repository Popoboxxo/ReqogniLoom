# L3 PresetGuard Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-004 — PresetGuard
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Laufzeit-Abfrage der PresetConfigEngine zur Bestimmung, welche API-Endpunkte und Felder im aktiven Workspace-Preset sichtbar und aktiv sind. Liefert Endpoint-Sichtbarkeits-Entscheidungen an den Controller und Feld-Filteranweisungen an den DataSerializer.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-008 | Preset-basierte Endpunkt- und Feldsichtbarkeit |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RA-INT-002 | eingehend / ausgehend | COMP-RA-001 (HttpEndpointController) | `PresetRequest {endpoint_id, workspace_id, method} -> PresetDecision \| PresetError` |
| IF-RA-INT-004 | ausgehend | COMP-RA-002 (DataSerializer) | `FieldFilter {permitted_fields, required_fields}` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Beschreibung |
|-------|----------|-------------|--------------|
| IF-RA-EXT-OUT-006 | ausgehend | PresetConfigEngine (ARCH-L1-008) | `is_feature_enabled(key, workspace_id)` — Preset-Abfrage |

## L3 Komponenten-Anforderungen

### REQ-L3-RA004-001: Endpunkt-Sichtbarkeitsprüfung per Workspace-Preset

Der PresetGuard SHALL für jeden eingehenden Request die PresetConfigEngine via `is_feature_enabled(endpoint_id, workspace_id)` konsultieren und eine `PresetDecision` (sichtbar / nicht sichtbar) zurückliefern. Nicht erlaubte Endpunkte SHALL mit einer `PresetDecision(visible=false)` beantwortet werden, die der Controller in HTTP 404 oder HTTP 403 übersetzt.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal-preset: request to Baseline endpoint returns `PresetDecision(visible=false)` → HTTP 404
- [ ] Extended-preset: Approver-related endpoints return `PresetDecision(visible=true)`
- [ ] Preset is queried per-request using `workspace_id` from AuthContext — not cached globally
- [ ] PresetConfigEngine unavailable → `PresetError` → HTTP 503, not silent pass-through

---

### REQ-L3-RA004-002: Feld-Filteranweisung an DataSerializer

Der PresetGuard SHALL nach einer positiven Endpunkt-Sichtbarkeitsprüfung eine `FieldFilter`-Anweisung erzeugen und über IF-RA-INT-004 an den DataSerializer liefern. Die `FieldFilter`-Anweisung SHALL `permitted_fields` (Liste aller im aktiven Preset erlaubten Felder) und `required_fields` (Liste der im aktiven Preset Pflichtfelder) enthalten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Extended-preset: `FieldFilter.required_fields` includes `change_reason`
- [ ] Minimal-preset: `FieldFilter.permitted_fields` excludes Extended-only fields
- [ ] `FieldFilter` is generated after a positive `PresetDecision` — never before
- [ ] Unit test: two different presets produce two distinct, non-overlapping `FieldFilter` sets

---

### REQ-L3-RA004-003: Preset-Abfrage ohne Geschäftslogik-Eigenimplementierung

Der PresetGuard DARF keine eigenständige Preset-Konfigurationslogik implementieren. Alle Preset-Entscheidungen MÜSSEN ausschließlich durch Aufruf von `is_feature_enabled(key, workspace_id)` auf der PresetConfigEngine getroffen werden. Hartcodierte Feature-Flags oder lokale Preset-Definitionen sind unzulässig.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] PresetGuard source contains no hard-coded feature flag lists
- [ ] All routing through `is_feature_enabled` calls — verifiable via static analysis
- [ ] Changing a preset in PresetConfigEngine propagates to API behavior without code change in PresetGuard

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
