/**
 * REQ-176 — CanvasToolbar: floating zoom / fit / grid / mermaid controls.
 *
 * Rendered inside the ReactFlowProvider so it can drive the viewport through
 * ``useReactFlow`` (design brief §5). Grid visibility and mermaid export are
 * owned by the parent WorkflowCanvas.
 */

import { useCallback } from "react";
import { useReactFlow } from "@xyflow/react";
import {
  Code2,
  Grid3x3,
  HelpCircle,
  Maximize2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import styles from "./WorkflowEditor.module.css";

interface CanvasToolbarProps {
  gridVisible: boolean;
  onToggleGrid: () => void;
  onCopyMermaid: () => void;
  onToggleHelp: () => void;
  helpOpen: boolean;
  disabled: boolean;
}

export function CanvasToolbar({
  gridVisible,
  onToggleGrid,
  onCopyMermaid,
  onToggleHelp,
  helpOpen,
  disabled,
}: CanvasToolbarProps): JSX.Element {
  const { t } = useTranslation();
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  const handleFit = useCallback(() => {
    void fitView({ padding: 0.2, duration: 300 });
  }, [fitView]);

  return (
    <div
      className={styles.toolbar}
      role="toolbar"
      aria-label={t("workflow.toolbar.ariaLabel")}
    >
      <button
        type="button"
        className={styles.toolbarButton}
        onClick={() => zoomIn({ duration: 200 })}
        aria-label={t("workflow.toolbar.zoomIn")}
        title={t("workflow.toolbar.zoomIn")}
        data-testid="workflow-zoom-in"
      >
        <ZoomIn size={16} />
      </button>
      <button
        type="button"
        className={styles.toolbarButton}
        onClick={() => zoomOut({ duration: 200 })}
        aria-label={t("workflow.toolbar.zoomOut")}
        title={t("workflow.toolbar.zoomOut")}
        data-testid="workflow-zoom-out"
      >
        <ZoomOut size={16} />
      </button>
      <button
        type="button"
        className={styles.toolbarButton}
        onClick={handleFit}
        aria-label={t("workflow.toolbar.fitToView")}
        title={t("workflow.toolbar.fitToViewTitle")}
        data-testid="workflow-fit-view"
      >
        <Maximize2 size={16} />
      </button>

      <span className={styles.toolbarDivider} aria-hidden="true" />

      <button
        type="button"
        className={`${styles.toolbarButton} ${
          gridVisible ? styles.toolbarButtonActive : ""
        }`}
        onClick={onToggleGrid}
        aria-label={t("workflow.toolbar.toggleGrid")}
        aria-pressed={gridVisible}
        title={t("workflow.toolbar.toggleGrid")}
        data-testid="workflow-toggle-grid"
      >
        <Grid3x3 size={16} />
      </button>
      <button
        type="button"
        className={styles.toolbarButton}
        onClick={onCopyMermaid}
        aria-label={t("workflow.toolbar.copyMermaidDiagram")}
        title={t("workflow.header.copyAsMermaid")}
        disabled={disabled}
        data-testid="workflow-copy-mermaid-toolbar"
      >
        <Code2 size={16} />
      </button>

      <span className={styles.toolbarDivider} aria-hidden="true" />

      <button
        type="button"
        className={`${styles.toolbarButton} ${
          helpOpen ? styles.toolbarButtonActive : ""
        }`}
        onClick={onToggleHelp}
        aria-label={t("workflow.toolbar.keyboardShortcuts")}
        aria-pressed={helpOpen}
        aria-expanded={helpOpen}
        aria-controls="workflow-canvas-help-panel"
        title={t("workflow.toolbar.keyboardShortcuts")}
        data-testid="workflow-help"
      >
        <HelpCircle size={16} />
      </button>
    </div>
  );
}
