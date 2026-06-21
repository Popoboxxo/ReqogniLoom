# L3 ToolRegistry Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-MC-002 — ToolRegistry
> **Parent-System:** McpServerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Tool-Discovery, -Registrierung und -Routing; Preset-basierte Tool-Sichtbarkeit; strukturierte Fehlerformatierung. Die ToolRegistry ist die zentrale Dispatch-Einheit: Sie empfaengt validierte JSON-RPC-Frames vom ProtocolHandler, prueft Authentifizierung und Berechtigung (via AuthAndTenancy), wendet Preset-Filter an (via PresetConfigEngine) und leitet den Aufruf an die zustaendige Tool-Gruppe weiter.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-MC-006 | API-Key-Validierung via AuthAndTenancy; AUTH_FAILED bei ungueltigen Keys |
| REQ-L2-MC-007 | RBAC-Pruefung vor schreibenden Operationen; PERMISSION_DENIED bei unzureichenden Rechten |
| REQ-L2-MC-008 | Preset-basierte Tool-Sichtbarkeit; FEATURE_NOT_ENABLED bei deaktivierten Tools |
| REQ-L2-MC-011 | Strukturierte JSON-Fehlerantwort mit error_code, message, details |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-MC-INT-001 | eingehend | COMP-MC-001 ProtocolHandler | `dispatch_request(json_rpc_frame) -> tool_call` |
| IF-MC-INT-002 | ausgehend | COMP-MC-003 RequirementsToolGroup | `execute_tool(tool_name, params, auth_context) -> ToolResult` |
| IF-MC-INT-003 | ausgehend | COMP-MC-004 ArchitectureToolGroup | `execute_tool(tool_name, params, auth_context) -> ToolResult` |
| IF-MC-INT-004 | ausgehend | COMP-MC-005 TestToolGroup | `execute_tool(tool_name, params, auth_context) -> ToolResult` |
| IF-MC-INT-005 | ausgehend | COMP-MC-006 CrossCuttingToolGroup | `execute_tool(tool_name, params, auth_context) -> ToolResult` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-MC-EXT-OUT-002 | ausgehend | AuthAndTenancy | data | API-Key-Validierung, Agent-Identitaet, Tenant, Rollen |
| IF-MC-EXT-OUT-004 | ausgehend | PresetConfigEngine | data | Preset-Abfrage fuer aktiven Workspace |

---

## L3 Komponenten-Anforderungen

### REQ-L3-MC002-001: API-Key-Validierung und Auth-Kontext-Aufbau

Die ToolRegistry SHALL fuer jeden eingehenden Dispatch-Aufruf den API-Key an AuthAndTenancy (IF-MC-EXT-OUT-002) zur Validierung weiterleiten. Bei gueltiger Validierung SHALL ein Auth-Kontext (Agent-Identitaet, Tenant-ID, Rollen) aufgebaut und allen nachgelagerten `execute_tool`-Aufrufen mitgegeben werden. Bei ungueltiger Validierung SHALL die ToolRegistry einen `AUTH_FAILED`-Fehler zurueckgeben, ohne die Tool-Gruppe zu involvieren.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Valid API-Key → AuthContext with agent identity, tenant ID, and roles built
- [ ] Invalid API-Key → error `AUTH_FAILED` returned, no tool group invoked
- [ ] Auth context is propagated to all `execute_tool` calls (IF-MC-INT-002..005)
- [ ] API-Key is not passed to tool groups or ApplicationService

---

### REQ-L3-MC002-002: RBAC-Pruefung vor schreibenden Operationen

Die ToolRegistry SHALL vor jedem `execute_tool`-Aufruf fuer schreibende Operationen (create, update, link, decompose) pruefen, ob die Rolle im Auth-Kontext die Operation erlaubt. Bei unzureichender Berechtigung SHALL ein `PERMISSION_DENIED`-Fehler zurueckgegeben werden, ohne die Tool-Gruppe aufzurufen. Lesende Operationen (get, query, search) DUERFEN NICHT durch RBAC blockiert werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Write operation with `Viewer` role → error `PERMISSION_DENIED`, tool group not invoked
- [ ] Write operation with `Editor` role → dispatched to tool group
- [ ] Read operation with any valid role → dispatched to tool group without RBAC check
- [ ] RBAC decision is logged with agent identity and operation name

---

### REQ-L3-MC002-003: Preset-basierter Tool-Filter

Die ToolRegistry SHALL vor jedem `execute_tool`-Aufruf das aktive Preset des Workspaces ueber PresetConfigEngine (IF-MC-EXT-OUT-004) abfragen. Tools, die im aktiven Preset nicht aktiviert sind, SHALL mit Fehler `FEATURE_NOT_ENABLED` abgelehnt werden. Die Preset-Konfiguration SOLL gecacht werden und nicht bei jedem Aufruf neu abgefragt werden muessen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Minimal-preset active → only permitted tools callable; others → `FEATURE_NOT_ENABLED`
- [ ] Extended-preset active → all 20 tools callable
- [ ] Preset cache invalidated when workspace preset changes
- [ ] `FEATURE_NOT_ENABLED` error returned before tool group is invoked

---

### REQ-L3-MC002-004: Tool-Routing zu Tool-Gruppen

Die ToolRegistry SHALL jeden validierten und autorisierten `execute_tool`-Aufruf anhand des Tool-Namens-Praefix (requirement.*, architecture.*, test.*, traceability.*, artifact.*, workspace.*) an die korrekte Tool-Gruppe (IF-MC-INT-002..005) routen. Bei unbekanntem Tool-Namen SHALL ein strukturierter Fehler `UNKNOWN_TOOL` zurueckgegeben werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `requirement.*` → routed to RequirementsToolGroup via IF-MC-INT-002
- [ ] `architecture.*` → routed to ArchitectureToolGroup via IF-MC-INT-003
- [ ] `test.*` → routed to TestToolGroup via IF-MC-INT-004
- [ ] `traceability.*`, `artifact.*`, `workspace.*` → routed to CrossCuttingToolGroup via IF-MC-INT-005
- [ ] Unknown tool name → error `UNKNOWN_TOOL` returned

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
