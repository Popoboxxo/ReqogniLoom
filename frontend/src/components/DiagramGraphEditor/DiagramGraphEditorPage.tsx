/**
 * GH-353 Task 8 — DiagramGraphEditorPage: node/edge diagram editor.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L2-DS-002 (payload_format=node_graph)
 *
 * Composes the header (visual/code toggle, save/back), the canvas +
 * inspector body, and owns the in-editor draft state. Modelled on
 * `WorkflowEditor/WorkflowEditorPage.tsx`, with one deliberate structural
 * divergence (see the Task 8 brief and graph-layout.ts's module doc):
 * positions round-trip through the SAVED PAYLOAD, not localStorage, and
 * auto-layout only runs when the user explicitly clicks the toolbar button —
 * never automatically on load, so a hand-arranged diagram is never silently
 * re-flowed just by opening it.
 *
 * The Code/Visual toggle reuses the pattern from
 * `DiagramView/DiagramDetailView.tsx`'s Mermaid source view (same
 * data-testid naming, same aria-pressed button-group shape): Code shows the
 * LIVE in-editor payload (via `flowToPayload` on the current draft), not a
 * stale server copy, and toggling back to Visual never discards edits since
 * both views read from the same draft state.
 */

import "@xyflow/react/dist/style.css";

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft } from "lucide-react";
import { GraphCanvas } from "./GraphCanvas";
import { GraphInspectorPanel } from "./GraphInspectorPanel";
import type { Selection } from "./constants";
import { layoutGraph } from "./graph-layout";
import type { GraphFlowEdge, GraphFlowNode } from "./graph-layout";
import {
  EMPTY_NODE_GRAPH_PAYLOAD,
  flowToPayload,
  payloadToFlowEdges,
  payloadToFlowNodes,
  useGraphPayload,
} from "./useGraphPayload";
import type { GraphEdge, GraphHandlePosition, GraphNode } from "../../types";
import styles from "./DiagramGraphEditor.module.css";

// Stable empty-array identities so `nodes`/`edges` below don't produce a new
// array reference on every render while `draft` is still null (which would
// otherwise defeat the `useMemo` deps that read them further down).
const EMPTY_FLOW_NODES: GraphFlowNode[] = [];
const EMPTY_FLOW_EDGES: GraphFlowEdge[] = [];

