/**
 * REQ-176 — StatusBar: bottom strip summarising the current workflow.
 */

import type { WorkflowGraph } from "../../api/workflows";
import { entityTypeLabel } from "./constants";
import styles from "./WorkflowEditor.module.css";

interface StatusBarProps {
  graph: WorkflowGraph | null;
}

export function StatusBar({ graph }: StatusBarProps): JSX.Element {
  const text = graph
    ? `${entityTypeLabel(graph.entityType)} Workflow · ${graph.states.length} states · ${graph.transitions.length} transitions · Read-only`
    : "Workflow Editor · Select an entity type";

  return (
    <div className={styles.statusBar} role="status" data-testid="workflow-status-bar">
      {text}
    </div>
  );
}
