/**
 * REQ-176 — WorkflowEditorLayout: the flex-row body (selector · canvas · inspector).
 */

import type { ReactNode } from "react";
import styles from "./WorkflowEditor.module.css";

interface WorkflowEditorLayoutProps {
  selector: ReactNode;
  canvas: ReactNode;
  inspector: ReactNode;
}

export function WorkflowEditorLayout({
  selector,
  canvas,
  inspector,
}: WorkflowEditorLayoutProps): JSX.Element {
  return (
    <div className={styles.layout}>
      {selector}
      {canvas}
      {inspector}
    </div>
  );
}
