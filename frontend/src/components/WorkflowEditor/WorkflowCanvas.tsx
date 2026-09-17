/**
 * REQ-176/REQ-177 — WorkflowCanvas: the React Flow viewport.
 *
 * Phase 1 rendered the graph read-only. Phase 2 (REQ-177) adds edit-mode
 * interactions when ``editMode`` is on: drag-from-handle to create a transition
 * (onConnect → Add Transition dialog), double-click a node to rename inline,
 * double-click empty canvas to add a state at the cursor, Delete/Backspace to
 * remove the selection (with confirmation, handled by the page), and node drag
 * with client-side position persistence. Read-only rendering is untouched when
 * ``editMode`` is false.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeMouseHandler,
  type EdgeTypes,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import { AlertCircle, Pencil, Workflow } from "lucide-react";
import type { WorkflowEntityType, WorkflowGraph } from "../../api/workflows";
import { layoutWorkflow } from "./layout";
import type { StateFlowNode, TransitionFlowEdge } from "./layout";
import { StateNode } from "./StateNode";
import { TransitionEdge } from "./TransitionEdge";
import { CanvasToolbar } from "./CanvasToolbar";
import { loadPositions, savePositions, type PositionMap } from "./layout-store";
import type { Selection } from "./constants";
import styles from "./WorkflowEditor.module.css";

// Defined once at module scope — React Flow warns on unstable type maps.
const NODE_TYPES: NodeTypes = { stateNode: StateNode };
const EDGE_TYPES: EdgeTypes = { transition: TransitionEdge };

interface WorkflowCanvasProps {
  graph: WorkflowGraph | null;
  entityType: WorkflowEntityType;
  workspaceId: string | undefined;
  isLoading: boolean;
  error: Error | null;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  onCopyMermaid: () => void;
  editMode: boolean;
  onConnectStates: (fromState: string, toState: string) => void;
  onRenameState: (oldName: string, newName: string) => void;
  onDeleteSelection: () => void;
  onAddStateRequest: () => void;
  onInitialize: () => void;
  initializing: boolean;
}

interface CanvasInnerProps extends WorkflowCanvasProps {
  graph: WorkflowGraph;
}

function CanvasInner({
  graph,
  entityType,
  workspaceId,
  selection,
  onSelect,
  onCopyMermaid,
  editMode,
  onConnectStates,
  onRenameState,
  onDeleteSelection,
  onAddStateRequest,
}: CanvasInnerProps): JSX.Element {
  const { t } = useTranslation();
  const { fitView } = useReactFlow();
  const [gridVisible, setGridVisible] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const helpPanelRef = useRef<HTMLDivElement | null>(null);
  const helpTriggerRef = useRef<HTMLElement | null>(null);

  // WCAG 4.1.2 — move focus into the (non-modal) help panel when it opens and
  // restore it to the toggle button on close, so keyboard/screen-reader users
  // reach the disclosed content and Escape returns them where they started.
  useEffect(() => {
    if (helpOpen) {
      helpTriggerRef.current = document.activeElement as HTMLElement | null;
      helpPanelRef.current?.focus();
    } else {
      helpTriggerRef.current?.focus?.();
    }
  }, [helpOpen]);

  // Persisted, hand-arranged node positions (client-side; see layout-store).
  const [positions, setPositions] = useState<PositionMap>(() =>
    workspaceId ? loadPositions(workspaceId, entityType) : {}
  );
  useEffect(() => {
    setPositions(workspaceId ? loadPositions(workspaceId, entityType) : {});
  }, [workspaceId, entityType]);

  // Positioned base graph — recomputed only when the state machine changes.
  const base = useMemo(
    () => layoutWorkflow(graph.states, graph.transitions),
    [graph.states, graph.transitions]
  );

  // Apply selection + edit affordances + stored positions to each node.
  const nodes: StateFlowNode[] = useMemo(
    () =>
      base.nodes.map((n) => ({
        ...n,
        position: positions[n.id] ?? n.position,
        draggable: editMode,
        selected: selection.kind === "state" && selection.id === n.id,
        data: { ...n.data, editMode, onRename: onRenameState },
      })),
    [base.nodes, selection, positions, editMode, onRenameState]
  );

  const edges: TransitionFlowEdge[] = useMemo(
    () =>
      base.edges.map((e) => ({
        ...e,
        selected: selection.kind === "transition" && selection.id === e.id,
      })),
    [base.edges, selection]
  );

  // Re-fit whenever the machine (node set) changes.
  useEffect(() => {
    const id = window.setTimeout(
      () => void fitView({ padding: 0.2, duration: 300 }),
      50
    );
    return () => window.clearTimeout(id);
  }, [base.nodes, fitView]);

  const handleNodeClick = useCallback<NodeMouseHandler<Node>>(
    (_e, node) => onSelect({ kind: "state", id: node.id }),
    [onSelect]
  );

  const handleEdgeClick = useCallback<EdgeMouseHandler<Edge>>(
    (_e, edge) => onSelect({ kind: "transition", id: edge.id }),
    [onSelect]
  );

  const handlePaneClick = useCallback(() => {
    onSelect({ kind: "none" });
    setHelpOpen(false);
  }, [onSelect]);

  const handleConnect = useCallback(
    (c: Connection) => {
      if (c.source && c.target) onConnectStates(c.source, c.target);
    },
    [onConnectStates]
  );

  const handleNodeDragStop = useCallback(
    (_e: MouseEvent | TouchEvent, node: StateFlowNode) => {
      if (!workspaceId) return;
      setPositions((prev) => {
        const next = { ...prev, [node.id]: { x: node.position.x, y: node.position.y } };
        savePositions(workspaceId, entityType, next);
        return next;
      });
    },
    [workspaceId, entityType]
  );

  // Double-click on the empty pane → add state. Attached as a native listener
  // (not a JSX handler on the wrapper) so the container stays non-interactive.
  const wrapRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    function onDblClick(e: MouseEvent): void {
      if (!editMode) return;
      const target = e.target as HTMLElement;
      // Only the empty pane triggers add-state; node double-clicks rename.
      if (target.classList.contains("react-flow__pane")) onAddStateRequest();
    }
    el.addEventListener("dblclick", onDblClick);
    return () => el.removeEventListener("dblclick", onDblClick);
  }, [editMode, onAddStateRequest]);

  // Keyboard shortcuts scoped to this page (design brief §9).
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if (e.key === "Escape") {
        onSelect({ kind: "none" });
        setHelpOpen(false);
      } else if (
        editMode &&
        !typing &&
        (e.key === "Delete" || e.key === "Backspace") &&
        selection.kind !== "none"
      ) {
        e.preventDefault();
        onDeleteSelection();
      } else if (
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        (e.key === "F" || e.key === "f")
      ) {
        e.preventDefault();
        void fitView({ padding: 0.2, duration: 300 });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fitView, onSelect, editMode, selection, onDeleteSelection]);

  const isEmpty = graph.states.length === 0;

  return (
    <div className={styles.canvasWrap} data-testid="workflow-canvas" ref={wrapRef}>
      <ReactFlow
        className={styles.flow}
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        onConnect={handleConnect}
        onNodeDragStop={handleNodeDragStop}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable={editMode}
        nodesConnectable={editMode}
        elementsSelectable
        deleteKeyCode={null}
        zoomOnDoubleClick={!editMode}
        proOptions={{ hideAttribution: true }}
      >
        {gridVisible && (
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="var(--color-border)"
          />
        )}
      </ReactFlow>

      <CanvasToolbar
        gridVisible={gridVisible}
        onToggleGrid={() => setGridVisible((v) => !v)}
        onCopyMermaid={onCopyMermaid}
        onToggleHelp={() => setHelpOpen((v) => !v)}
        helpOpen={helpOpen}
        disabled={isEmpty}
      />

      {editMode && !isEmpty && (
        <div className={styles.editHint} data-testid="workflow-edit-hint">
          <Pencil size={12} aria-hidden="true" />
          {t("workflow.canvas.editHint")}
        </div>
      )}

      {helpOpen && (
        <div
          id="workflow-canvas-help-panel"
          className={`${styles.overlay} ${styles.overlayInteractive}`}
          role="region"
          aria-label={t("workflow.canvas.helpTitle")}
          tabIndex={-1}
          ref={helpPanelRef}
        >
          <div className={styles.overlayTitle}>{t("workflow.canvas.helpTitle")}</div>
          <div className={styles.overlayText}>{t("workflow.canvas.helpText")}</div>
        </div>
      )}
    </div>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps): JSX.Element {
  const { t } = useTranslation();
  const { graph, isLoading, error, editMode, onInitialize, initializing } = props;

  if (isLoading) {
    return (
      <div className={styles.canvasWrap} data-testid="workflow-canvas-loading">
        <div className={styles.overlay} role="status">
          <div className={styles.spinner} aria-hidden="true" />
          <div className={styles.overlayText}>{t("workflow.canvas.loading")}</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.canvasWrap} data-testid="workflow-canvas-error">
        <div className={styles.overlay} role="alert">
          <AlertCircle size={40} className={styles.overlayIcon} aria-hidden="true" />
          <div className={styles.overlayTitle}>{t("workflow.canvas.loadErrorTitle")}</div>
          <div className={styles.overlayText}>{error.message}</div>
        </div>
      </div>
    );
  }

  if (!graph) {
    return (
      <div className={styles.canvasWrap} data-testid="workflow-canvas-empty">
        <div className={styles.overlay} role="status">
          <Workflow size={48} className={styles.overlayIcon} aria-hidden="true" />
          <div className={styles.overlayText}>{t("workflow.canvas.selectEntityType")}</div>
        </div>
      </div>
    );
  }

  // No workflow configured (or no states) — offer initialization in edit mode.
  if (graph.states.length === 0) {
    return (
      <div className={styles.canvasWrap} data-testid="workflow-canvas-noworkflow">
        <div
          className={`${styles.overlay} ${editMode ? styles.overlayInteractive : ""}`}
          role="status"
        >
          <Workflow size={48} className={styles.overlayIcon} aria-hidden="true" />
          <div className={styles.overlayTitle}>{t("workflow.canvas.noWorkflowTitle")}</div>
          <div className={styles.overlayText}>
            {t("workflow.canvas.noWorkflowText")}
          </div>
          {editMode && (
            <button
              type="button"
              className={styles.initializeButton}
              onClick={onInitialize}
              disabled={initializing}
              data-testid="workflow-initialize-button"
            >
              <Workflow size={16} aria-hidden="true" />
              {initializing
                ? t("workflow.canvas.initializing")
                : t("workflow.canvas.initializeWorkflow")}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <CanvasInner {...props} graph={graph} />
    </ReactFlowProvider>
  );
}
