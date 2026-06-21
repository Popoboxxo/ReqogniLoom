# L3 TestToolGroup Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-MC-005 — TestToolGroup
> **Parent-System:** McpServerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Implementierung der fuenf Test-Tools: `test.get`, `test.query`, `test.create`, `test.update` und `test.link`. Die Gruppe ermoeglicht AI-Agenten das Erstellen, Lesen, Aktualisieren und Verknuepfen von Testfaellen. Insbesondere wird das Schreiben von Test-Ergebnissen (Passed/Failed/Not Run) und die nachtraegliche TraceLink-Erzeugung vom Typ `verifies` unterstuetzt.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-MC-003 | Fuenf Test-Tools; test.update schreibt Test-Status; test.link erzeugt TraceLink `verifies` |
| REQ-L2-MC-009 | Direkter ApplicationService-Zugriff via In-Process-Python; keine HTTP-Roundtrips |
| REQ-L2-MC-012 | AuditLog-Eintrag bei jeder schreibenden Operation; synchron vor Response |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-MC-INT-004 | eingehend | COMP-MC-002 ToolRegistry | `execute_tool(tool_name, params, auth_context) -> ToolResult` |
| IF-MC-INT-006 | ausgehend | COMP-MC-001 ProtocolHandler | `ToolResult -> JSON-Response` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-MC-EXT-OUT-003 | ausgehend | ApplicationService | data | Use-Case-Methoden (In-Process Python); inkl. AuditLog-Schreiben |

---

## L3 Komponenten-Anforderungen

### REQ-L3-MC005-001: Implementierung der fuenf Test-Tools

Die TestToolGroup SHALL die fuenf Tools `test.get`, `test.query`, `test.create`, `test.update` und `test.link` implementieren. `test.create` SHALL als Pflichtparameter `title`, `type` und optional `linked_req_id` unterstuetzen; bei Angabe von `linked_req_id` SHALL automatisch ein TraceLink vom Typ `verifies` erzeugt werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] All 5 tools callable via `execute_tool` interface with correctly serialized results
- [ ] `test.create(title, type, linked_req_id)` → TestCase with UUID and optional TraceLink `verifies`
- [ ] `test.create(title, type)` without `linked_req_id` → TestCase without TraceLink
- [ ] `test.get(id)` → TestCase with status, linked requirements, and audit fields
- [ ] `test.query(filter)` → paginated list matching filter criteria
- [ ] Missing required parameter → error `VALIDATION_ERROR`

---

### REQ-L3-MC005-002: Test-Status-Aktualisierung via test.update

Das Tool `test.update` SHALL das Schreiben des Test-Status (Passed, Failed, Not Run) fuer einen bestehenden TestCase ermgoelichen. Der Status SHALL gegen die erlaubten Werte validiert werden. Nach erfolgreicher Aktualisierung SHALL der neue Status im zurueckgegebenen TestCase-Objekt enthalten sein.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `test.update(id, {status: "Passed"})` → TestCase returned with status "Passed"
- [ ] `test.update(id, {status: "Failed"})` → TestCase returned with status "Failed"
- [ ] `test.update(id, {status: "Not Run"})` → TestCase returned with status "Not Run"
- [ ] Invalid status value → error `VALIDATION_ERROR`
- [ ] Non-existent test ID → error propagated from ApplicationService

---

### REQ-L3-MC005-003: TraceLink-Erzeugung via test.link und AuditLog

Das Tool `test.link` SHALL einen nachtraeglichen TraceLink vom Typ `verifies` zwischen einem TestCase und einem Requirement erzeugen. Fuer alle schreibenden Operationen (create, update, link) SHALL die TestToolGroup einen AuditLog-Eintrag ueber den ApplicationService erzeugen, der Agent-Identitaet, API-Key-Hash, Tool-Name, betroffene Entitaets-IDs und Zeitstempel enthaelt.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `test.link(test_id, req_id)` → TraceLink of type `verifies` created with valid ID
- [ ] `test.link` with non-existent `req_id` → error from ApplicationService propagated
- [ ] After `test.create` with `linked_req_id`: AuditLog entry contains test UUID and TraceLink ID
- [ ] After `test.update`: AuditLog entry contains agent ID, tool name, test UUID, new status
- [ ] Read operations (`get`, `query`) do NOT produce AuditLog entries

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
