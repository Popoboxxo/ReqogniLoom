/**
 * GH-353 Task 8 — GraphEdge: custom React Flow edge for a node_graph diagram.
 *
 * Modelled on `WorkflowEditor/TransitionEdge.tsx`: bezier path with an arrow
 * marker, a floating label pill via `EdgeLabelRenderer`, and a wide
 * transparent hover path so the thin stroke stays easy to click. Edge `type`
 * (flow/association/dependency/containment) drives the accent color and
 * `style.line` (solid/dashed, defaulting per type) drives the dash pattern.
 */

import { useState, type CSSProperties } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import type { GraphFlowEdge } from "./graph-layout";
import type { GraphEdgeType } from "../../types";
import styles from "./DiagramGraphEditor.module.css";

// Canonical edge-type colors (mirrors the accent tokens used elsewhere in the
// concept). Theming phase 2, checkpoint 2: migrated onto the new,
// theme-independent --color-diagram-edge-* tokens in tokens.css (see that
// file's comment — a prior version of this comment claimed SVG `stroke`
// couldn't resolve CSS custom properties reliably; that wasn't borne out on
// investigation, but the new tokens are frozen at the same value in both
// themes regardless, so the rendered color is unchanged either way).
// "containment" (#64748b) has no --palette-* primitive close enough without
// colliding with "association"'s slate-600 and was left as raw hex.
const STROKE_BY_TYPE: Record<GraphEdgeType, string> = {
  flow: "var(--color-diagram-edge-primary)", // indigo 500
  association: "var(--color-diagram-edge-default)", // slate 600
  dependency: "var(--color-diagram-edge-dependency)", // amber 500
  containment: "#64748b", // no adequately close token — see tokens.css comment
};
const STROKE_ACTIVE = "var(--color-diagram-edge-primary)";

// Edge types whose default line style is dashed when `style.line` is absent.
const DEFAULT_DASHED_TYPES = new Set<GraphEdgeType>(["dependency", "containment"]);

export function GraphEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
  selected,
}: EdgeProps<GraphFlowEdge>): JSX.Element {
  const [hovered, setHovered] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const active = selected || hovered;
  const edge = data?.edge;
  const edgeType: GraphEdgeType = edge?.type ?? "flow";
  const isDashed = edge?.style?.line
    ? edge.style.line === "dashed"
    : DEFAULT_DASHED_TYPES.has(edgeType);

  // Hoisted per-render style objects — the ui-ratchet gate forbids inline JSX
  // style object literals in .tsx files, so any value that must vary
  // per-instance (stroke color, dash pattern, the label-pill transform) is
  // built once here as a named `CSSProperties` const instead.
  const pathStyle: CSSProperties = {
    stroke: active ? STROKE_ACTIVE : STROKE_BY_TYPE[edgeType],
    strokeWidth: selected ? 3 : hovered ? 2.5 : 1.5,
    strokeDasharray: isDashed ? "6 4" : undefined,
  };
  const labelTransform: CSSProperties = {
    transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
  };

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={pathStyle} />
      {/* Wide transparent path to make the thin edge easy to hover/click. */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        className={styles.edgeHoverPath}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {edge && (
        <EdgeLabelRenderer>
          <div
            className={`${styles.edgeLabel} ${selected ? styles.edgeLabelSelected : ""}`}
            style={labelTransform}
            role="button"
            tabIndex={-1}
            data-testid={`graph-edge-${edge.id}`}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
          >
            <span className={styles.edgeLabelText}>{edge.label || edgeType}</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
