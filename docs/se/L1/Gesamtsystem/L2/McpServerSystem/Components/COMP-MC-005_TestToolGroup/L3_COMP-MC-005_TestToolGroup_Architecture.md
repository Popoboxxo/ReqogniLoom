---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 TestToolGroup Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-MC-005_TestToolGroup
> **Parent:** L2_McpServerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die TestToolGroup implementiert die fünf Test-Tools: `test.get`, `test.query`, `test.create`, `test.update` und `test.link`. Sie empfängt autorisierte execute_tool-Aufrufe vom ToolRegistry, validiert Parameter gegen dedizierte JSON-Schemas und delegiert Domain-Operationen an den ApplicationService. Das Tool `test.create` unterstützt optionale automatische TraceLink-Erstellung (Typ `verifies`). Das Tool `test.update` schreibt Test-Status (Passed, Failed, Not Run). Das Tool `test.link` erzeugt nachträgliche TraceLinks zwischen TestCases und Requirements. Sie erzeugt AuditLog-Einträge für alle schreibenden Operationen.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`TestToolGroup` (Klasse):** Zentrale Tool-Implementierungen und Dispatcher.
- **`TestGetTool` (Klasse):** Implementierung von `test.get`.
- **`TestQueryTool` (Klasse):** Implementierung von `test.query`.
- **`TestCreateTool` (Klasse):** Implementierung von `test.create` — optional mit TraceLink-Erstellung.
- **`TestUpdateTool` (Klasse):** Implementierung von `test.update` — schreibt Test-Status.
- **`TestLinkTool` (Klasse):** Implementierung von `test.link` — erzeugt TraceLink `verifies`.
- **`JsonSchemaValidator` (Helper):** Parameter-Validierung.

### 2.2 Datenstrukturen

- **Tool-Parameter-Schemas (JSON-Schema):**
  - `test.create`: { "title": required, "type": required, "linked_req_id": optional, "workspace_id": required }
  - `test.update`: { "id": required, "data": required (can include status) }
  - `test.link`: { "test_id": required, "req_id": required }
  - `test.get`: { "id": required }
  - `test.query`: { "filter": object, "page": integer, "limit": integer }

- **TestCase (Domain):**
  - `id`: UUID
  - `title`: str
  - `type`: str (enum: manual, automated, exploratory, ...)
  - `status`: str (enum: "Passed", "Failed", "Not Run", default "Not Run")
  - `workspace_id`: UUID
  - `created_at`: datetime
  - `linked_requirements`: list[UUID] (Requirement-IDs connected via `verifies` TraceLinks)

- **TraceLink (via test.create with linked_req_id):**
  - `id`: UUID
  - `source_id`: UUID (TestCase)
  - `target_id`: UUID (Requirement)
  - `target_type`: str (fixed: "requirement")
  - `link_type`: str (fixed: "verifies")
  - `created_at`: datetime

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-MC005-001 (Fünf Tools) | Jedes Tool hat eigene Klasse. `test.create(title, type, linked_req_id)`: Validiere Parameter. Erstelle TestCase. Falls linked_req_id gesetzt: automatisch create_trace_link(test_id, req_id, "verifies") aufrufen. Rückgabe: ToolResult mit TestCase und optional TraceLink-ID. |
| REQ-L3-MC005-002 (Test-Status via test.update) | Validiere status gegen erlaubte Werte (Passed, Failed, Not Run). Delegiere an ApplicationService.update_test_case(id, {status: ...}). Rückgabe: ToolResult mit aktualisiertem TestCase. |
| REQ-L3-MC005-003 (TraceLink via test.link & AuditLog) | `test.link(test_id, req_id)`: Erstelle TraceLink mit link_type="verifies". AuditLog für alle schreibenden Operationen (create, update, link) mit agent_id, api_key_hash, tool_name, entity_id(s). Synchron vor ToolResult. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-MC-INT-004:** Aufruf vom ToolRegistry: `execute_tool(tool_name, params, auth_context) -> ToolResult`.

- **Ausgänge (Outbound):**
  - **IF-MC-EXT-OUT-003:** Aufruf an ApplicationService: `get_test_case()`, `query_test_cases()`, `create_test_case()`, `update_test_case()`, `create_trace_link()`. Alle mit auth_context und audit-enabled flag.

---

## 5. Architectural Rationale

**ADR-L3-MC005-01 — Automatische TraceLink-Erstellung in test.create**
*Entscheidung:* Falls `linked_req_id` in test.create-Parametern, erstelle automatisch TraceLink (Typ `verifies`).
*Rationale:* Optimales User-Experience: Ein Tool-Aufruf erzeugt sowohl TestCase als auch Link. Erfüllt REQ-L3-MC005-001 vollständig.
*Alternative abgelehnt:* Nur TestCase-Erstellung, separate test.link erforderlich — würde mehre Aufrufe erfordern.

**ADR-L3-MC005-02 — Test-Status als Update-Parameter**
*Entscheidung:* Test-Status wird via test.update geschrieben, als Update-Feld in data-Parameter.
*Rationale:* Consistent mit test-Framework-Pattern (Update = mehrere Felder möglich). Erfüllt REQ-L3-MC005-002.
*Alternative abgelehnt:* Dediziertes test.set_status-Tool — zu granular.

**ADR-L3-MC005-03 — TraceLink nur via test.link oder test.create**
*Entscheidung:* TraceLinks können entweder in test.create (automatisch) oder test.link (manuell) erzeugt werden.
*Rationale:* Flexibel für unterschiedliche Workflows. Erfüllt REQ-L3-MC005-003.
*Alternative abgelehnt:* Nur test.link zulassen — würde test.create-Convenience-Feature entfernen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
