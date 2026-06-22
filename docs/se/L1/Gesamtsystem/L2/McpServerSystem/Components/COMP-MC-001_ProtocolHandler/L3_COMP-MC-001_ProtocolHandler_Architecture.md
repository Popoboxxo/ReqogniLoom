---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 ProtocolHandler Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-MC-001_ProtocolHandler
> **Parent:** L2_McpServerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der ProtocolHandler ist die einzige Komponente mit direktem Zugang zur externen Systemgrenze. Er empfängt MCP-Anfragen über drei Transportprotokolle (stdio, SSE, HTTP), validiert die JSON-RPC-Frames gegen das MCP-Protokollschema, extrahiert den API-Key und leitet validierte Frames an die ToolRegistry weiter. Er serialisiert ToolResult-Objekte zurück in das transportspezifische Antwortformat und stellt sicher, dass jeder Request/Response-Pair eineindeutig korreliert ist.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ProtocolHandler` (Klasse):** Zentrale Request/Response-Ochestration.
- **`TransportAdapter` (Abstrakte Klasse):** Abstraktion über stdio/SSE/HTTP.
- **`StdioTransportAdapter` (Klasse, extends TransportAdapter):** Implementierung für stdio.
- **`SseTransportAdapter` (Klasse, extends TransportAdapter):** Implementierung für SSE.
- **`HttpTransportAdapter` (Klasse, extends TransportAdapter):** Implementierung für HTTP.
- **`JsonRpcValidator` (Helper-Klasse):** JSON-RPC-Schema-Validierung.
- **`ErrorFormatter` (Helper-Klasse):** Strukturierte Fehlerformatierung nach REQ-L2-MC-011.

### 2.2 Datenstrukturen

- **Request-Frame (JSON-RPC):**
  - `jsonrpc`: str (fixed: "2.0")
  - `method`: str (Tool-Name)
  - `params`: dict (Tool-Parameter)
  - `id`: int | str (Request-ID)
  - **Custom Fields:**
    - `api_key`: str (Header oder in params)

- **Response-Frame (JSON-RPC):**
  - `jsonrpc`: str (fixed: "2.0")
  - `result`: dict | None (ToolResult bei Erfolg)
  - `error`: dict | None (ErrorFormatter-Output bei Fehler)
  - `id`: int | str (matching Request-ID)

- **ErrorResponse (REQ-L2-MC-011 Format):**
  - `error_code`: str (z.B. "VALIDATION_ERROR", "AUTH_FAILED")
  - `message`: str (human-readable)
  - `details`: dict | None (optional, technische Details)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-MC001-001 (Transport-Abstraktionv) | TransportAdapter-Interface: read_request() → Frame, write_response() → serialized. Konkrete Implementierungen für stdio, SSE, HTTP. ProtocolHandler bleibt transport-agnostisch. |
| REQ-L3-MC001-002 (JSON-RPC-Validierung) | JsonRpcValidator: Prüft method, id, JSON-Syntax vor Dispatch. Invalid → ErrorResponse, kein Dispatch. |
| REQ-L3-MC001-003 (API-Key-Extraktion) | ProtocolHandler extrahiert api_key aus Request (Header oder params, transport-abhängig). Fehlt der Key → sofort ErrorResponse `AUTH_FAILED`, kein Dispatch. Key wird nicht gelogged (nur Hash in Logs). |
| REQ-L3-MC001-004 (Response-Serialisierung) | ProtocolHandler mappt ToolResult → Response-Frame mit matching `id`. Concurrent-Requests: Request-ID-Tracking verhindert Mismatch. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-MC-EXT-IN-001:** MCP-Protokoll über stdio, SSE, HTTP mit API-Key.

- **Ausgänge (Outbound):**
  - **IF-MC-INT-001:** Aufruf an ToolRegistry: `dispatch_request(json_rpc_frame) -> ToolResult`.
  - **IF-MC-EXT-OUT-001:** Strukturierte Tool-Response (JSON) an AI-Agent.

---

## 5. Architectural Rationale

**ADR-L3-MC001-01 — TransportAdapter-Pattern**
*Entscheidung:* Transport-Logik ist in spezifische Adapter-Klassen ausgelagert, ProtocolHandler bleibt agnostisch.
*Rationale:* Entkopplung, einfach neue Transporte hinzufügbar. Erfüllt REQ-L3-MC001-001 (Transport-Transparenz).
*Alternative abgelehnt:* Monolithischer ProtocolHandler mit if-statements für jeden Transport — Wartungsnightmare.

**ADR-L3-MC001-02 — Early JSON-RPC-Validierung**
*Entscheidung:* Validierung erfolgt BEVOR ToolRegistry involviert wird.
*Rationale:* Fail-fast, spart Ressourcen. Erfüllt REQ-L3-MC001-002.
*Alternative abgelehnt:* Validierung im ToolRegistry — würde zu späten Fehler-Berichte führen.

**ADR-L3-MC001-03 — API-Key in Dispatch-Frame mitgeben**
*Entscheidung:* Extrahierter API-Key wird als Teil der Dispatch-Nachricht an ToolRegistry weitergegeben.
*Rationale:* ToolRegistry braucht Key zur Authentifizierung. Erfüllt REQ-L3-MC001-003.
*Alternative abgelehnt:* Key in separatem Channel — würde Request/Auth-Koppelung verlieren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
