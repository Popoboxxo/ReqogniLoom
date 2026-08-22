/**
 * REQ-176/REQ-177 — StateNode: custom React Flow node for a workflow state.
 *
 * Glassmorphism card with a type-colored left accent, a type dot, the state
 * name (uppercase), and the outgoing-transition count (design brief §6). In
 * read-only mode the four anchoring handles are transparent; in edit mode
 * (REQ-177) they become visible/interactive for drag-to-connect and a
 * double-click swaps the name for an inline rename input.
 */

import { memo, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { ArrowRight, ChevronRight } from "lucide-react";
import type { StateFlowNode } from "./layout";
import type { WorkflowStateType } from "../../api/workflows";
import styles from "./WorkflowEditor.module.css";

const TYPE_CLASS: Record<WorkflowStateType, string> = {
  initial: styles.typeInitial,
  active: styles.typeActive,
  terminal: styles.typeTerminal,
  error: styles.typeError,
};

function StateNodeComponent({
  data,
  selected,
}: NodeProps<StateFlowNode>): JSX.Element {
  const { t } = useTranslation();
  const { state, editMode, onRename } = data;
  const typeClass = TYPE_CLASS[state.type];
  const handleClass = editMode ? styles.handleEdit : styles.handle;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(state.name);
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
    if (next && next !== state.name) onRename?.(state.name, next);
    else setDraft(state.name);
  };

  const cancel = (): void => {
    setDraft(state.name);
    setEditing(false);
  };

  return (
    <div
      className={`${styles.stateNode} ${typeClass} ${
        selected ? styles.stateNodeSelected : ""
      }`}
      role="button"
      tabIndex={0}
      aria-label={t("workflow.canvas.stateAriaLabel", {
        name: state.name,
        type: state.type,
        count: state.outgoingCount,
      })}
      data-testid={`workflow-state-node-${state.id}`}
      onDoubleClick={
        editMode
          ? (e) => {
              e.stopPropagation();
              setDraft(state.name);
              setEditing(true);
            }
          : undefined
      }
      // WCAG 2.1.1 — role="button" must be Enter/Space-operable. Mirrors
      // onDoubleClick above exactly: only active in edit mode, opens the
      // inline rename input.
      onKeyDown={
        editMode
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                e.stopPropagation();
                setDraft(state.name);
                setEditing(true);
              }
            }
          : undefined
      }
    >
      <Handle
        type="target"
        position={Position.Top}
        id="top"
        className={handleClass}
        isConnectable={!!editMode}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className={handleClass}
        isConnectable={!!editMode}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        className={handleClass}
        isConnectable={!!editMode}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className={handleClass}
        isConnectable={!!editMode}
      />

      <div className={styles.stateNodeHeader}>
        {state.isInitial ? (
          <ChevronRight
            size={12}
            className={styles.stateInitialIcon}
            aria-hidden="true"
          />
        ) : (
          <span className={styles.stateDot} aria-hidden="true" />
        )}
        {editing ? (
          <input
            ref={inputRef}
            className={styles.stateNameInput}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              else if (e.key === "Escape") cancel();
              e.stopPropagation();
            }}
            data-testid={`workflow-state-rename-${state.id}`}
          />
        ) : (
          <span className={styles.stateName}>{state.name}</span>
        )}
        <span className={styles.stateOutgoing} aria-hidden="true">
          <ArrowRight size={12} />
          {state.outgoingCount}
        </span>
      </div>
      <div className={styles.stateSubline}>
        <span>{state.type}</span>
      </div>
    </div>
  );
}

export const StateNode = memo(StateNodeComponent);
