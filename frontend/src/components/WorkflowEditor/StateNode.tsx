/**
 * REQ-176 — StateNode: custom React Flow node for a workflow state.
 *
 * Glassmorphism card with a type-colored left accent, a type dot, the state
 * name (uppercase), and the outgoing-transition count (design brief §6). Handles
 * are present on all four sides for edge anchoring but are transparent in the
 * read-only Phase 1.
 */

import { memo } from "react";
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
  const { state } = data;
  const typeClass = TYPE_CLASS[state.type];

  return (
    <div
      className={`${styles.stateNode} ${typeClass} ${
        selected ? styles.stateNodeSelected : ""
      }`}
      role="button"
      tabIndex={0}
      aria-label={`State: ${state.name}, type ${state.type}, ${state.outgoingCount} outgoing transitions`}
      data-testid={`workflow-state-node-${state.id}`}
    >
      {/* Anchoring handles — transparent in read-only mode */}
      <Handle
        type="target"
        position={Position.Top}
        id="top"
        className={styles.handle}
        isConnectable={false}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className={styles.handle}
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        className={styles.handle}
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className={styles.handle}
        isConnectable={false}
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
        <span className={styles.stateName}>{state.name}</span>
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
