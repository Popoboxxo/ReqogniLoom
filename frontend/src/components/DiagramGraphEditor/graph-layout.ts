/**
 * GH-353 Task 8 — Auto-layout for the node_graph diagram editor via @dagrejs/dagre.
 *
 * Modelled on `WorkflowEditor/layout.ts`: turns a `GraphNode[]`/`GraphEdge[]`
 * pair into positioned React Flow `Node[]`/`Edge[]` arrays, keeping the
 * dagre centre->top-left position correction and the self-loop skip.
 *
 * IMPORTANT divergence from the WorkflowEditor reference (see the Task 8
 * brief): this module is called ONLY from the explicit "Auto layout" toolbar
 * action (`GraphToolbar`), never automatically on load. Positions for a
 * loaded diagram come straight from the saved payload's `node.position`
 * fields (see `useGraphPayload.ts`'s `payloadToFlowNodes`) — there is no
 * `layout-store.ts` equivalent and no client-side localStorage layer here.
 * Re-flowing a hand-arranged diagram on every open would destroy the
 * arrangement two collaborators expect to see identically.
 */

import dagre from "@dagrejs/dagre";
import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import type { GraphEdge, GraphHandlePosition, GraphNode } from "../../types";

/** Data carried by a graph node. */
export interface GraphNodeData extends Record<string, unknown> {
  node: GraphNode;
  editMode?: boolean;
  onRename?: (id: string, newLabel: string) => void;
}

/** Data carried by a graph edge. */
export interface GraphEdgeData extends Record<string, unknown> {
  edge: GraphEdge;
}

export type GraphFlowNode = Node<GraphNodeData, "graphNode">;
export type GraphFlowEdge = Edge<GraphEdgeData, "graphEdge">;

export const DEFAULT_NODE_WIDTH = 180;
export const DEFAULT_NODE_HEIGHT = 64;

/**
 * Compute dagre positions for `nodes`/`edges` and return fully-built React
 * Flow node/edge arrays (all domain fields preserved via `data.node`/
 * `data.edge`, only `position` and the handle ids are (re)computed).
 *
 * @param nodes  Current node_graph nodes (with their existing, soon-to-be-
 *               replaced positions).
 * @param edges  Current node_graph edges.
 */
export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[]
): { nodes: GraphFlowNode[]; edges: GraphFlowEdge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 90, marginx: 24, marginy: 24 });

  for (const node of nodes) {
    const width = node.size?.width ?? DEFAULT_NODE_WIDTH;
    const height = node.size?.height ?? DEFAULT_NODE_HEIGHT;
    graph.setNode(node.id, { width, height });
  }
  for (const edge of edges) {
    // dagre cannot rank a self-loop; skip it for layout (the node keeps its
    // computed position and the self-loop edge still renders).
    if (edge.source !== edge.target) {
      graph.setEdge(edge.source, edge.target);
    }
  }

  dagre.layout(graph);

  const flowNodes: GraphFlowNode[] = nodes.map((node) => {
    const pos = graph.node(node.id);
    const width = node.size?.width ?? DEFAULT_NODE_WIDTH;
    const height = node.size?.height ?? DEFAULT_NODE_HEIGHT;
    // dagre returns the node CENTER; React Flow expects the top-left corner.
    return {
      id: node.id,
      type: "graphNode",
      position: { x: pos.x - width / 2, y: pos.y - height / 2 },
      // T8 (GH-353 final review): must match payloadToFlowNodes's
      // width/height so the two node-construction paths (initial load vs.
      // "Auto layout" toolbar action) produce the identical GraphFlowNode
      // shape — a diverging shape here is the same defect class as C1.
      width,
      height,
      data: { node },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });

  const flowEdges: GraphFlowEdge[] = edges.map((edge) => {
    const isSelfLoop = edge.source === edge.target;
    // Explicit handle ids (GraphNode renders top/bottom/left/right handles,
    // top/left = targets, bottom/right = sources — see GraphNode.tsx).
    // Self-loops leave from the right handle and re-enter at the top so they
    // render as a visible arc instead of collapsing onto themselves.
    const sourceHandle: GraphHandlePosition = isSelfLoop ? "right" : "bottom";
    const targetHandle: GraphHandlePosition = "top";
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "graphEdge",
      data: { edge: { ...edge, source_handle: sourceHandle, target_handle: targetHandle } },
      sourceHandle,
      targetHandle,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}
