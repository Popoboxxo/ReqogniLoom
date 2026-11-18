/**
 * A11Y-005 / WCAG 2.2 SC 2.5.8 (Target Size Minimum, AA): the live axe gate
 * (S3.3) flagged the transition edge label pill (`._edgeLabel_*[role="button"]`)
 * and the state node (`div[data-testid="workflow-state-node-proposed"]`) on
 * /workflows. Both floor their hit area at 24px via the existing `--space-6`
 * token — but axe's `target-size` rule is an OR: a target passes on SIZE *or*
 * on SPACING (no other focusable widget inside the 24px circle around its
 * centre). Reciprocal transitions (A->B / B->A) land on the exact same bezier
 * midpoint, so their two 24px circles intersect and BOTH checks fail. A label
 * midpoint can also fall inside a state node box. The fix therefore has two
 * halves, both pinned here:
 *
 *   1. CSS-source assertions for the >=24px hit area (below).
 *   2. Pure-function assertions for the deterministic label-offset relaxation
 *      in `layout.ts` — every label centre >=24px from every other label and
 *      >=12px (the axe circle radius) outside every state node box.
 *
 * Limitation: jsdom does not lay out elements, so the CSS assertions are source
 * assertions, not measurements of the rendered target. The spacing tests run
 * the REAL layout helpers (`layoutWorkflow`, `getBezierPath` and the resolver)
 * in flow coordinates; the final live axe run remains the gate's job.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { WorkflowState, WorkflowTransition } from "../api/workflows";
import {
  computeEdgeLabelCenter,
  layoutWorkflow,
  resolveEdgeLabelOffsets,
  TARGET_SIZE_MIN,
  type StateFlowNode,
  type TransitionFlowEdge,
} from "../components/WorkflowEditor/layout";

const SRC = join(__dirname, "..");
const CSS_PATH = "components/WorkflowEditor/WorkflowEditor.module.css";

/** Return the body of a single CSS rule, matched on its own selector line. */
function ruleBlock(source: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
  if (!match) {
    throw new Error(`CSS rule "${selector}" not found in ${CSS_PATH}`);
  }
  return match[1];
}

const css = readFileSync(join(SRC, CSS_PATH), "utf-8");

// ---------------------------------------------------------------------------
// Geometry helpers — flow-coordinate positions for the editor graph.
// ---------------------------------------------------------------------------

/** The seeded workspace's extended Requirement workflow (backend preset + the
 *  import-time `proposed` injection). Same states/transition pairs the a11y
 *  sweep renders on /workflows — including the reciprocal draft <-> in_review
 *  pair whose label centres coincide. */
const EXTENDED_STATES = [
  "draft", "proposed", "in_review", "approved", "implemented",
  "verified", "released", "deprecated", "rejected",
];
const EXTENDED_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ["draft", "in_review"],
  ["in_review", "approved"],
  ["approved", "deprecated"],
  ["in_review", "draft"],
  ["approved", "implemented"],
  ["implemented", "verified"],
  ["verified", "released"],
  ["approved", "released"],
  ["released", "deprecated"],
  ["verified", "deprecated"],
  ["proposed", "draft"],
  ["proposed", "rejected"],
];

function graphFrom(
  names: readonly string[],
  pairs: ReadonlyArray<readonly [string, string]>
): { nodes: StateFlowNode[]; edges: TransitionFlowEdge[] } {
  const outgoing: Record<string, number> = {};
  const incoming: Record<string, number> = {};
  for (const [, to] of pairs) incoming[to] = (incoming[to] ?? 0) + 1;
  for (const [from] of pairs) outgoing[from] = (outgoing[from] ?? 0) + 1;
  const states: WorkflowState[] = names.map((name, index) => ({
    id: name,
    name,
    type: index === 0 ? "initial" : "active",
    outgoingCount: outgoing[name] ?? 0,
    incomingCount: incoming[name] ?? 0,
    isInitial: index === 0,
  }));
  const transitions: WorkflowTransition[] = pairs.map(([from, to]) => ({
    id: `${from}__${to}`,
    name: `${from} -> ${to}`,
    from_state: from,
    to_state: to,
    change_reason_required: false,
    signature_gate: false,
  }));
  return layoutWorkflow(states, transitions);
}

/** Final (offset-applied) label centres, in the same flow coordinates React
 *  Flow uses for `getBezierPath`'s labelX/labelY. */
function resolvedCenters(
  nodes: readonly StateFlowNode[],
  edges: readonly TransitionFlowEdge[]
): Map<string, { x: number; y: number }> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const offsets = resolveEdgeLabelOffsets(edges, nodes);
  return new Map(
    edges.map((edge) => {
      const base = computeEdgeLabelCenter(edge, byId);
      const offset = offsets.get(edge.id) ?? { x: 0, y: 0 };
      return [edge.id, { x: base.x + offset.x, y: base.y + offset.y }];
    })
  );
}

