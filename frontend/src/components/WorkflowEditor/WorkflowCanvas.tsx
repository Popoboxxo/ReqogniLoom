/**
 * REQ-176 — WorkflowCanvas: the React Flow viewport (read-only, Phase 1).
 *
 * Wraps ReactFlowProvider, applies the dagre auto-layout, renders the custom
 * StateNode / TransitionEdge, and manages selection + grid + empty/loading/
 * error overlays (design brief §5). Selection is lifted to the parent so the
 * InspectorPanel and StatusBar stay in sync.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type EdgeMouseHandler,
  type EdgeTypes,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
} from "@xyflow/react";
import { AlertCircle, Workflow } from "lucide-react";
import type { WorkflowGraph } from "../../api/workflows";
import { layoutWorkflow } from "./layout";
import type { StateFlowNode, TransitionFlowEdge } from "./layout";
import { StateNode } from "./StateNode";
import { TransitionEdge } from "./TransitionEdge";
import { CanvasToolbar } from "./CanvasToolbar";
import type { Selection } from "./constants";
import styles from "./WorkflowEditor.module.css";

// Defined once at module scope — React Flow warns on unstable type maps.
const NODE_TYPES: NodeTypes = { stateNode: StateNode };
const EDGE_TYPES: EdgeTypes = { transition: TransitionEdge };

interface WorkflowCanvasProps {
  graph: WorkflowGraph | null;
  isLoading: boolean;
  error: Error | null;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  onCopyMermaid: () => void;
}

interface CanvasInnerProps extends WorkflowCanvasProps {
  graph: WorkflowGraph;
}

function CanvasInner({
  graph,
  selection,
  onSelect,
  onCopyMermaid,
}: CanvasInnerProps): JSX.Element {
  const { fitView } = useReactFlow();
  const [gridVisible, setGridVisible] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);

  // Positioned base graph — recomputed only when the state machine changes.
  const base = useMemo(
    () => layoutWorkflow(graph.states, graph.transitions),
    [graph.states, graph.transitions]
  );

  // Apply the current selection as React Flow's ``selected`` flag.
  const nodes: StateFlowNode[] = useMemo(
    () =>
      base.nodes.map((n) => ({
        ...n,
        selected: selection.kind === "state" && selection.id === n.id,
      })),
    [base.nodes, selection]
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

  // Keyboard shortcuts scoped to this page (design brief §9). Registered on the
  // window so the container div stays a non-interactive element (a11y).
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        onSelect({ kind: "none" });
        setHelpOpen(false);
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
  }, [fitView, onSelect]);

  const isEmpty = graph.states.length === 0;

  return (
    <div className={styles.canvasWrap} data-testid="workflow-canvas">
      <ReactFlow
        className={styles.flow}
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
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

      {helpOpen && (
        <div className={`${styles.overlay} ${styles.overlayInteractive}`} role="dialog" aria-label="Keyboard shortcuts">
          <div className={styles.overlayTitle}>Keyboard shortcuts</div>
          <div className={styles.overlayText}>
            Tab — move focus · Enter/Space — select · Esc — deselect ·
            Ctrl/Cmd+Shift+F — fit to view · scroll — zoom · drag — pan
          </div>
        </div>
      )}

      {isEmpty && (
        <div className={styles.overlay} role="status">
          <Workflow size={48} className={styles.overlayIcon} aria-hidden="true" />
          <div className={styles.overlayTitle}>No workflow defined</div>
          <div className={styles.overlayText}>
            This entity type has no workflow states configured for the active
            preset.
          </div>
        </div>
      )}
    </div>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps): JSX.Element {
  const { graph, isLoading, error } = props;

  if (isLoading) {
    return (
      <div className={styles.canvasWrap} data-testid="workflow-canvas-loading">
        <div className={styles.overlay} role="status">
          <div className={styles.spinner} aria-hidden="true" />
          <div className={styles.overlayText}>Loading workflow…</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.canvasWrap} data-testid="workflow-canvas-error">
        <div className={styles.overlay} role="alert">
          <AlertCircle size={40} className={styles.overlayIcon} aria-hidden="true" />
          <div className={styles.overlayTitle}>Could not load workflow</div>
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
          <div className={styles.overlayText}>Select an entity type.</div>
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
