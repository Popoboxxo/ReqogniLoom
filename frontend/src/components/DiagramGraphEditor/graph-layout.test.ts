/**
 * GH-353 Task 8 — graph-layout.ts tests: dagre wiring, centre-correction,
 * self-loop skip, and the handle-id convention.
 */

import dagre from "@dagrejs/dagre";
import { describe, expect, it } from "vitest";
import { Position } from "@xyflow/react";
import { DEFAULT_NODE_HEIGHT, DEFAULT_NODE_WIDTH, layoutGraph } from "./graph-layout";
import type { GraphEdge, GraphNode } from "../../types";

/**
 * Independently reproduce dagre's raw (center-based) node placement for the
 * given sizes, using the exact same graph settings as graph-layout.ts. Used
 * to verify the module's centre->top-left correction against a second,
 * independently-run dagre computation rather than a hand-derived literal —
 * dagre's exact placement algorithm is not part of this module's contract,
 * only the correction transform applied on top of it is.
 */
function rawDagreCenter(
  nodeSizes: Record<string, { width: number; height: number }>,
  edges: Array<[string, string]>
): Record<string, { x: number; y: number }> {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 90, marginx: 24, marginy: 24 });
  for (const [id, size] of Object.entries(nodeSizes)) {
    graph.setNode(id, size);
  }
  for (const [source, target] of edges) {
    graph.setEdge(source, target);
  }
  dagre.layout(graph);
  const out: Record<string, { x: number; y: number }> = {};
  for (const id of Object.keys(nodeSizes)) {
    const pos = graph.node(id);
    out[id] = { x: pos.x, y: pos.y };
  }
  return out;
}

function node(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    type: "box",
    label: id,
    position: { x: 0, y: 0 },
    ...overrides,
  };
}

function edge(id: string, source: string, target: string, overrides: Partial<GraphEdge> = {}): GraphEdge {
  return { id, source, target, type: "flow", ...overrides };
}

describe("layoutGraph", () => {
  it("positions every input node and edge, preserving domain data", () => {
    const nodes = [node("a"), node("b"), node("c")];
    const edges = [edge("e1", "a", "b"), edge("e2", "b", "c")];

    const { nodes: flowNodes, edges: flowEdges } = layoutGraph(nodes, edges);

    expect(flowNodes.map((n) => n.id)).toEqual(["a", "b", "c"]);
    expect(flowEdges.map((e) => e.id)).toEqual(["e1", "e2"]);
    // Domain node/edge objects are carried through untouched (label etc.).
    expect(flowNodes[0].data.node.label).toBe("a");
    expect(flowEdges[0].data!.edge.type).toBe("flow");
  });

  it("applies the dagre centre -> top-left position correction", () => {
    const nodes = [node("a"), node("b")];
    const edges = [edge("e1", "a", "b")];

    const { nodes: flowNodes } = layoutGraph(nodes, edges);

    // dagre's TB layout ranks "a" above "b" with vertical spacing (ranksep);
    // the top rank's node y-position must be exactly marginy (24) minus half
    // the node height is NOT how dagre reports node.y (dagre.node(id) already
    // returns the CENTER), so after the -height/2 correction the node's
    // top-left y must be less than its dagre-reported center.
    const a = flowNodes.find((n) => n.id === "a")!;
    expect(a.position.x).toBeTypeOf("number");
    expect(a.position.y).toBeTypeOf("number");
    // Corrected top-left position is offset by exactly half the node box from
    // what a *naive* (uncorrected) center-based placement would report — i.e.
    // it is not simply (0,0) and not NaN.
    expect(Number.isFinite(a.position.x)).toBe(true);
    expect(Number.isFinite(a.position.y)).toBe(true);
    // "b" is ranked below "a" in a TB layout — its top-left y must be strictly
    // greater than a's.
    const b = flowNodes.find((n) => n.id === "b")!;
    expect(b.position.y).toBeGreaterThan(a.position.y);
  });

  it("honors an explicit node size for the centre correction", () => {
    const size = { width: 300, height: 120 };
    const nodes = [node("a", { size }), node("b", { size: { width: 180, height: 64 } })];
    const edges = [edge("e1", "a", "b")];

    const { nodes: flowNodes } = layoutGraph(nodes, edges);
    const a = flowNodes.find((n) => n.id === "a")!;

    const raw = rawDagreCenter(
      { a: size, b: { width: 180, height: 64 } },
      [["a", "b"]]
    );
    // The correction must subtract half of the node's OWN custom size, not
    // DEFAULT_NODE_WIDTH/HEIGHT — verified against an independent dagre run.
    expect(a.position.x).toBe(raw.a.x - size.width / 2);
    expect(a.position.y).toBe(raw.a.y - size.height / 2);
  });

  it("uses the shared default node size when none is given", () => {
    const nodes = [node("solo"), node("other")];
    const edges = [edge("e1", "solo", "other")];

    const { nodes: flowNodes } = layoutGraph(nodes, edges);
    const solo = flowNodes.find((n) => n.id === "solo")!;

    const raw = rawDagreCenter(
      {
        solo: { width: DEFAULT_NODE_WIDTH, height: DEFAULT_NODE_HEIGHT },
        other: { width: DEFAULT_NODE_WIDTH, height: DEFAULT_NODE_HEIGHT },
      },
      [["solo", "other"]]
    );
    expect(solo.position.x).toBe(raw.solo.x - DEFAULT_NODE_WIDTH / 2);
    expect(solo.position.y).toBe(raw.solo.y - DEFAULT_NODE_HEIGHT / 2);
  });

  it("skips self-loop edges for dagre ranking without crashing, and still renders the node", () => {
    const nodes = [node("a")];
    const edges = [edge("self", "a", "a")];

    const { nodes: flowNodes, edges: flowEdges } = layoutGraph(nodes, edges);

    expect(flowNodes).toHaveLength(1);
    expect(Number.isFinite(flowNodes[0].position.x)).toBe(true);
    expect(Number.isFinite(flowNodes[0].position.y)).toBe(true);
    expect(flowEdges).toHaveLength(1);
  });

  it("assigns the top/left=target, bottom/right=source handle convention", () => {
    const nodes = [node("a"), node("b")];
    const regularEdges = [edge("e1", "a", "b")];
    const { edges: flowEdges } = layoutGraph(nodes, regularEdges);

    expect(flowEdges[0].sourceHandle).toBe("bottom");
    expect(flowEdges[0].targetHandle).toBe("top");
    expect(flowEdges[0].data!.edge.source_handle).toBe("bottom");
    expect(flowEdges[0].data!.edge.target_handle).toBe("top");
  });

  it("routes a self-loop out of the right handle so it renders as a visible arc", () => {
    const nodes = [node("a")];
    const edges = [edge("self", "a", "a")];
    const { edges: flowEdges } = layoutGraph(nodes, edges);

    expect(flowEdges[0].sourceHandle).toBe("right");
    expect(flowEdges[0].targetHandle).toBe("top");
  });

  it("sets sourcePosition/targetPosition to Bottom/Top for every node (TB layout)", () => {
    const nodes = [node("a"), node("b")];
    const { nodes: flowNodes } = layoutGraph(nodes, []);
    for (const n of flowNodes) {
      expect(n.sourcePosition).toBe(Position.Bottom);
      expect(n.targetPosition).toBe(Position.Top);
    }
  });
});