/** Distance from a point to a rectangle; 0 when the point is inside it. */
function distanceToBox(
  point: { x: number; y: number },
  box: { left: number; right: number; top: number; bottom: number }
): number {
  if (
    point.x >= box.left &&
    point.x <= box.right &&
    point.y >= box.top &&
    point.y <= box.bottom
  ) {
    return 0;
  }
  const dx = Math.max(box.left - point.x, 0, point.x - box.right);
  const dy = Math.max(box.top - point.y, 0, point.y - box.bottom);
  return Math.hypot(dx, dy);
}

// ---------------------------------------------------------------------------
// 1. Hit-area size (CSS source; jsdom has no layout engine).
// ---------------------------------------------------------------------------

describe("WorkflowEditor touch targets — minimum size (SC 2.5.8)", () => {
  const edgeLabel = ruleBlock(css, ".edgeLabel");
  const stateNode = ruleBlock(css, ".stateNode");

  it("edge label reserves the 24px AA minimum width via --space-6", () => {
    expect(edgeLabel).toContain("min-width: var(--space-6)");
  });

  it("edge label reserves the 24px AA minimum height via --space-6", () => {
    expect(edgeLabel).toContain("min-height: var(--space-6)");
  });

  it("state node reserves the 24px AA minimum height via --space-6", () => {
    expect(stateNode).toContain("min-height: var(--space-6)");
  });

  it("state node keeps its wider intrinsic min-width (already above 24px)", () => {
    expect(stateNode).toContain("min-width: 160px");
  });

  it("keeps the edge label glyph/padding unchanged (no visual-snapshot change)", () => {
    expect(edgeLabel).toContain("padding: 2px 8px");
    expect(edgeLabel).toContain("font-size: var(--font-size-xs)");
  });

  it("TransitionEdge applies the injected collision-avoidance offset to its label", () => {
    const src = readFileSync(
      join(SRC, "components/WorkflowEditor/TransitionEdge.tsx"),
      "utf-8"
    );
    expect(src).toContain("data?.labelOffset");
    expect(src).toContain("labelX + labelOffset.x");
    expect(src).toContain("labelY + labelOffset.y");
  });
});

// ---------------------------------------------------------------------------
// 2. Spacing — the half the 24px min-size assertion cannot cover.
// ---------------------------------------------------------------------------

describe("WorkflowEditor touch targets — clearance (SC 2.5.8 spacing exception)", () => {
  it("separates two labels whose bezier midpoints coincide (reciprocal edges)", () => {
    const { nodes, edges } = graphFrom(["a", "b"], [["a", "b"], ["b", "a"]]);
    expect(edges).toHaveLength(2);

    const before = new Map(nodes.map((n) => [n.id, n]));
    expect(computeEdgeLabelCenter(edges[0], before)).toEqual(
      computeEdgeLabelCenter(edges[1], before)
    );

    const centers = resolvedCenters(nodes, edges);
    const [a, b] = [...centers.values()];
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(TARGET_SIZE_MIN);
  });

  it("keeps EVERY pair of demo-workflow label centres >=24px apart", () => {
    const { nodes, edges } = graphFrom(EXTENDED_STATES, EXTENDED_PAIRS);
    const centers = [...resolvedCenters(nodes, edges).values()];
    let closest = Number.POSITIVE_INFINITY;
    for (let i = 0; i < centers.length; i += 1) {
      for (let j = i + 1; j < centers.length; j += 1) {
        closest = Math.min(
          closest,
          Math.hypot(centers[i].x - centers[j].x, centers[i].y - centers[j].y)
        );
      }
    }
    expect(closest).toBeGreaterThanOrEqual(TARGET_SIZE_MIN);
  });

  it("keeps every demo-workflow label circle >=12px clear of every state node", () => {
    const { nodes, edges } = graphFrom(EXTENDED_STATES, EXTENDED_PAIRS);
    const centers = [...resolvedCenters(nodes, edges).values()];
    const boxes = nodes.map((n) => ({
      left: n.position.x,
      right: n.position.x + 200,
      top: n.position.y,
      bottom: n.position.y + 64,
    }));
    // axe's `target-offset` circle radius: 24px diameter / 2.
    const circleRadius = TARGET_SIZE_MIN / 2;
    for (const center of centers) {
      for (const box of boxes) {
        expect(distanceToBox(center, box)).toBeGreaterThanOrEqual(circleRadius);
      }
    }
  });

  it("is deterministic — identical input yields identical offsets", () => {
    const { nodes, edges } = graphFrom(EXTENDED_STATES, EXTENDED_PAIRS);
    const first = resolveEdgeLabelOffsets(edges, nodes);
    const second = resolveEdgeLabelOffsets(edges, nodes);
    expect([...first]).toEqual([...second]);
  });

  it("does not move labels that were already clear of every target", () => {
    const { nodes, edges } = graphFrom(
      ["a", "b", "c"],
      [["a", "b"], ["b", "c"]]
    );
    const offsets = resolveEdgeLabelOffsets(edges, nodes);
    for (const offset of offsets.values()) {
      expect(offset).toEqual({ x: 0, y: 0 });
    }
  });
});
