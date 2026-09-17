/**
 * REQ-176 — StatusBar: bottom strip summarising the current workflow.
 */

import { useTranslation } from "react-i18next";
import type { WorkflowGraph } from "../../api/workflows";
import styles from "./WorkflowEditor.module.css";

interface StatusBarProps {
  graph: WorkflowGraph | null;
}

export function StatusBar({ graph }: StatusBarProps): JSX.Element {
  const { t } = useTranslation();
  const text = graph
    ? t("workflow.statusBar.summary", {
        entityType: t(`workflow.entityTypes.${graph.entityType}`),
        stateCount: graph.states.length,
        transitionCount: graph.transitions.length,
      })
    : t("workflow.statusBar.emptyPrompt");

  return (
    <div className={styles.statusBar} role="status" data-testid="workflow-status-bar">
      {text}
    </div>
  );
}
