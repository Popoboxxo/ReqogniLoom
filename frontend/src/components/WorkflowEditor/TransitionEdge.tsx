/**
 * REQ-176 — TransitionEdge: custom React Flow edge for a workflow transition.
 *
 * Bezier path with an arrow marker and a floating label pill (design brief §7).
 * The pill shows the target state, a lock icon when a change_reason is required,
 * and a ``[sig]`` gate badge when a signature gate guards the transition.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { Lock } from "lucide-react";
import type { TransitionFlowEdge } from "./layout";
import styles from "./WorkflowEditor.module.css";

// Canonical edge colors (design brief §11). Theming phase 2, checkpoint 2:
// migrated onto the new, theme-independent --color-diagram-edge-* tokens in
// tokens.css (see that file's comment — this used to be raw hex mirroring
// token definitions by hand, citing an SVG-stroke resolution concern that
// didn't hold up on investigation; the tokens are frozen at the same value
// in both themes regardless, so the rendered color is unchanged either way).
const STROKE_DEFAULT = "var(--color-diagram-edge-default)"; // slate 600
const STROKE_ACTIVE = "var(--color-diagram-edge-primary)"; // indigo 500

export function TransitionEdge({
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
}: EdgeProps<TransitionFlowEdge>): JSX.Element {
  const { t } = useTranslation();
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
  const transition = data?.transition;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: active ? STROKE_ACTIVE : STROKE_DEFAULT,
          strokeWidth: selected ? 3 : hovered ? 2.5 : 1.5,
        }}
      />
      {/* Wide transparent path to make the thin edge easy to hover/click. */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        style={{ cursor: "pointer" }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {transition && (
        <EdgeLabelRenderer>
          <div
            className={`${styles.edgeLabel} ${
              selected ? styles.edgeLabelSelected : ""
            }`}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            role="button"
            tabIndex={-1}
            aria-label={t("workflow.canvas.transitionAriaLabel", {
              name: transition.name,
              from: transition.from_state,
              to: transition.to_state,
            })}
            data-testid={`workflow-transition-edge-${transition.id}`}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            // WCAG 2.1.1 — this element has no onClick of its own; selecting
            // the transition happens via the native click bubbling up (through
            // the React tree, per EdgeLabelRenderer's portal semantics) to
            // React Flow's onEdgeClick. Enter/Space must reach the same path,
            // so we dispatch a real click rather than duplicate that wiring.
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                e.currentTarget.click();
              }
            }}
          >
            {transition.change_reason_required && (
              <Lock size={10} className={styles.edgeLockIcon} aria-hidden="true" />
            )}
            <span className={styles.edgeLabelText}>{transition.to_state}</span>
            {transition.signature_gate && (
              <span className={styles.edgeGateBadge} aria-hidden="true">
                [sig]
              </span>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
