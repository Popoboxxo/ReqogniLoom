/**
 * REQ-176 — Auto-layout for the workflow graph via @dagrejs/dagre.
 *
 * Turns the derived WorkflowGraph (states + transitions) into positioned
 * React Flow Node[] / Edge[] arrays. Layout is top-to-bottom (rankdir "TB")
 * with 80px horizontal / 100px vertical spacing per the design brief (§5).
 */

import dagre from "@dagrejs/dagre";
import {
  getBezierPath,
  MarkerType,
  Position,
  type Edge,
  type Node,
} from "@xyflow/react";
import type { WorkflowState, WorkflowTransition } from "../../api/workflows";

/** Data carried by a state node. */
export interface StateNodeData extends Record<string, unknown> {
  state: WorkflowState;
  /** REQ-177 — edit-mode affordances injected by the canvas. */
  editMode?: boolean;
  onRename?: (oldName: string, newName: string) => void;
}

/** A flow-coordinate offset applied to an edge's floating label pill. */
export interface EdgeLabelOffset {
  x: number;
  y: number;
}

/** Data carried by a transition edge. */
export interface TransitionEdgeData extends Record<string, unknown> {
  transition: WorkflowTransition;
  /**
   * Deterministic collision-avoidance offset (flow px) for the label pill.
   * Injected by {@link resolveEdgeLabelOffsets} at the canvas level, after
   * persisted node positions have been applied.
   */
  labelOffset?: EdgeLabelOffset;
}

export type StateFlowNode = Node<StateNodeData, "stateNode">;
export type TransitionFlowEdge = Edge<TransitionEdgeData, "transition">;

const NODE_WIDTH = 200;
const NODE_HEIGHT = 64;

/** WCAG 2.2 SC 2.5.8 minimum target size (CSS px); axe's `target-offset` check
 *  uses a 24px-diameter circle, i.e. a 12px radius around the target centre. */
export const TARGET_SIZE_MIN = 24;

/**
 * Minimum React Flow viewport zoom for the workflow canvas (WCAG 2.2 SC 2.5.8).
 *
 * React Flow renders nodes AND the `EdgeLabelRenderer` portal inside a single
 * `.react-flow__viewport` div whose CSS transform is `scale(zoom)`. The 24px
 * `min-width`/`min-height` on `.edgeLabel`/`.stateNode` (and the 28px label
 * offsets computed below) are therefore *flow* pixels: at zoom < 1 they shrink
 * on screen. axe measures *rendered* CSS pixels, so a zoom of e.g. 0.44 renders
 * a 24px target as ~10.6px and a 28px clearance as ~12.4px — failing BOTH halves
 * of the `target-size` rule (`target-size` >=24px OR `target-offset` >=24px).
 *
 * The extended workflow graph is ~480x1212 flow px (dagre TB, 9 states, 12
 * transitions). `fitView({ padding: 0.2 })` is height-constrained and picks
 * zoom ~= 0.44 in a ~640px-tall canvas — well below 1. Clamping the zoom floor
 * to 1 guarantees `24px * zoom >= 24px` rendered, so the CSS/geometry invariants
 * above hold in the browser exactly as they do in the unit tests. Users can
 * still pan and zoom in (up to maxZoom); they simply cannot shrink targets
 * below the AA minimum. See `workflow-editor-target-size.test.ts`.
 */
export const MIN_CANVAS_ZOOM = 1;
/** Centre-to-centre clearance between two labels — a little above the AA
 *  minimum so sub-pixel rounding can never re-introduce an overlap. */
const LABEL_CLEARANCE = TARGET_SIZE_MIN + 4;
/** Keep a label centre at least 12px (the axe circle radius) outside a state
 *  node's box; the extra 4px is tolerance for handle-position rounding. */
const NODE_CLEARANCE = TARGET_SIZE_MIN / 2 + 4;
/** React Flow's default 6px handles are translated half their size outside the
 *  node box, so an edge endpoint sits 3px beyond width/height. */
const HANDLE_OVERHANG = 3;
const MAX_RELAX_ITERATIONS = 16;

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

/**
 * Compute the bezier midpoint where React Flow will render one edge's label.
 *
 * Mirrors `getEdgePosition` + `getBezierPath` from `@xyflow/react`: handle
 * centres sit at the node's width/height plus the 3px handle overhang, and the
 * `bottom -> top` bezier midpoint is the plain midpoint of the two endpoints.
 * Keeping this a pure function lets the spacing invariant be unit-tested in
 * jsdom (which has no layout engine).
 */
