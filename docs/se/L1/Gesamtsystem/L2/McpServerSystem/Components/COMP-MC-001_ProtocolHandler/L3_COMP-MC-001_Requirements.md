# L3 ProtocolHandler Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-MC-001 — ProtocolHandler
> **Parent-System:** McpServerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Transport-Protokoll-Abstraktion (stdio, SSE, HTTP), JSON-RPC-Frame-Validierung, Request/Response-Handling. Der ProtocolHandler ist die einzige Komponente mit Zugang zur externen Systemgrenze. Er nimmt eingehende MCP-Anfragen entgegen, validiert den JSON-RPC-Frame und leitet valide Frames an die ToolRegistry weiter. Er nimmt ToolResult-Objekte entgegen und serialisiert sie in das transportspezifische Antwortformat.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-MC-005 | Mindestens drei Transportprotokolle: stdio, SSE, HTTP; transparent fuer Tool-Handler |
| REQ-L2-MC-006 | API-Key vor jeder Tool-Ausfuehrung an AuthAndTenancy weiterleiten; AUTH_FAILED bei fehlendem/ungueltigen Key |
| REQ-L2-MC-010 | p95-Antwortzeit < 200ms fuer Standard-Requests unter 50 gleichzeitigen Agenten |
| REQ-L2-MC-011 | Strukturierte JSON-Fehlerantwort mit error_code, message, details |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-MC-INT-001 | ausgehend | COMP-MC-002 ToolRegistry | `dispatch_request(json_rpc_frame) -> tool_call` |
| IF-MC-INT-006 | eingehend | COMP-MC-003..006 ToolGroups | `ToolResult -> JSON-Response` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-MC-EXT-IN-001 | eingehend | AI-Agent | data | MCP-Protokoll (JSON-RPC ueber stdio/SSE/HTTP) mit API-Key |
| IF-MC-EXT-OUT-001 | ausgehend | AI-Agent | data | Strukturierte Tool-Response (JSON) oder Fehler |

---

## L3 Komponenten-Anforderungen

### REQ-L3-MC001-001: Transport-Protokoll-Unterstuetzung


**Implementation State:** Implemented
**Review Findings:** `McpSseTransportView` verarbeitet SSE asynchron über Redis.
**Test Status:** Covered
**Remarks:** HTTP POST 202 Accepted ist standardkonform umgesetzt.


Der ProtocolHandler SHALL MCP-Anfragen ueber alle drei Transportprotokolle stdio, SSE und HTTP empfangen und beantworten. Das verwendete Transportprotokoll SHALL fuer die nachgelagerten Komponenten vollstaendig transparent sein; der interne Dispatch-Aufruf (IF-MC-INT-001) DARF KEINE transportspezifischen Informationen enthalten.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] MCP tool call via stdio → correctly dispatched and responded
- [ ] MCP tool call via SSE → correctly dispatched and responded
- [ ] MCP tool call via HTTP → correctly dispatched and responded
- [ ] Internal dispatch call contains no transport-specific fields

---

### REQ-L3-MC001-002: JSON-RPC-Frame-Validierung


**Implementation State:** Implemented
**Review Findings:** Standardkonforme `protocol_handler.py` verarbeitet `initialize`, `tools/list` und `tools/call`.
**Test Status:** Covered
**Remarks:** Vollständige JSON-RPC Fehlerbehandlung integriert.


Der ProtocolHandler SHALL eingehende JSON-RPC-Frames gegen das MCP-Protokollschema validieren, bevor ein Dispatch erfolgt. Frames mit fehlendem `method`-Feld, ungueltiger `id`, fehlerhaftem JSON oder unbekanntem MCP-Methoden-Typ SHALL mit einem strukturierten Fehler gemaess REQ-L2-MC-011 abgelehnt werden, ohne dass die ToolRegistry involviert wird.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Frame with missing `method` field → error `VALIDATION_ERROR` returned, no dispatch
- [ ] Frame with malformed JSON → error `VALIDATION_ERROR` returned, no dispatch
- [ ] Valid frame → passed to ToolRegistry via IF-MC-INT-001
- [ ] Error response matches structured format: `{"error_code": "VALIDATION_ERROR", "message": "...", "details": {...}}`

---

### REQ-L3-MC001-003: API-Key-Extraktion und -Weiterleitung


**Implementation State:** Implemented
**Review Findings:** API Key Extraktion in View Layer implementiert, wird via AuthContext übergeben.
**Test Status:** Covered
**Remarks:** Auth-Prüfung erfolgt vor Dispatch in ToolRegistry.


Der ProtocolHandler SHALL den API-Key aus dem eingehenden MCP-Request extrahieren und ihn als Teil des Dispatch-Aufrufs (IF-MC-INT-001) an die ToolRegistry uebergeben. Fehlt der API-Key im Request, SHALL der ProtocolHandler die Anfrage mit Fehler `AUTH_FAILED` unmittelbar ablehnen, ohne Dispatch.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Request without API-Key → error `AUTH_FAILED` returned immediately, no dispatch
- [ ] Request with API-Key → key forwarded as part of dispatch frame to ToolRegistry
- [ ] API-Key is not logged in plaintext (only hash permitted in logs)

---

### REQ-L3-MC001-004: Response-Serialisierung und -Routing


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der ProtocolHandler SHALL ein eingehendes `ToolResult`-Objekt (IF-MC-INT-006) korrekt in das transportspezifische JSON-Antwortformat serialisieren und an den aufrufenden AI-Agent zurueckgeben. Die Zuordnung zwischen eingehender Request-`id` und ausgehender Response-`id` SHALL eineindeutig und verlustfrei sein (kein Request/Response-Mismatch).

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] ToolResult with valid payload → serialized to JSON-RPC response with matching `id`
- [ ] Concurrent requests from multiple agents → each response routed to correct originating client
- [ ] Error ToolResult → serialized to structured error response (not raw exception)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
