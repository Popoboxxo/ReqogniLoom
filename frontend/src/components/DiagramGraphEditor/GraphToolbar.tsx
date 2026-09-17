/**
 * GH-353 Task 8 — GraphToolbar: floating add-node / auto-layout / zoom / fit / grid controls.
 *
 * Modelled on `WorkflowEditor/CanvasToolbar.tsx`. Rendered inside the
 * `ReactFlowProvider` so it can drive the viewport through `useReactFlow`.
 *
 * "Auto layout" is an EXPLICIT action here (see graph-layout.ts) — unlike the
 * WorkflowEditor reference, positions are never recomputed automatically.
 */

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useReactFlow } from "@xyflow/react";
import { Grid3x3, LayoutGrid, Maximize2, Plus, ZoomIn, ZoomOut } from "lucide-react";
import styles from "./DiagramGraphEditor.module.css";

interface GraphToolbarProps {
  gridVisible: boolean;
  onToggleGrid: () => void;
  editMode: boolean;
  onAddNode: () => void;
  onAutoLayout: () => void;
  disabled: boolean;
}

export function GraphToolbar({
  gridVisible,
  onToggleGrid,
  editMode,
  onAddNode,
  onAutoLayout,
  disabled,
}: GraphToolbarProps): JSX.Element {
  const { t } = useTranslation();
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  const handleFit = useCallback(() => {
    void fitView({ padding: 0.2, duration: 300 });
  }, [fitView]);

  return (
    <div className={styles.toolbar} role="toolbar" aria-label={t("diagramGraph.toolbar.ariaLabel")}>
      {editMode && (
        <>
          <button
            type="button"
            className={styles.toolbarButton}
            onClick={onAddNode}
            aria-label={t("diagramGraph.toolbar.addNode")}
            title={t("diagramGraph.toolbar.addNode")}
            data-testid="graph-toolbar-add-node"
          >
            <Plus size={16} />
          </button>
          <button
            type="button"
            className={styles.toolbarButton}
            onClick={onAutoLayout}
            disabled={disabled}
            aria-label={t("diagramGraph.toolbar.autoLayout")}
            title={t("diagramGraph.toolbar.autoLayoutTitle")}
            data-testid="graph-toolbar-auto-layout"
          >
            <LayoutGrid size={16} />
          </button>
          <span className={styles.toolbarDivider} aria-hidden="true" />
        </>
      )}

      <button
        type="button"
        className={styles.toolbarButton}
        onClick={() => zoomIn({ duration: 200 })}
        aria-label={t("diagramGraph.toolbar.zoomIn")}
        title={t("diagramGraph.toolbar.zoomIn")}
        data-testid="graph-zoom-in"
      >
        <ZoomIn size={16} />
      </button>
      <button
        type="button"
        className={styles.toolbarButton}
        onClick={() => zoomOut({ duration: 200 })}
        aria-label={t("diagramGraph.toolbar.zoomOut")}
        title={t("diagramGraph.toolbar.zoomOut")}
        data-testid="graph-zoom-out"
      >
        <ZoomOut size={16} />
      </button>
      <button
        type="button"
        className={styles.toolbarButton}
        onClick={handleFit}
        aria-label={t("diagramGraph.toolbar.fitToView")}
        title={t("diagramGraph.toolbar.fitToView")}
        data-testid="graph-fit-view"
      >
        <Maximize2 size={16} />
      </button>

      <span className={styles.toolbarDivider} aria-hidden="true" />

      <button
        type="button"
        className={`${styles.toolbarButton} ${gridVisible ? styles.toolbarButtonActive : ""}`}
        onClick={onToggleGrid}
        aria-label={t("diagramGraph.toolbar.toggleGrid")}
        aria-pressed={gridVisible}
        title={t("diagramGraph.toolbar.toggleGrid")}
        data-testid="graph-toggle-grid"
      >
        <Grid3x3 size={16} />
      </button>
    </div>
  );
}
