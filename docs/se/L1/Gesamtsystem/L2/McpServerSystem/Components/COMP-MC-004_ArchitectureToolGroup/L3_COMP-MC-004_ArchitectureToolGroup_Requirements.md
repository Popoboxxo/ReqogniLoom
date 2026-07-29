---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 ArchitectureToolGroup Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-MC-004_ArchitectureToolGroup
> **Parent:** L2_McpServerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die ArchitectureToolGroup implementiert die fünf Architecture-Tools: `architecture.get`, `architecture.query`, `architecture.create`, `architecture.update` und `architecture.link`. Sie empfängt autorisierte execute_tool-Aufrufe vom ToolRegistry, validiert Parameter gegen dedizierte JSON-Schemas und delegiert Domain-Operationen an den ApplicationService. Das Tool `architecture.link` erzeugt TraceLinks zwischen ArchitectureElements und anderen Artefakten (Requirements, TestCases, andere ArchitectureElements). Sie erzeugt AuditLog-Einträge für alle schreibenden Operationen.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ArchitectureToolGroup` (Klasse):** Zentrale Tool-Implementierungen und Dispatcher.
- **`ArchitectureGetTool` (Klasse):** Implementierung von `architecture.get`.
- **`ArchitectureQueryTool` (Klasse):** Implementierung von `architecture.query`.
- **`ArchitectureCreateTool` (Klasse):** Implementierung von `architecture.create`.
- **`ArchitectureUpdateTool` (Klasse):** Implementierung von `architecture.update`.
- **`ArchitectureLinkTool` (Klasse):** Implementierung von `architecture.link` — erstellt TraceLinks.
- **`JsonSchemaValidator` (Helper):** Parameter-Validierung.

### 2.2 Datenstrukturen

- **Tool-Parameter-Schemas (JSON-Schema):**
  - `architecture.create`: { "title": required, "description": required, "element_type": required (enum), "workspace_id": required }
  - `architecture.update`: { "id": required, "data": required (object) }
  - `architecture.link`: { "arch_id": required, "target_id": required, "target_type": required (enum: requirement|testcase|architecture), "link_type": required (enum: implements|verified_by|composed_of|...) }
  - `architecture.get`: { "id": required }
  - `architecture.query`: { "filter": object, "page": integer, "limit": integer }

- **ArchitectureElement (Domain):**
  - `id`: UUID
  - `title`: str
  - `description`: str
  - `element_type`: str (enum: subsystem, component, interface, etc.)
  - `workspace_id`: UUID
  - `created_at`: datetime

- **TraceLink (Domain):**
  - `id`: UUID (auto-generated)
  - `source_id`: UUID (ArchitectureElement)
  - `target_id`: UUID (Requirement | TestCase | ArchitectureElement)
  - `target_type`: str (enum)
  - `link_type`: str (enum)
  - `created_at`: datetime

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-MC004-001 (Fünf Tools) | Jedes Tool hat eigene Klasse mit execute()-Methode. Parameter-Validierung via JsonSchemaValidator. `architecture.create` mit Pflicht-Parametern (title, description, element_type, workspace_id) → ArchitectureElement mit UUID. |
| REQ-L3-MC004-002 (TraceLink-Erzeugung) | `architecture.link`: Validiert link_type, delegiert an ApplicationService.create_trace_link(arch_id, target_id, target_type, link_type). Rückgabe: ToolResult mit TraceLink-ID und Status. |
| REQ-L3-MC004-003 (AuditLog) | Write-Tools (create, update, link): ApplicationService-Call mit audit-enabled flag. Nach Erfolg: AuditLog-Eintrag mit agent_id, api_key_hash, tool_name, entity_id(s). Für link: zusätzlich TraceLink-ID. Synchron vor ToolResult. Read-Tools: kein AuditLog. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-MC-INT-003:** Aufruf vom ToolRegistry: `execute_tool(tool_name, params, auth_context) -> ToolResult`.

- **Ausgänge (Outbound):**
  - **IF-MC-EXT-OUT-003:** Aufruf an ApplicationService: `get_architecture_element()`, `query_architecture_elements()`, `create_architecture_element()`, `update_architecture_element()`, `create_trace_link()`. Alle mit auth_context und audit-enabled flag.

---

## 5. Architectural Rationale

**ADR-L3-MC004-01 — TraceLink als separater ApplicationService-Call**
*Entscheidung:* `architecture.link` delegiert TraceLink-Erstellung an spezialisierten ApplicationService-Endpunkt `create_trace_link()`, nicht als Update auf ArchitectureElement.
*Rationale:* Klare Separation: ArchitectureElement ist Entität, TraceLink ist separate Relation. Erfüllt REQ-L3-MC004-002.
*Alternative abgelehnt:* TraceLinks als Teil von ArchitectureElement — würde Datenmodell komplizieren.

**ADR-L3-MC004-02 — Dedizierte Tool-Klassen**
*Entscheidung:* Jedes Tool hat eigene Klasse wie in RequirementsToolGroup.
*Rationale:* Konsistent mit anderen Tool-Gruppen, skalierbar. Erfüllt REQ-L3-MC004-001.
*Alternative abgelehnt:* Monolithe Klasse — wartungsunfreundlich.

**ADR-L3-MC004-03 — Validierter link_type vor ApplicationService**
*Entscheidung:* `architecture.link` validiert link_type gegen enum BEVOR ApplicationService-Call.
*Rationale:* Fail-fast, gibt klare Fehler-Meldung bei ungültigen link_type. Erfüllt REQ-L3-MC004-002.
*Alternative abgelehnt:* ApplicationService-Validierung — würde zu spät fehlschlagen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
