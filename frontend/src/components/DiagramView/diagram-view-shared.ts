/**
 * ARCH-L1-001 ReactFrontend — DiagramView shared constants & styles.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-050 (Container/Presenter decomposition — shared snippets)
 *
 * Constants, form defaults and token-based style snippets shared by the
 * DiagramView container, the create form and the detail presenter. Extracted
 * from the former monolithic DiagramView so the pieces don't duplicate them.
 */

import type { DiagramType, PayloadFormat } from "../../types";

export const DIAGRAM_TYPES: DiagramType[] = [
  "block",
  "flow",
  "context",
  "canvas",
  "mermaid",
];
export const PAYLOAD_FORMATS: PayloadFormat[] = [
  "mermaid",
  "plantuml",
  "json",
  "canvas_stroke",
  "node_graph",
];

export const DEFAULT_CONTENT: Record<PayloadFormat, string> = {
  mermaid:
    "graph TD\n  A[Start] --> B{Decision}\n  B -- yes --> C[Process]\n  B -- no --> D[End]",
  plantuml:
    "@startuml\n  actor User\n  User -> App : request\n  App --> User : response\n@enduml",
  json: JSON.stringify(
    {
      nodes: [
        { id: "n1", label: "Start" },
        { id: "n2", label: "End" },
      ],
      edges: [{ from: "n1", to: "n2" }],
    },
    null,
    2,
  ),
  // canvas_stroke diagrams use the CanvasEditor UI — initial empty canvas
  canvas_stroke: '{"strokes": []}',
  // node_graph diagrams use the DiagramGraphEditor UI (GH-353 Task 8) —
  // initial empty envelope matching diagram/node_graph.py's v1 schema.
  node_graph: JSON.stringify({ schema_version: 1, nodes: [], edges: [] }),
};

export interface FormState {
  name: string;
  diagram_type: DiagramType;
  payload_format: PayloadFormat;
  content: string;
  description: string;
}

export const EMPTY_FORM: FormState = {
  name: "",
  diagram_type: "block",
  payload_format: "mermaid",
  content: DEFAULT_CONTENT.mermaid,
  description: "",
};

export function diagramVersionLabel(n: number): string {
  // 0 means "no version yet" — show as "—"
  return n > 0 ? String(n) : "—";
}

export const formLabelStyle = {
  display: "flex",
  flexDirection: "column" as const,
  gap: "var(--space-1)",
  fontWeight: 500,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

export const formInputStyle = {
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
  boxSizing: "border-box" as const,
};

export const formPrimaryButtonStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  fontFamily: "inherit",
};

export const formCancelButtonStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
};

/**
 * Framing for the read-only diagram previews in the overview's detail pane
 * (Phase 6 / decision E2-D4). Shared by the client-rendered Mermaid preview
 * and the server-rendered canvas SVG preview so both read as the same kind of
 * surface — a rendered artifact, not an editable field.
 */
export const previewBoxStyle: React.CSSProperties = {
  padding: "var(--space-4)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface-raised)",
  overflow: "auto",
  maxHeight: "520px",
  minHeight: "160px",
};

export const formDangerButtonStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  background: "transparent",
  color: "var(--color-danger, #ef4444)",
  border: "1px solid var(--color-danger, #ef4444)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
};

/**
 * GH-353 Task 9: Error message styling for read-only preview errors
 * (e.g., invalid JSON in node_graph payload).
 */
export const previewErrorStyle: React.CSSProperties = {
  color: "var(--color-danger)",
  margin: 0,
};

/**
 * GH-353 Task 9: Empty content placeholder styling for read-only previews
 * (e.g., empty node_graph or mermaid source).
 */
export const previewEmptyStyle: React.CSSProperties = {
  color: "var(--color-text-muted)",
  margin: 0,
};
