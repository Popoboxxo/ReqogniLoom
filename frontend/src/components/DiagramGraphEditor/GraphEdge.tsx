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
// concept). SVG `stroke` cannot resolve CSS custom properties reliably across
// the whole matrix of themes here, so the hex values mirror the tokens.
const STROKE_BY_TYPE: Record<GraphEdgeType, string> = {
  flow: "#6366f1", // --color-primary (indigo 500)
  association: "#475569", // --color-border-hover (slate 600)
  dependency: "#f59e0b", // --color-warning (amber 500)
  containment: "#64748b", // --color-text-muted (slate 500)
};
const STROKE_ACTIVE = "#6366f1";

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
