---
step: interfaces
agent: se-interface-mgr
iteration: 1
status: done
timestamp: "2026-07-01T12:00:00Z"
schema_version: "1.0.0"
---

# L2 DiagramServiceSystem — Interface Registry (Phase 4)

> **Scope:** COMP-DS-006 (CanvasEditor) + COMP-DS-007 (MermaidLiveRenderer)
> **REQ:** REQ-L1-056, REQ-L1-057
> **Parent:** ARCH-L1-013 DiagramServiceSystem

## L1 Interfaces (IF-L1-058..061)

| ID | Richtung | Quelle | Ziel | Typ | Verantwortlich |
|----|----------|--------|------|-----|----------------|
| IF-L1-058 | input | ReactFrontend (001) | DiagramService (013) | REST/JSON | COMP-DS-006 |
| IF-L1-059 | input | ReactFrontend (001) | DiagramService (013) | REST/JSON | COMP-DS-007 |
| IF-L1-060 | output | DiagramService (013) | ReactFrontend (001) | REST/JSON | COMP-DS-006 |
| IF-L1-061 | output | DiagramService (013) | ReactFrontend (001) | REST/JSON | COMP-DS-007 |

## L2 Internal Interfaces (IF-DS-INT-001..009)

| ID | Quelle | Ziel | Typ | Vertrag |
|----|--------|------|-----|---------|
| IF-DS-INT-001 | 001 DiagramManager | 002 DiagramValidator | In-Process Python | `validate_payload(type, content) -> bool` |
| IF-DS-INT-002 | 001 DiagramManager | 003 DiagramRenderer | In-Process Python | `prepare_renderable(type, content) -> RenderableDiagram` |
| IF-DS-INT-003 | 001 DiagramManager | 004 TraceabilityConnector | In-Process Python | `create_document_link(diagram_id, target_id)` |
| IF-DS-INT-004 | 006 CanvasEditor | 002 DiagramValidator | In-Process Python | `validate_canvas_strokes(stroke_data: dict) -> ValidationResult` |
| IF-DS-INT-005 | 006 CanvasEditor | 001 DiagramManager | In-Process Python | `persist_canvas(name, stroke_data, tenant, user) -> Diagram` |
| IF-DS-INT-006 | 006 CanvasEditor | 004 TraceabilityConnector | In-Process Python | `link_canvas_to_artifact(diagram_id, target_id) -> TraceLink` |
| IF-DS-INT-007 | 007 MermaidLiveRenderer | 001 DiagramManager | In-Process Python | `persist_mermaid_source(name, source, tenant, user) -> Diagram` |
| IF-DS-INT-008 | 007 MermaidLiveRenderer | 003 DiagramRenderer | In-Process Python | `get_render_hints(diagram_type, payload_format) -> RenderHint` |
| IF-DS-INT-009 | 007 MermaidLiveRenderer | 005 McpArtifactProvider | In-Process Python | `register_mcp_type(diagram_type, payload_format) -> None` |

## Propagation Map

| Sub-System | Inherited External | New Internal Incoming | New Internal Outgoing |
|------------|-------------------|-----------------------|-----------------------|
| COMP-DS-006 | IF-L1-058, IF-L1-060 | — | IF-DS-INT-004, IF-DS-INT-005, IF-DS-INT-006 |
| COMP-DS-007 | IF-L1-059, IF-L1-061 | — | IF-DS-INT-007, IF-DS-INT-008, IF-DS-INT-009 |

## JSON Output

