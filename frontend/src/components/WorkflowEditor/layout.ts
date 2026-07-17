/**
 * REQ-176 — Auto-layout for the workflow graph via @dagrejs/dagre.
 *
 * Turns the derived WorkflowGraph (states + transitions) into positioned
 * React Flow Node[] / Edge[] arrays. Layout is top-to-bottom (rankdir "TB")
 * with 80px horizontal / 100px vertical spacing per the design brief (§5).
 */

import dagre from "@dagrejs/dagre";
import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import type { WorkflowState, WorkflowTransition } from "../../api/workflows";

/** Data carried by a state node. */
export interface StateNodeData extends Record<string, unknown> {
  state: WorkflowState;
}

/** Data carried by a transition edge. */
export interface TransitionEdgeData extends Record<string, unknown> {
  transition: WorkflowTransition;
}

export type StateFlowNode = Node<StateNodeData, "stateNode">;
export type TransitionFlowEdge = Edge<TransitionEdgeData, "transition">;

const NODE_WIDTH = 200;
const NODE_HEIGHT = 64;

/**
 * Compute node positions and build the React Flow node/edge arrays.
 *
 * @param states       Derived workflow states.
 * @param transitions  Derived workflow transitions.
 * @returns positioned nodes and styled edges.
 */
export function layoutWorkflow(
  states: WorkflowState[],
  transitions: WorkflowTransition[]
): { nodes: StateFlowNode[]; edges: TransitionFlowEdge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 80, ranksep: 100, marginx: 24, marginy: 24 });

  for (const state of states) {
    graph.setNode(state.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const t of transitions) {
    // dagre cannot rank a self-loop; skip it for layout (the node keeps its
    // computed position and the self-loop edge still renders).
    if (t.from_state !== t.to_state) {
      graph.setEdge(t.from_state, t.to_state);
    }
  }

  dagre.layout(graph);

  const nodes: StateFlowNode[] = states.map((state) => {
    const pos = graph.node(state.id);
    // dagre returns the node CENTER; React Flow expects the top-left corner.
    return {
      id: state.id,
      type: "stateNode",
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { state },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
  });

  const edges: TransitionFlowEdge[] = transitions.map((t) => {
    const isSelfLoop = t.from_state === t.to_state;
    return {
      id: t.id,
      source: t.from_state,
      target: t.to_state,
      type: "transition",
      data: { transition: t },
      // Explicit handle ids (StateNode renders top/bottom/left/right handles).
      // Self-loops leave from the right handle and re-enter at the top so they
      // render as a visible arc instead of collapsing onto themselves.
      sourceHandle: isSelfLoop ? "right" : "bottom",
      targetHandle: "top",
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    };
  });

  return { nodes, edges };
}
