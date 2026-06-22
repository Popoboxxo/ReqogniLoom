---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 ToolRegistry Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-MC-002_ToolRegistry
> **Parent:** L2_McpServerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die ToolRegistry ist die zentrale Dispatch-Einheit und Zugriffskontroll-Schicht. Sie empfängt validierte JSON-RPC-Frames vom ProtocolHandler, validiert den API-Key via AuthAndTenancy, wendet Preset-Filter (PresetConfigEngine) an, prüft RBAC für schreibende Operationen und leitet autorisierte Aufrufe an die zuständige Tool-Gruppe weiter. Sie gibt strukturierte ToolResult-Objekte zurück oder Fehler (AUTH_FAILED, PERMISSION_DENIED, FEATURE_NOT_ENABLED, UNKNOWN_TOOL).

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ToolRegistry` (Klasse):** Zentrale Dispatch- und Autorisierungs-Logik.
- **`AuthContext` (Dataclass):** Kapselt Agent-Identität, Tenant-ID, Rollen (nach Auth-Validierung).
- **`ToolGroupRouter` (Helper-Klasse):** Routed Tool-Namen zu zuständigen Gruppen basierend auf Präfix.
- **`PresetCache` (Klasse):** LRU-Cache für Preset-Konfigurationen (Invalidierung bei Workspace-Änderung).
- **`RbacValidator` (Helper-Klasse):** RBAC-Regeln pro Operation.

### 2.2 Datenstrukturen

- **AuthContext:**
  - `agent_id`: str (AI-Agent-Identität)
  - `tenant_id`: str
  - `workspace_id`: str (optional, aus Request)
  - `roles`: set[str] (z.B. {"Viewer", "Editor", "Admin"})

- **ToolGroupRouter Mapping:**
  - `requirement.*` → RequirementsToolGroup
  - `architecture.*` → ArchitectureToolGroup
  - `test.*` → TestToolGroup
  - `traceability.*`, `artifact.*`, `workspace.*` → CrossCuttingToolGroup

- **PresetCache (In-Memory Dict):**
  - Key: workspace_id
  - Value: { enabled_tools: set[str], ttl: timestamp }

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-MC002-001 (API-Key-Validierung) | Methode `_validate_api_key(api_key)`: Aufruf an AuthAndTenancy. Bei ungültig: return AUTH_FAILED, kein Dispatch. Bei gültig: AuthContext aufbauen mit agent_id, tenant_id, roles. |
| REQ-L3-MC002-002 (RBAC-Prüfung) | Methode `_check_rbac(auth_context, operation)`: Für write-Operationen (create, update, link, decompose) prüfen, ob Rolle erlaubt. Lesend: keine Prüfung. Fehler: PERMISSION_DENIED. |
| REQ-L3-MC002-003 (Preset-Filter) | Methode `_check_preset(workspace_id, tool_name)`: Abfrage PresetConfigEngine. Gecachtes Preset-Objekt mit enabled_tools-Set. Tool nicht in Set: FEATURE_NOT_ENABLED. |
| REQ-L3-MC002-004 (Tool-Routing) | Methode `_route_tool(tool_name)`: Prefix-Match (requirement.*, architecture.*, etc.) → zuständige Gruppe. Unbekannt: UNKNOWN_TOOL. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-MC-INT-001:** Aufruf vom ProtocolHandler: `dispatch_request(json_rpc_frame, api_key)`.

- **Ausgänge (Outbound):**
  - **IF-MC-EXT-OUT-002:** Aufruf an AuthAndTenancy: `validate_api_key(key) -> AuthContext`.
  - **IF-MC-EXT-OUT-004:** Aufruf an PresetConfigEngine: `get_preset(workspace_id) -> PresetConfig`.
  - **IF-MC-INT-002:** Aufruf an RequirementsToolGroup: `execute_tool(...)`.
  - **IF-MC-INT-003:** Aufruf an ArchitectureToolGroup: `execute_tool(...)`.
  - **IF-MC-INT-004:** Aufruf an TestToolGroup: `execute_tool(...)`.
  - **IF-MC-INT-005:** Aufruf an CrossCuttingToolGroup: `execute_tool(...)`.

---

## 5. Architectural Rationale

**ADR-L3-MC002-01 — Drei-Schichten-Autorisierung (Auth → RBAC → Preset)**
*Entscheidung:* Sequential: (1) API-Key-Validierung (Auth), (2) RBAC für schreibend, (3) Preset-Filter.
*Rationale:* Klare Hierarchie: Auth ist erste Barriere (fail-fast). RBAC prüft Berechtigung. Preset ist Zusatzfilter (Compliance). Erfüllt REQ-L3-MC002-001..003.
*Alternative abgelehnt:* Parallel-Prüfung — könnte zu unklaren Fehler-Meldungen führen.

**ADR-L3-MC002-02 — Preset-Caching mit Invalidierung**
*Entscheidung:* Preset-Konfigurationen werden gecacht (LRU, workspace_id als Key). Invalidierung bei Workspace-Änderung (event-driven oder TTL).
*Rationale:* Optimiert Preset-Abfrage-Latenz. Erfüllt REQ-L3-MC002-003 (Caching erwünscht).
*Alternative abgelehnt:* Immer fresh preset laden — würde Latenz auf jede ToolRegistry-Anfrage hinzufügen.

**ADR-L3-MC002-03 — Expliziter Tool-Routing basierend auf Präfix**
*Entscheidung:* Tool-Namen werden nach Präfix klassifiziert (requirement.*, architecture.*, etc.). Unbekannte Präfixe → UNKNOWN_TOOL.
*Rationale:* Skalierbar, einfach neue Tool-Gruppen hinzufügbar. Erfüllt REQ-L3-MC002-004.
*Alternative abgelehnt:* Dynamisches Tool-Registry (alle Tools registrieren sich) — würde Komplexität hinzufügen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
