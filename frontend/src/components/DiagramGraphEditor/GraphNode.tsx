/**
 * GH-353 Task 8 — GraphNode: custom React Flow node for a node_graph diagram.
 *
 * Modelled on `WorkflowEditor/StateNode.tsx`: four anchoring handles (top/left
 * = targets, bottom/right = sources), transparent/inert in read-only mode and
 * visible/interactive in edit mode, plus a double-click-to-rename inline
 * input. Shape (box/rounded/ellipse/diamond/note/group) and accent color
 * (style.accent) come straight from the node_graph schema (see
 * backend/diagram/node_graph.py NODE_TYPES / STYLE_ACCENTS).
 */

import { memo, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Link2 } from "lucide-react";
import type { GraphFlowNode } from "./graph-layout";
import type { GraphStyleAccent } from "../../types";
import styles from "./DiagramGraphEditor.module.css";

const SHAPE_CLASS: Record<string, string> = {
  box: styles.shapeBox,
  rounded: styles.shapeRounded,
  ellipse: styles.shapeEllipse,
  diamond: styles.shapeDiamond,
  note: styles.shapeNote,
  group: styles.shapeGroup,
};

const ACCENT_CLASS: Record<GraphStyleAccent, string> = {
  default: styles.accentDefault,
  primary: styles.accentPrimary,
  success: styles.accentSuccess,
  warning: styles.accentWarning,
  danger: styles.accentDanger,
  muted: styles.accentMuted,
};

function GraphNodeComponent({ data, selected }: NodeProps<GraphFlowNode>): JSX.Element {
  const { t } = useTranslation();
  const { node, editMode, onRename } = data;
  const shapeClass = SHAPE_CLASS[node.type] ?? styles.shapeBox;
  const accentClass = ACCENT_CLASS[node.style?.accent ?? "default"];
  const handleClass = editMode ? styles.handleEdit : styles.handle;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(node.label);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const commit = (): void => {
    const next = draft.trim();
    setEditing(false);
    if (next && next !== node.label) onRename?.(node.id, next);
    else setDraft(node.label);
  };

  const cancel = (): void => {
    setDraft(node.label);
    setEditing(false);
  };

  return (
    <div
      className={`${styles.graphNode} ${shapeClass} ${accentClass} ${
        selected ? styles.graphNodeSelected : ""
      }`}
      role="button"
      tabIndex={0}
      aria-label={t("diagramGraph.canvas.nodeAriaLabel", {
        label: node.label,
        type: node.type,
      })}
      data-testid={`graph-node-${node.id}`}
      onDoubleClick={
        editMode
          ? (e) => {
              e.stopPropagation();
              setDraft(node.label);
              setEditing(true);
            }
          : undefined
      }
    >
      <Handle type="target" position={Position.Top} id="top" className={handleClass} isConnectable={!!editMode} />
      <Handle type="target" position={Position.Left} id="left" className={handleClass} isConnectable={!!editMode} />
      <Handle type="source" position={Position.Bottom} id="bottom" className={handleClass} isConnectable={!!editMode} />
      <Handle type="source" position={Position.Right} id="right" className={handleClass} isConnectable={!!editMode} />

      <div className={styles.graphNodeHeader}>
        {editing ? (
          <input
            ref={inputRef}
            className={styles.graphNodeLabelInput}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              else if (e.key === "Escape") cancel();
              e.stopPropagation();
            }}
            data-testid={`graph-node-rename-${node.id}`}
          />
        ) : (
          <span className={styles.graphNodeLabel}>{node.label}</span>
        )}
        {node.artifact_ref && (
          <Link2
            size={12}
            className={styles.graphNodeLinkIcon}
            aria-label={t("diagramGraph.canvas.nodeLinkedAriaLabel", {
              entityType: node.artifact_ref.entity_type,
            })}
          />
        )}
      </div>
    </div>
  );
}

export const GraphNode = memo(GraphNodeComponent);
