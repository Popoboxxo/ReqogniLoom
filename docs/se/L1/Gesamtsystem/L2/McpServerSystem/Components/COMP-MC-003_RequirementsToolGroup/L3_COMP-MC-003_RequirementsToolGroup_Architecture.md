---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 RequirementsToolGroup Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-MC-003_RequirementsToolGroup
> **Parent:** L2_McpServerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die RequirementsToolGroup implementiert die sechs Requirements-Tools: `requirement.get`, `requirement.query`, `requirement.create`, `requirement.update`, `requirement.decompose` und `requirement.validate`. Sie empfängt autorisierte execute_tool-Aufrufe vom ToolRegistry, validiert die Eingabeparameter gegen dedizierte JSON-Schemas, prüft LLM-Verfügbarkeit für LLM-abhängige Tools und delegiert Domain-Operationen an den ApplicationService. Sie erzeugt AuditLog-Einträge für schreibende Operationen und gibt strukturierte ToolResult-Objekte zurück.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`RequirementsToolGroup` (Klasse):** Zentrale Tool-Implementierungen und Dispatcher.
- **`RequirementGetTool` (Klasse):** Implementierung von `requirement.get`.
- **`RequirementQueryTool` (Klasse):** Implementierung von `requirement.query`.
- **`RequirementCreateTool` (Klasse):** Implementierung von `requirement.create`.
- **`RequirementUpdateTool` (Klasse):** Implementierung von `requirement.update`.
- **`RequirementDecomposeTool` (Klasse):** Implementierung von `requirement.decompose` (LLM-abhängig).
- **`RequirementValidateTool` (Klasse):** Implementierung von `requirement.validate` (LLM-abhängig).
- **`JsonSchemaValidator` (Helper):** Parameter-Validierung gegen JSON-Schema pro Tool.

### 2.2 Datenstrukturen

- **Tool-Parameter-Schemas (JSON-Schema):**
  - `requirement.get`: { "id": { "type": "string", "required": true } }
  - `requirement.query`: { "filter": { "type": "object" }, "page": { "type": "integer" }, "limit": { "type": "integer" } }
  - `requirement.create`: { "title": { "type": "string", "required": true }, "description": { "type": "string" }, ... }
  - `requirement.update`: { "id": { "type": "string", "required": true }, "data": { "type": "object" }, ... }
  - `requirement.decompose`: { "requirement_id": { "type": "string", "required": true } } (requires LLM)
  - `requirement.validate`: { "requirement_id": { "type": "string", "required": true } } (requires LLM)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-MC003-001 (Sechs Tools) | Jedes Tool hat eigene Klasse mit execute()-Methode. Parameter-Validierung via JsonSchemaValidator. Bei Fehler: ToolResult mit VALIDATION_ERROR. Bei Erfolg: ApplicationService-Aufruf, ToolResult mit Ergebnis. |
| REQ-L3-MC003-002 (LLM-Abhängige Tools) | `requirement.decompose` und `requirement.validate`: Check `LLM_PROVIDER` env var BEVOR ApplicationService-Aufruf. Nicht konfiguriert: sofort ToolResult mit LLM_NOT_CONFIGURED, kein Service-Call. |
| REQ-L3-MC003-003 (AuditLog) | Write-Tools (create, update, decompose): ApplicationService-Call mit audit-enabled flag. Nach erfolgreicher Operation: AuditLog-Eintrag mit agent_id, api_key_hash, tool_name, entity_id, timestamp. Synchron vor ToolResult-Rückgabe. Read-Tools: kein AuditLog. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-MC-INT-002:** Aufruf vom ToolRegistry: `execute_tool(tool_name, params, auth_context) -> ToolResult`.

- **Ausgänge (Outbound):**
  - **IF-MC-EXT-OUT-003:** Aufruf an ApplicationService: `get_requirement()`, `query_requirements()`, `create_requirement()`, `update_requirement()`, `decompose_requirement()`, `validate_requirement()`. Alle mit auth_context und audit-enabled flag.

---

## 5. Architectural Rationale

**ADR-L3-MC003-01 — Dedizierte Klasse pro Tool**
*Entscheidung:* Jedes Tool hat eigene Klasse (RequirementGetTool, RequirementCreateTool, etc.).
*Rationale:* Klare Separation of Concerns, einfach neue Tools hinzufügbar ohne monolithe Klasse. Erfüllt REQ-L3-MC003-001.
*Alternative abgelehnt:* Single RequirementsToolGroup-Klasse mit if-statements — zu groß und wartungsunfreundlich.

**ADR-L3-MC003-02 — Early LLM-Availability-Check**
*Entscheidung:* LLM-Verfügbarkeit wird geprüft BEVOR ApplicationService aufgerufen wird.
*Rationale:* Fail-fast, spart ApplicationService-Ressourcen. Erfüllt REQ-L3-MC003-002.
*Alternative abgelehnt:* LLM-Check im ApplicationService — würde zu spät scheitern.

**ADR-L3-MC003-03 — AuditLog via ApplicationService-Flag**
*Entscheidung:* Write-Tools setzen audit-enabled-Flag im ApplicationService-Call. Service handled Audit-Logging.
*Rationale:* Zentrale Audit-Logik im ApplicationService, Tool-Gruppe muss nicht selbst mit AuditLog interagieren. Erfüllt REQ-L3-MC003-003.
*Alternative abgelehnt:* Tool-Gruppe schreibt direkt zu AuditLog — würde Duplizierung mit anderen Komponenten führen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