export function computeEdgeLabelCenter(
  edge: TransitionFlowEdge,
  nodeById: ReadonlyMap<string, StateFlowNode>
): { x: number; y: number } {
  const source = nodeById.get(edge.source);
  const target = nodeById.get(edge.target);
  if (!source || !target) return { x: 0, y: 0 };

  const isSelfLoop = edge.source === edge.target;
  const sourceX =
    source.position.x +
    (isSelfLoop ? NODE_WIDTH + HANDLE_OVERHANG : NODE_WIDTH / 2);
  const sourceY =
    source.position.y +
    (isSelfLoop ? NODE_HEIGHT / 2 : NODE_HEIGHT + HANDLE_OVERHANG);
  const targetX = target.position.x + NODE_WIDTH / 2;
  const targetY = target.position.y - HANDLE_OVERHANG;

  const [, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition: isSelfLoop ? Position.Right : Position.Bottom,
    targetX,
    targetY,
    targetPosition: Position.Top,
  });
  return { x: labelX, y: labelY };
}

/**
 * Deterministically push overlapping edge-label targets apart.
 *
 * axe-core's `target-size` rule passes a target if EITHER its box is >=24px OR
 * no other focusable widget's box intersects the 24px circle around its centre
 * (`target-offset`). Both checks fail when two labels land on the exact same
 * bezier midpoint — which happens for every reciprocal transition pair (e.g.
 * `draft -> in_review` and `in_review -> draft`) — or when a label midpoint
 * falls inside a state node. The 24px `min-width`/`min-height` on `.edgeLabel`
 * fixes the size half only; this resolves the spacing half.
 *
 * The relaxation is idempotent and order-stable: identical input yields
 * identical offsets, so persisted layouts and re-renders do not jitter.
 *
 * @param edges  Rendered transition edges (source/target ids + handle choice).
 * @param nodes  Rendered state nodes (with their final positions).
 * @returns One offset per edge id, to be added to React Flow's labelX/labelY.
 */
export function resolveEdgeLabelOffsets(
  edges: readonly TransitionFlowEdge[],
  nodes: readonly StateFlowNode[]
): Map<string, EdgeLabelOffset> {
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const centres = edges.map((edge) => computeEdgeLabelCenter(edge, nodeById));
  const offsets: EdgeLabelOffset[] = centres.map(() => ({ x: 0, y: 0 }));
  const nodeBoxes = nodes.map((n) => ({
    left: n.position.x,
    right: n.position.x + NODE_WIDTH,
    top: n.position.y,
    bottom: n.position.y + NODE_HEIGHT,
  }));

  const current = (index: number): { x: number; y: number } => ({
    x: centres[index].x + offsets[index].x,
    y: centres[index].y + offsets[index].y,
  });

  for (let iteration = 0; iteration < MAX_RELAX_ITERATIONS; iteration += 1) {
    let moved = false;

    // Label <-> label: keep a >=LABEL_CLEARANCE centre distance. Favour the
    // vertical axis — pills can be up to 160px wide, so horizontal separation
    // alone does not guarantee the 24px circles clear each other.
    for (let i = 0; i < centres.length; i += 1) {
      for (let j = i + 1; j < centres.length; j += 1) {
        const a = current(i);
        const b = current(j);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.hypot(dx, dy);
        if (distance >= LABEL_CLEARANCE) continue;

        const push = (LABEL_CLEARANCE - distance) / 2 + 0.5;
        const axis =
          distance < 1e-6 || Math.abs(dy) >= Math.abs(dx) ? "y" : "x";
        const direction =
          axis === "y" ? (dy === 0 ? 1 : Math.sign(dy)) : Math.sign(dx);
        offsets[i][axis] -= push * direction;
        offsets[j][axis] += push * direction;
        moved = true;
      }
    }

    // Label <-> state node: push the label out of the node's box expanded by
    // NODE_CLEARANCE, along the axis of least penetration. Recompute `current`
    // per box so consecutive pushes see the already-adjusted position.
    for (let i = 0; i < centres.length; i += 1) {
      for (const box of nodeBoxes) {
        const c = current(i);
        const left = box.left - NODE_CLEARANCE;
        const right = box.right + NODE_CLEARANCE;
        const top = box.top - NODE_CLEARANCE;
        const bottom = box.bottom + NODE_CLEARANCE;
        if (c.x <= left || c.x >= right || c.y <= top || c.y >= bottom) continue;

        const dl = c.x - left;
        const dr = right - c.x;
        const dt = c.y - top;
        const db = bottom - c.y;
        const smallest = Math.min(dl, dr, dt, db);
        if (smallest === dt) offsets[i].y -= dt + 0.5;
        else if (smallest === db) offsets[i].y += db + 0.5;
        else if (smallest === dl) offsets[i].x -= dl + 0.5;
        else offsets[i].x += dr + 0.5;
        moved = true;
      }
    }

    if (!moved) break;
  }

  return new Map(edges.map((edge, index) => [edge.id, offsets[index]]));
}
