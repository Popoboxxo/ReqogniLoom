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

Der ProtocolHandler ist die einzige Komponente mit direktem Zugang zur externen Systemgrenze. Er empfängt MCP-Anfragen über HTTP (POST für Messages, GET für SSE Streaming), validiert die JSON-RPC-Frames gegen das MCP-Protokollschema, extrahiert den API-Key und leitet validierte Frames an die ToolRegistry weiter. Die asynchrone SSE-Rückkanal-Kommunikation in Django wird durch Redis PubSub realisiert. Er serialisiert ToolResult-Objekte zurück in das transportspezifische Antwortformat und stellt sicher, dass jeder Request/Response-Pair eineindeutig korreliert ist. Zusätzlich verwaltet er den MCP Lifecycle (`initialize`, `ping`, `tools/list`).

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ProtocolHandler` (Klasse in `protocol_handler.py`):** Zentrale Lifecycle- und JSON-RPC-Orchestrierung (`initialize`, `ping`, `tools/list`, `tools/call`).
- **`McpMessagesView` (Django View):** Nimmt HTTP POST Anfragen (`/messages/`) entgegen, antwortet sofort mit HTTP 202 Accepted und delegiert die Ausführung an einen Worker-Thread.
- **`McpSseTransportView` (Django View):** Liefert asynchrone Server-Sent Events über eine StreamingHttpResponse aus.
- **`RedisSsePubSub` (Klasse in `sse_pubsub.py`):** Brücke zwischen synchronen Django-Threads und dem asynchronen SSE-Rückkanal via Redis.

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


## Derived L3 Requirements for Unmapped L2

### REQ-L3-MC001-U000: Auto-derived from REQ-L2-MCP-007
Abgeleitet von: REQ-L2-MCP-007

### REQ-L3-MC001-U001: Auto-derived from REQ-L2-MCP-002
Abgeleitet von: REQ-L2-MCP-002

### REQ-L3-MC001-U002: Auto-derived from REQ-L2-MCP-013
Abgeleitet von: REQ-L2-MCP-013

### REQ-L3-MC001-U003: Auto-derived from REQ-L2-MCP-001
Abgeleitet von: REQ-L2-MCP-001

### REQ-L3-MC001-U004: Auto-derived from REQ-L2-MCP-003
Abgeleitet von: REQ-L2-MCP-003

### REQ-L3-MC001-U005: Auto-derived from REQ-L2-MCP-006
Abgeleitet von: REQ-L2-MCP-006

### REQ-L3-MC001-U006: Auto-derived from REQ-L2-MCP-008
Abgeleitet von: REQ-L2-MCP-008

### REQ-L3-MC001-U007: Auto-derived from REQ-L2-MCP-010
Abgeleitet von: REQ-L2-MCP-010

### REQ-L3-MC001-U008: Auto-derived from REQ-L2-MCP-011
Abgeleitet von: REQ-L2-MCP-011

### REQ-L3-MC001-U009: Auto-derived from REQ-L2-MCP-014
Abgeleitet von: REQ-L2-MCP-014

### REQ-L3-MC001-U010: Auto-derived from REQ-L2-MCP-004
Abgeleitet von: REQ-L2-MCP-004

### REQ-L3-MC001-U011: Auto-derived from REQ-L2-MCP-005
Abgeleitet von: REQ-L2-MCP-005

### REQ-L3-MC001-U012: Auto-derived from REQ-L2-MCP-012
Abgeleitet von: REQ-L2-MCP-012

### REQ-L3-MC001-U013: Auto-derived from REQ-L2-MCP-009
Abgeleitet von: REQ-L2-MCP-009
