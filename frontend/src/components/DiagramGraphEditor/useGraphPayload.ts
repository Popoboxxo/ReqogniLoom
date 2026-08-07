/**
 * GH-353 Task 8 — DiagramGraphEditor data + (de)serialization hook.
 *
 * Modelled on `WorkflowEditor/useWorkflowData.ts` + `useWorkflowMutations.ts`,
 * but adapted to the node_graph editor's different persistence model:
 * `content` on `DiagramDetail` is a JSON-ENCODED STRING (see
 * backend/rest_api/serializers_diagram.py `NodeGraphPayloadSerializer`
 * docstring — "content is transported as a JSON-encoded string, not a nested
 * object, on the actual REST endpoint"), so this hook owns the
 * parse/stringify boundary in addition to the query/mutation wiring.
 *
 * The `payloadToFlowNodes` / `payloadToFlowEdges` / `flowToPayload` functions
 * are the canonical (de)serialization matching Task 1's exact schema
 * (backend/diagram/node_graph.py) — every other file that needs to convert
 * between the domain `NodeGraphPayload` and React Flow's node/edge arrays
 * goes through these, so the schema mapping has exactly one place to drift.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Position } from "@xyflow/react";
import { diagramsApi } from "../../api/diagrams";
import { diagramKeys } from "../DiagramView/useDiagramData";
import { asError } from "../../queries/query-error";
import type { GraphEdge, GraphHandlePosition, GraphViewport, NodeGraphPayload } from "../../types";
import type { GraphFlowEdge, GraphFlowNode } from "./graph-layout";
import { DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT } from "./graph-layout";

export const NODE_GRAPH_SCHEMA_VERSION = 1 as const;

export const EMPTY_NODE_GRAPH_PAYLOAD: NodeGraphPayload = {
  schema_version: NODE_GRAPH_SCHEMA_VERSION,
  nodes: [],
  edges: [],
};

function apiErrorMessage(err: unknown): string {
  return (err as { error?: { message?: string } })?.error?.message ?? String(err);
}

/**
 * Parse the persisted `content` string into a `NodeGraphPayload`, throwing on
 * malformed JSON *or* a shape that isn't a valid NodeGraphPayload (missing
 * `nodes`/`edges` arrays). This is the single source of truth for "is this
 * string a valid node_graph payload" — both `parseNodeGraphContent` (tolerant
 * fallback, below) and callers that want to surface a parse error to the user
 * (e.g. DiagramDetailView's read-only preview, GH-353 final review I4) build
 * on this one validation instead of each re-implementing a slightly different
 * (and, per the final review, weaker) check.
 */
export function parseNodeGraphContentStrict(content: string | null | undefined): NodeGraphPayload {
  if (!content) return EMPTY_NODE_GRAPH_PAYLOAD;
  const parsed = JSON.parse(content) as unknown;
  if (
    parsed &&
    typeof parsed === "object" &&
    Array.isArray((parsed as NodeGraphPayload).nodes) &&
    Array.isArray((parsed as NodeGraphPayload).edges)
  ) {
    return parsed as NodeGraphPayload;
  }
  throw new Error(
    "node_graph content is not a valid NodeGraphPayload (missing 'nodes'/'edges' arrays)."
  );
}

/** Parse the persisted `content` string into a `NodeGraphPayload`, tolerating malformed/missing content. */
export function parseNodeGraphContent(content: string | null | undefined): NodeGraphPayload {
  try {
    return parseNodeGraphContentStrict(content);
  } catch {
    return EMPTY_NODE_GRAPH_PAYLOAD;
  }
}

/**
 * Convert the persisted `nodes[]` into positioned React Flow nodes. Positions
 * come straight from `node.position` — NOT recomputed via dagre (see
 * graph-layout.ts's module doc for why auto-layout must stay an explicit
 * toolbar action rather than something this loader runs implicitly).
 */
export function payloadToFlowNodes(payload: NodeGraphPayload): GraphFlowNode[] {
  return payload.nodes.map((node) => ({
    id: node.id,
    type: "graphNode",
    position: { x: node.position.x, y: node.position.y },
    width: node.size?.width ?? DEFAULT_NODE_WIDTH,
    height: node.size?.height ?? DEFAULT_NODE_HEIGHT,
    data: { node },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  }));
}

/** Convert the persisted `edges[]` into React Flow edges, using each edge's own stored handle ids. */
export function payloadToFlowEdges(payload: NodeGraphPayload): GraphFlowEdge[] {
  return payload.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "graphEdge",
    sourceHandle: edge.source_handle ?? "bottom",
    targetHandle: edge.target_handle ?? "top",
    data: { edge },
  }));
}

/**
 * Convert the current React Flow node/edge draft back into a saveable
 * `NodeGraphPayload`. Every domain field (label/type/style/artifact_ref/
 * parent_id for nodes; label/type/style for edges) is read from `data.node`/
 * `data.edge` — only `position` (from the live node) and the handle ids
 * (from the live edge, which the user may have re-dragged onto a different
 * handle) are taken from the React Flow objects themselves.
 */
export function flowToPayload(
  nodes: GraphFlowNode[],
  edges: GraphFlowEdge[],
  viewport?: GraphViewport
): NodeGraphPayload {
  const payload: NodeGraphPayload = {
    schema_version: NODE_GRAPH_SCHEMA_VERSION,
    nodes: nodes.map((n) => ({
      ...n.data.node,
      position: { x: n.position.x, y: n.position.y },
    })),
    edges: edges.map((e): GraphEdge => {
      const base = e.data?.edge;
      if (!base) {
        throw new Error(`graph edge ${e.id} is missing its domain data`);
      }
      return {
        ...base,
        source: e.source,
        target: e.target,
        source_handle: (e.sourceHandle as GraphHandlePosition | null | undefined) ?? undefined,
        target_handle: (e.targetHandle as GraphHandlePosition | null | undefined) ?? undefined,
      };
    }),
  };
  if (viewport) payload.viewport = viewport;
  return payload;
}

export interface UseGraphPayloadResult {
  /** `null` while the underlying diagram detail is still loading. */
  payload: NodeGraphPayload | null;
  diagramName: string;
  isLoading: boolean;
  error: Error | null;
  save: (payload: NodeGraphPayload) => Promise<void>;
  isSaving: boolean;
  saveError: string | null;
  resetSaveError: () => void;
}

/** Loads the diagram detail and exposes a save mutation for `payload_format=node_graph`. */
export function useGraphPayload(diagramId: string | undefined): UseGraphPayloadResult {
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: diagramKeys.detail(diagramId ?? ""),
    queryFn: () => diagramsApi.get(diagramId as string),
    enabled: !!diagramId,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: NodeGraphPayload) => {
      if (!diagramId) return Promise.reject(new Error("no diagram id"));
      return diagramsApi.update(diagramId, {
        payload_format: "node_graph",
        content: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      if (diagramId) {
        void queryClient.invalidateQueries({ queryKey: diagramKeys.detail(diagramId) });
      }
    },
  });

  return {
    payload: detailQuery.data ? parseNodeGraphContent(detailQuery.data.content) : null,
    diagramName: detailQuery.data?.name ?? "",
    isLoading: !!diagramId && detailQuery.isLoading,
    error: detailQuery.error ? asError(detailQuery.error) : null,
    save: async (payload) => {
      await saveMutation.mutateAsync(payload);
    },
    isSaving: saveMutation.isPending,
    saveError: saveMutation.error ? apiErrorMessage(saveMutation.error) : null,
    resetSaveError: () => saveMutation.reset(),
  };
}
