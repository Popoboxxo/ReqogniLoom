---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 PresetPolicyService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-012_PresetPolicyService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der PresetPolicyService ist die zentrale Querschnitts-Komponente für Configurable-Rigor-Enforcement. Er validiert Preset-Regeln (Scope-Erlaubnis für Baselines, change_reason-Anforderung für Updates, Transition-Role-Validierung, Downgrade-Inkompatibilität) und wird von BaselineFacade, WorkflowFacade und allen schreibenden Domain-Services konsultiert. Der Service ist die Single Source of Truth für Preset-Policy-Entscheidungen und implementiert Caching (TTL 5 Minuten) zur Performance-Optimierung.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`PresetPolicyService` (Klasse):** Zentrale Policy-Abfragne-Engine mit Methoden:
  - `is_scope_allowed(workspace_id, scope) → boolean`
  - `is_change_reason_required(workspace_id) → boolean`
  - `validate_transition_roles(auth_context, item_id, target_state) → (boolean, error_message)`
  - `check_downgrade_compatibility(workspace_id, target_preset) → (compatible: bool, incompatible_items: [])`
  - `get_policy(workspace_id, policy_key) → policy_value` (generische Abfrage)

- **`PresetCache` (Cache-Manager):** In-Memory Cache für Preset-Definitionen mit TTL 5 Minuten. Event-Listener für Preset-Update-Events zum Invalidieren.

- **`PolicyValidator` (Klasse):** Validiert einzelne Policy-Regeln (Scope gegen Whitelist, change_reason gegen Enum, Rollen gegen Whitelist).

- **`PresetPolicyResult` (DTO):** boolean result, error_message (optional), metadata.

### 2.2 Datenstrukturen

- **Preset-Definition (von PresetConfigEngine):**
  - preset_type: enum (Basic, Standard, Enhanced, Extended)
  - allowed_scopes: list (document, project, global)
  - change_reason_required: boolean
  - transition_roles: dict (target_state → required_roles_list)
  - enumerations_allowed: boolean (für Downgrade-Kompatibilität)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PPL-001 (Scope-Validierung für Baseline) | Methode `is_scope_allowed(workspace_id, scope)` → boolean. Lade Preset-Definition (vom Cache oder PresetConfigEngine). Prüfe scope gegen allowed_scopes-Whitelist. Return true/false + Error-Nachricht wenn blockiert. |
| REQ-L3-PPL-002 (Change-Reason-Requirement) | Methode `is_change_reason_required(workspace_id)` → boolean. Workspace-Preset konsultieren (nicht Global-Default). Return true für Enhanced/Extended, false für Basic/Standard. |
| REQ-L3-PPL-003 (Transition-Role-Validierung) | Methode `validate_transition_roles(auth_context, item_id, target_state) → (bool, error_msg)`. Lade Workflow-Definition des Items. Prüfe erforderliche Rollen für target_state. Vergleiche mit User-Rollen aus auth_context. Return true wenn alle erforderlich, false + Fehler wenn fehlend. |
| REQ-L3-PPL-004 (Downgrade-Inkompatibilität) | Methode `check_downgrade_compatibility(workspace_id, target_preset)` → (bool, incompatible_items). Lade alle Artefakte der Workspace. Prüfe Kompatibilität gegen target_preset (z.B. Extended erlaubt Enumerationen, Basic nicht). Sammle Inkompatible Items mit Grund. Return (false, items) wenn Inkompatibilitäten, (true, []) sonst. |
| REQ-L3-PPL-005 (Preset-Cache mit TTL) | PresetCache mit 5-Minuten-TTL. Event-Listener für Preset-Update-Events triggert Invalidierung. Cache-Hit reduziert PresetConfigEngine-Aufrufe um ≥70%. Fallback: bei Cache-Fehler → Live-Query. |
| REQ-L3-PPL-006 (Workspace-spezifisches Preset) | Alle Methoden akzeptieren workspace_id Parameter. Workspace-Preset wird konsultiert (falls konfiguriert). Fallback zu Tenant-Default wenn keine Workspace-Config. Keine Cross-Workspace-Policy-Anwendung. |
| REQ-L3-PPL-007 (Zentrale Policy-Query-Schnittstelle) | Methode `get_policy(workspace_id, policy_key)` → policy_value. Policy-Keys dokumentiert (scope_allowed, change_reason_required, transition_roles, etc.). Unbekannte Keys werfen Error. Default-Wert wird zurückgegeben wenn Key nicht im Preset definiert. |
| REQ-L3-PPL-008 (Fehlerbehandlung und Audit-Logging) | Bei Policy-Violations: strukturierter Error mit aussagekräftiger Nachricht (z.B. "Scope 'document' not allowed in Extended preset"). Downgrade-Versuche werden optional in AuditLog geloggt. Keine sensitiven Daten in Error-Messages. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-INT-006:** Scope-Erlaubnis-Anfrage von BaselineFacade (`is_scope_allowed(workspace_id, scope)`).
  - **IF-AS-INT-007:** Transition-Role-Validierungsanfrage von WorkflowFacade (`validate_transition_roles(...)` und `is_change_reason_required(...)`).
  - **IF-AS-INT-008:** change_reason-Anforderungsabfrage von AdrService, RiskService, IssueService (`is_change_reason_required(workspace_id)`).

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-004:** Preset-Config abrufen von PresetConfigEngine (`get_preset(workspace_id)`).
  - **IF-AS-EXT-OUT-007:** Workspace-Zustand abfragen vom PersistenceLayer (SELECT COUNT, für Downgrade-Kompatibilität).