function newNodeId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `n-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * React Flow's `Connection.sourceHandle`/`targetHandle` are `string | null`
 * (GraphNode.tsx's own handle ids are always one of these four). Used to
 * validate a real handle before trusting it, so a `null` (or otherwise
 * unexpected) value falls through to the caller's default instead of being
 * written into the saved payload as-is.
 */
function isGraphHandlePosition(value: string | null | undefined): value is GraphHandlePosition {
  return value === "top" || value === "right" || value === "bottom" || value === "left";
}

export function DiagramGraphEditorPage(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: diagramId } = useParams<{ id: string }>();

  const { payload, diagramName, isLoading, error, save, isSaving, saveError, resetSaveError } =
    useGraphPayload(diagramId);

  const [draft, setDraft] = useState<{ nodes: GraphFlowNode[]; edges: GraphFlowEdge[] } | null>(null);
  const [loadedForId, setLoadedForId] = useState<string | undefined>(undefined);
  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [editMode, setEditMode] = useState(false);
  const [viewMode, setViewMode] = useState<"visual" | "code">("visual");
  const [toast, setToast] = useState<string | null>(null);

  // Seed the draft exactly once per loaded diagram — after that, all edits
  // live only in `draft` until Save. Re-seeding on every `payload` change
  // would silently discard in-progress edits whenever TanStack Query
  // refetches in the background.
  if (payload && loadedForId !== diagramId) {
    setDraft({ nodes: payloadToFlowNodes(payload), edges: payloadToFlowEdges(payload) });
    setLoadedForId(diagramId);
  }

  const nodes = draft?.nodes ?? EMPTY_FLOW_NODES;
  const edges = draft?.edges ?? EMPTY_FLOW_EDGES;

  const flashToast = useCallback((message: string): void => {
    setToast(message);
    window.setTimeout(() => setToast(null), 3000);
  }, []);

  // --- draft mutations (local only, until Save) ---------------------------

  const handleUpdateNode = useCallback((id: string, patch: Partial<GraphNode>): void => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: prev.nodes.map((n) =>
          n.id === id ? { ...n, data: { ...n.data, node: { ...n.data.node, ...patch } } } : n
        ),
      };
    });
  }, []);

  const handleUpdateEdge = useCallback((id: string, patch: Partial<GraphEdge>): void => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        edges: prev.edges.map((e) => {
          if (e.id !== id || !e.data) return e;
          const nextEdge = { ...e.data.edge, ...patch };
          return {
            ...e,
            sourceHandle: patch.source_handle ?? e.sourceHandle,
            targetHandle: patch.target_handle ?? e.targetHandle,
            data: { edge: nextEdge },
          };
        }),
      };
    });
  }, []);

  const handleRenameNode = useCallback(
    (id: string, newLabel: string): void => handleUpdateNode(id, { label: newLabel }),
    [handleUpdateNode]
  );

  const handleNodeDragStop = useCallback(
    (id: string, position: { x: number; y: number }): void => {
      setDraft((prev) => {
        if (!prev) return prev;
        return { ...prev, nodes: prev.nodes.map((n) => (n.id === id ? { ...n, position } : n)) };
      });
    },
    []
  );

  const handleAddNode = useCallback((): void => {
    const id = newNodeId();
    const newNode: GraphFlowNode = {
      id,
      type: "graphNode",
      position: { x: 80 + nodes.length * 24, y: 80 + nodes.length * 24 },
      data: {
        node: {
          id,
          type: "box",
          label: t("diagramGraph.canvas.newNodeLabel"),
          position: { x: 80 + nodes.length * 24, y: 80 + nodes.length * 24 },
        },
      },
    };
    setDraft((prev) => ({
      nodes: [...(prev?.nodes ?? []), newNode],
      edges: prev?.edges ?? [],
    }));
    setSelection({ kind: "node", id });
  }, [nodes.length, t]);

  const handleConnectNodes = useCallback(
    (
      source: string,
      target: string,
      sourceHandle: string | null,
      targetHandle: string | null
    ): void => {
      const id = newNodeId();
      // Thread the handle the user actually dragged from/to (React Flow's
      // Connection.sourceHandle/targetHandle) through to the created edge —
      // only fall back to the dagre-style bottom/top default when React Flow
      // reports no specific handle (e.g. a connection not started from a
      // named handle). Reviewer finding (Task 8, round 1): this previously
      // hardcoded bottom/top unconditionally, discarding e.g. a left/right
      // connection in this free-form editor (unlike WorkflowEditor's
      // rank-oriented state machine, where bottom/top is a reasonable
      // default for every edge).
      const resolvedSourceHandle: GraphHandlePosition = isGraphHandlePosition(sourceHandle)
        ? sourceHandle
        : "bottom";
      const resolvedTargetHandle: GraphHandlePosition = isGraphHandlePosition(targetHandle)
        ? targetHandle
        : "top";
      const newEdge: GraphFlowEdge = {
        id,
        source,
        target,
        type: "graphEdge",
        sourceHandle: resolvedSourceHandle,
        targetHandle: resolvedTargetHandle,
        data: {
          edge: {
            id,
            source,
            target,
            type: "flow",
            source_handle: resolvedSourceHandle,
            target_handle: resolvedTargetHandle,
          },
        },
      };
      setDraft((prev) => ({
        nodes: prev?.nodes ?? [],
        edges: [...(prev?.edges ?? []), newEdge],
      }));
      setSelection({ kind: "edge", id });
    },
    []
  );

  const handleDeleteNode = useCallback((id: string): void => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        nodes: prev.nodes
          .filter((n) => n.id !== id)
          // Clear dangling parent_id references left by a deleted group node,
          // matching the backend validator's "parent_id must reference an
          // existing group node" invariant.
          .map((n) =>
            n.data.node.parent_id === id
              ? { ...n, data: { ...n.data, node: { ...n.data.node, parent_id: null } } }
              : n
          ),
        edges: prev.edges.filter((e) => e.source !== id && e.target !== id),
      };
    });
    setSelection({ kind: "none" });
  }, []);

  const handleDeleteEdge = useCallback((id: string): void => {
    setDraft((prev) => (prev ? { ...prev, edges: prev.edges.filter((e) => e.id !== id) } : prev));
    setSelection({ kind: "none" });
  }, []);

  const handleDeleteSelection = useCallback((): void => {
    if (selection.kind === "node") handleDeleteNode(selection.id);
    else if (selection.kind === "edge") handleDeleteEdge(selection.id);
  }, [selection, handleDeleteNode, handleDeleteEdge]);

  // --- auto layout (explicit action, see graph-layout.ts) -----------------

  const handleAutoLayout = useCallback((): void => {
    setDraft((prev) => {
      if (!prev) return prev;
      const domainNodes = prev.nodes.map((n) => n.data.node);
      const domainEdges = prev.edges.map((e) => e.data?.edge).filter((e): e is GraphEdge => !!e);
      const laidOut = layoutGraph(domainNodes, domainEdges);
      return laidOut;
    });
  }, []);

  // --- save -----------------------------------------------------------------

  const currentPayload = useMemo(
    () => flowToPayload(nodes, edges, payload?.viewport),
    [nodes, edges, payload?.viewport]
  );

  const handleSave = useCallback(async (): Promise<void> => {
    try {
      await save(currentPayload);
      flashToast(t("diagramGraph.toast.saved"));
    } catch {
      // Error surfaced via saveError below.
    }
  }, [save, currentPayload, flashToast, t]);

  const toggleEditMode = useCallback((): void => {
    setEditMode((v) => {
      if (v) setSelection({ kind: "none" });
      return !v;
    });
  }, []);

  if (!diagramId) {
    return (
      <div className={styles.page} data-testid="graph-editor-missing-id">
        {t("diagramGraph.header.missingDiagramId")}
      </div>
    );
  }

  return (
    <div className={styles.page} data-testid="graph-editor-page">
      <header className={styles.header} data-testid="graph-editor-header">
        <button
          type="button"
          className={styles.iconButton}
          onClick={() => navigate(`/diagrams/${diagramId}`)}
          aria-label={t("diagramGraph.header.back")}
          data-testid="graph-editor-back"
        >
          <ArrowLeft size={16} />
        </button>
        <div className={styles.headerTitleGroup}>
          <span className={styles.headerDot} aria-hidden="true" />
          <h1 className={styles.headerTitle}>{diagramName || t("diagramGraph.header.titleDefault")}</h1>
        </div>

        <div className={styles.headerSpacer} />

        <div role="group" aria-label={t("diagramGraph.header.viewMode")} className={styles.viewModeGroup}>
          <button
            type="button"
            data-testid="graph-viewmode-visual-btn"
            aria-pressed={viewMode === "visual"}
            className={`${styles.iconButton} ${viewMode === "visual" ? styles.iconButtonPrimary : ""}`}
            onClick={() => setViewMode("visual")}
          >
            {t("diagramGraph.header.viewModeLabels.visual")}
          </button>
          <button
            type="button"
            data-testid="graph-viewmode-code-btn"
            aria-pressed={viewMode === "code"}
            className={`${styles.iconButton} ${viewMode === "code" ? styles.iconButtonPrimary : ""}`}
            onClick={() => setViewMode("code")}
          >
            {t("diagramGraph.header.viewModeLabels.code")}
          </button>
        </div>

        <button
          type="button"
          className={styles.toggleButton}
          role="switch"
          aria-checked={editMode}
          onClick={toggleEditMode}
          data-testid="graph-edit-toggle"
        >
          <span className={`${styles.toggleTrack} ${editMode ? styles.toggleTrackOn : ""}`}>
            <span className={`${styles.toggleThumb} ${editMode ? styles.toggleThumbOn : ""}`} />
          </span>
          <span className={editMode ? styles.toggleTextOn : ""}>
            {editMode ? t("diagramGraph.header.editing") : t("diagramGraph.header.readOnly")}
          </span>
        </button>

        <button
          type="button"
          className={`${styles.iconButton} ${styles.iconButtonPrimary}`}
          onClick={() => void handleSave()}
          disabled={isSaving || isLoading}
          data-testid="graph-editor-save"
        >
          {isSaving ? t("diagramGraph.header.saving") : t("diagramGraph.header.save")}
        </button>
      </header>

      <div className={styles.layout}>
        {viewMode === "visual" ? (
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            isLoading={isLoading}
            error={error}
            selection={selection}
            onSelect={setSelection}
            editMode={editMode}
            onConnectNodes={handleConnectNodes}
            onRenameNode={handleRenameNode}
            onNodeDragStop={handleNodeDragStop}
            onDeleteSelection={handleDeleteSelection}
            onAddNode={handleAddNode}
            onAutoLayout={handleAutoLayout}
          />
        ) : (
          <div className={styles.codeView} data-testid="graph-code-view">
            <pre className={styles.codeViewPre} data-testid="graph-code-view-content">
              {JSON.stringify(currentPayload ?? EMPTY_NODE_GRAPH_PAYLOAD, null, 2)}
            </pre>
          </div>
        )}

        {viewMode === "visual" && (
          <GraphInspectorPanel
            nodes={nodes}
            edges={edges}
            selection={selection}
            onSelect={setSelection}
            editMode={editMode}
            onUpdateNode={handleUpdateNode}
            onUpdateEdge={handleUpdateEdge}
            onDeleteNode={handleDeleteNode}
            onDeleteEdge={handleDeleteEdge}
          />
        )}
      </div>

      {toast && (
        <div className={styles.statusBar} role="status" data-testid="graph-editor-toast">
          {toast}
        </div>
      )}
      {saveError && (
        <div className={`${styles.toast} ${styles.toastError}`} role="alert" data-testid="graph-editor-error-toast">
          <AlertCircle size={16} className={styles.toastIcon} aria-hidden="true" />
          {saveError}
          <button
            type="button"
            className={styles.modalClose}
            onClick={resetSaveError}
            aria-label={t("diagramGraph.header.dismissError")}
            data-testid="graph-editor-error-dismiss"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
