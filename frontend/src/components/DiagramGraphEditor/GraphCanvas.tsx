/**
 * GH-353 Task 8 — GraphCanvas: the React Flow viewport for the node_graph editor.
 *
 * Modelled on `WorkflowEditor/WorkflowCanvas.tsx`: drag-from-handle to create
 * an edge (onConnect), node drag to reposition, Delete/Backspace to remove the
 * selection. Positions live in the page's in-editor draft state (passed down
 * as `nodes`/`edges` props) and round-trip through the SAVED PAYLOAD on Save —
 * there is no client-side position persistence layer here (see graph-layout.ts
 * for the rationale).
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
  type OnConnect,
} from "@xyflow/react";
import { Waypoints } from "lucide-react";
import { GraphNode } from "./GraphNode";
import { GraphEdge } from "./GraphEdge";
import { GraphToolbar } from "./GraphToolbar";
import type { GraphFlowEdge, GraphFlowNode } from "./graph-layout";
import type { Selection } from "./constants";
import styles from "./DiagramGraphEditor.module.css";

// Defined once at module scope — React Flow warns on unstable type maps.
const NODE_TYPES: NodeTypes = { graphNode: GraphNode };
const EDGE_TYPES: EdgeTypes = { graphEdge: GraphEdge };

interface GraphCanvasProps {
  nodes: GraphFlowNode[];
  edges: GraphFlowEdge[];
  isLoading: boolean;
  error: Error | null;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  editMode: boolean;
  onConnectNodes: (source: string, target: string) => void;
  onRenameNode: (id: string, newLabel: string) => void;
  onNodeDragStop: (id: string, position: { x: number; y: number }) => void;
  onDeleteSelection: () => void;
  onAddNode: () => void;
  onAutoLayout: () => void;
}

function CanvasInner({
  nodes,
  edges,
  selection,
  onSelect,
  editMode,
  onConnectNodes,
  onRenameNode,
  onNodeDragStop,
  onDeleteSelection,
  onAddNode,
  onAutoLayout,
}: GraphCanvasProps): JSX.Element {
  const { t } = useTranslation();
  const { fitView } = useReactFlow();
  const [gridVisible, setGridVisible] = useState(true);

  // Apply selection + edit affordances to each node/edge (positions/domain
  // fields already live in the props — this is pure presentation wiring).
  const flowNodes: GraphFlowNode[] = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        draggable: editMode,
        selected: selection.kind === "node" && selection.id === n.id,
        data: { ...n.data, editMode, onRename: onRenameNode },
      })),
    [nodes, selection, editMode, onRenameNode]
  );

  const flowEdges: GraphFlowEdge[] = useMemo(
    () =>
      edges.map((e) => ({
        ...e,
        selected: selection.kind === "edge" && selection.id === e.id,
      })),
    [edges, selection]
  );

  const handleNodeClick = useCallback<NodeMouseHandler<Node>>(
    (_e, node) => onSelect({ kind: "node", id: node.id }),
    [onSelect]
  );

  const handleEdgeClick = useCallback<EdgeMouseHandler<Edge>>(
    (_e, edge) => onSelect({ kind: "edge", id: edge.id }),
    [onSelect]
  );

  const handlePaneClick = useCallback(() => {
    onSelect({ kind: "none" });
  }, [onSelect]);

  const handleConnect = useCallback<OnConnect>(
    (c: Connection) => {
      if (c.source && c.target) onConnectNodes(c.source, c.target);
    },
    [onConnectNodes]
  );

  const handleNodeDragStop = useCallback(
    (_e: MouseEvent | TouchEvent, node: GraphFlowNode) => {
      onNodeDragStop(node.id, { x: node.position.x, y: node.position.y });
    },
    [onNodeDragStop]
  );

  // Keyboard shortcuts scoped to this page.
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if (e.key === "Escape") {
        onSelect({ kind: "none" });
      } else if (
        editMode &&
        !typing &&
        (e.key === "Delete" || e.key === "Backspace") &&
        selection.kind !== "none"
      ) {
        e.preventDefault();
        onDeleteSelection();
      } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "F" || e.key === "f")) {
        e.preventDefault();
        void fitView({ padding: 0.2, duration: 300 });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fitView, onSelect, editMode, selection, onDeleteSelection]);

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const isEmpty = nodes.length === 0;

  return (
    <div className={styles.canvasWrap} data-testid="graph-canvas" ref={wrapRef}>
      <ReactFlow
        className={styles.flow}
        nodes={flowNodes}
        edges={flowEdges}
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
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        {gridVisible && (
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--color-border)" />
        )}
      </ReactFlow>

      <GraphToolbar
        gridVisible={gridVisible}
        onToggleGrid={() => setGridVisible((v) => !v)}
        editMode={editMode}
        onAddNode={onAddNode}
        onAutoLayout={onAutoLayout}
        disabled={false}
      />

      {isEmpty && (
        <div className={styles.overlay} role="status">
          <Waypoints size={40} className={styles.overlayIcon} aria-hidden="true" />
          <div className={styles.overlayTitle}>{t("diagramGraph.canvas.emptyTitle")}</div>
          <div className={styles.overlayText}>
            {editMode ? t("diagramGraph.canvas.emptyHintEdit") : t("diagramGraph.canvas.emptyHintReadOnly")}
          </div>
        </div>
      )}
    </div>
  );
}

export function GraphCanvas(props: GraphCanvasProps): JSX.Element {
  const { t } = useTranslation();
  const { isLoading, error } = props;

  if (isLoading) {
    return (
      <div className={styles.canvasWrap} data-testid="graph-canvas-loading">
        <div className={styles.overlay} role="status">
          <div className={styles.spinner} aria-hidden="true" />
          <div className={styles.overlayText}>{t("diagramGraph.canvas.loading")}</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.canvasWrap} data-testid="graph-canvas-error">
        <div className={styles.overlay} role="alert">
          <div className={styles.overlayTitle}>{t("diagramGraph.canvas.loadErrorTitle")}</div>
          <div className={styles.overlayText}>{error.message}</div>
        </div>
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