---

## 5. Architectural Rationale

**ADR-L3-PPL-01 — Single Source of Truth für Policy-Regeln**

*Entscheidung:* PresetPolicyService ist die alleinige Komponente, die Policy-Regeln auswertet. Alle Konsultationen (Scope, change_reason, Rollen, Downgrade) erfolgen zentral hier.

*Rationale:* Verhindert Inkonsistenzen, wenn mehrere Services Policy-Regeln interpretieren. Änderungen an Policy-Logik erfolgen an einer Stelle. Alternative: Jeder Service implementiert Policy-Logik selbst → Inkonsistenzen, schwer zu debuggen. **Abgelehnt**: Querschnitts-Logik muss zentralisiert sein.

*Erfüllt Trigger:* REQ-L3-PPL-001, REQ-L3-PPL-002, REQ-L3-PPL-003, REQ-L3-PPL-004 (zentrale Validierung).

---

**ADR-L3-PPL-02 — In-Memory Cache für Preset-Definitionen**

*Entscheidung:* Preset-Definitionen werden bis zu 5 Minuten gecacht. Invalidierung bei Preset-Update-Events.

*Rationale:* Preset-Abfragen sind häufig (bei jedem Transition, BaselineCreation, Update). Caching reduziert PresetConfigEngine-Hits. Alternative: Kein Cache, immer live query → höhere Latenz, höhere Last auf PresetConfigEngine. **Abgelehnt**: Performance-Anforderung erfordert Caching; 5 Minuten TTL ist akzeptabel für Policy-Änderungen.

*Erfüllt Trigger:* REQ-L3-PPL-005 (Caching und Performance).

---

**ADR-L3-PPL-03 — Workspace-spezifische Policies mit Tenant-Default-Fallback**

*Entscheidung:* Workspace-spezifisches Preset wird konsultiert; fallback zu Tenant-Default wenn nicht konfiguriert.

*Rationale:* Ermöglicht granulare Konfigurierbarkeit: Workspaces können unterschiedliche Rigor-Level haben (z.B. Prod-Workspace: Extended, Dev-Workspace: Basic). Fallback verhindert fehlende Config. Alternative: Nur Global-Default → weniger Flexibilität. **Abgelehnt**: Multi-Workspace-Szenarien erfordern Workspace-spezifische Policies.

*Erfüllt Trigger:* REQ-L3-PPL-006 (Workspace-spezifisches Preset).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