```json
{
  "internal_interfaces": [
    {
      "source_id": "COMP-DS-001",
      "target_id": "COMP-DS-002",
      "interface_type": "in-process_python",
      "data_payload": "validate_payload(type, content) -> bool",
      "version": "1.0.0",
      "preconditions": ["DiagramManager has valid payload data"],
      "postconditions": ["ValidationResult returned; error raised on invalid payload"],
      "invariants": ["IF-DS-INT-001 remains available for all diagram types"]
    },
    {
      "source_id": "COMP-DS-001",
      "target_id": "COMP-DS-003",
      "interface_type": "in-process_python",
      "data_payload": "prepare_renderable(type, content) -> RenderableDiagram",
      "version": "1.0.0",
      "preconditions": ["Payload validated via IF-DS-INT-001"],
      "postconditions": ["RenderableDiagram with SVG representation returned"],
      "invariants": ["IF-DS-INT-002 never triggers database writes"]
    },
    {
      "source_id": "COMP-DS-001",
      "target_id": "COMP-DS-004",
      "interface_type": "in-process_python",
      "data_payload": "create_document_link(diagram_id, target_id)",
      "version": "1.0.0",
      "preconditions": ["Diagram exists in persistence layer"],
      "postconditions": ["TraceLink of type 'documents' created"],
      "invariants": ["IF-DS-INT-003 is idempotent for same (diagram_id, target_id)"]
    },
    {
      "source_id": "COMP-DS-006",
      "target_id": "COMP-DS-002",
      "interface_type": "in-process_python",
      "data_payload": "validate_canvas_strokes(stroke_data: dict) -> ValidationResult",
      "version": "1.0.0",
      "preconditions": ["CanvasEditor has collected stroke_data from user interaction"],
      "postconditions": ["Stroke structure validated; syntax errors returned"],
      "invariants": ["IF-DS-INT-004 never mutates stroke_data"]
    },
    {
      "source_id": "COMP-DS-006",
      "target_id": "COMP-DS-001",
      "interface_type": "in-process_python",
      "data_payload": "persist_canvas(name, stroke_data, tenant, user) -> Diagram",
      "version": "1.0.0",
      "preconditions": ["Stroke data validated via IF-DS-INT-004", "Auth context valid"],
      "postconditions": ["Diagram entity with type='canvas' persisted", "Version created"],
      "invariants": ["IF-DS-INT-005 always creates a new version on update"]
    },
    {
      "source_id": "COMP-DS-006",
      "target_id": "COMP-DS-004",
      "interface_type": "in-process_python",
      "data_payload": "link_canvas_to_artifact(diagram_id, target_id) -> TraceLink",
      "version": "1.0.0",
      "preconditions": ["Diagram exists", "Target artifact exists"],
      "postconditions": ["TraceLink of type 'documents' created in TraceabilityEngine"],
      "invariants": ["IF-DS-INT-006 never overwrites existing links"]
    },
    {
      "source_id": "COMP-DS-007",
      "target_id": "COMP-DS-001",
      "interface_type": "in-process_python",
      "data_payload": "persist_mermaid_source(name, source, tenant, user) -> Diagram",
      "version": "1.0.0",
      "preconditions": ["Mermaid source validated via IF-DS-INT-008", "Auth context valid"],
      "postconditions": ["Diagram entity with type='mermaid' persisted", "Version created"],
      "invariants": ["IF-DS-INT-007 always creates a new version on update"]
    },
    {
      "source_id": "COMP-DS-007",
      "target_id": "COMP-DS-003",
      "interface_type": "in-process_python",
      "data_payload": "get_render_hints(diagram_type, payload_format) -> RenderHint",
      "version": "1.0.0",
      "preconditions": ["Mermaid source is valid", "DiagramRenderer initialized"],
      "postconditions": ["Render hints returned with supported Mermaid theme config"],
      "invariants": ["IF-DS-INT-008 never returns stale hints"]
    },
    {
      "source_id": "COMP-DS-007",
      "target_id": "COMP-DS-005",
      "interface_type": "in-process_python",
      "data_payload": "register_mcp_type(diagram_type, payload_format) -> None",
      "version": "1.0.0",
      "preconditions": ["Mermaid diagram type is supported", "McpArtifactProvider initialized"],
      "postconditions": ["Mermaid type registered in MCP tool groups", "artifact.get can return Mermaid source"],
      "invariants": ["IF-DS-INT-009 is idempotent for same (diagram_type, payload_format)"]
    }
  ],
  "propagation_map": {
    "COMP-DS-006": {
      "inherited_external": ["IF-L1-058", "IF-L1-060"],
      "new_internal_incoming": [],
      "new_internal_outgoing": ["IF-DS-INT-004", "IF-DS-INT-005", "IF-DS-INT-006"]
    },
    "COMP-DS-007": {
      "inherited_external": ["IF-L1-059", "IF-L1-061"],
      "new_internal_incoming": [],
      "new_internal_outgoing": ["IF-DS-INT-007", "IF-DS-INT-008", "IF-DS-INT-009"]
    }
  }
}
```

## Collision Note

> **ID-Kollision (Phase 4 → L2-Architektur):** IF-DS-INT-004..009 wurden in der initialen `L2_DiagramServiceSystem_Architecture.md` mit abweichenden Source/Target-Paarungen definiert. Die Registry verwendet die aktualisierten Definitionen aus der L1-Gesamtarchitektur. L2-Architektur benachrichtigt zur Konsolidierung.

## Registrierte Interfaces

- IF-L1-058: ReactFrontend (001) → DiagramService (013) — Canvas Auto-Save Push
- IF-L1-059: ReactFrontend (001) → DiagramService (013) — Mermaid Source Update
- IF-L1-060: DiagramService (013) → ReactFrontend (001) — Canvas Stroke-Daten + Export
- IF-L1-061: DiagramService (013) → ReactFrontend (001) — Mermaid Source + Render + Export
- IF-DS-INT-001: DiagramManager → DiagramValidator (preexisting, now registered)
- IF-DS-INT-002: DiagramManager → DiagramRenderer (preexisting, now registered)
- IF-DS-INT-003: DiagramManager → TraceabilityConnector (preexisting, now registered)
- IF-DS-INT-004: CanvasEditor → DiagramValidator — Canvas stroke validation
- IF-DS-INT-005: CanvasEditor → DiagramManager — Canvas persist
- IF-DS-INT-006: CanvasEditor → TraceabilityConnector — Canvas trace link
- IF-DS-INT-007: MermaidLiveRenderer → DiagramManager — Mermaid persist
- IF-DS-INT-008: MermaidLiveRenderer → DiagramRenderer — Render hints
- IF-DS-INT-009: MermaidLiveRenderer → McpArtifactProvider — MCP type registration
