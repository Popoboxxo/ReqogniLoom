/**
 * ARCH-L1-001 ReactFrontend — connection view edge geometry (V.2).
 *
 * Pure module: row rectangles in, SVG path strings out. No React, no DOM, no
 * measurement — the renderer measures, this module only turns measurements
 * into a corridor-shaped Bézier.
 *
 * Contracts (plan V.2):
 *
 * - One path per edge whose **both** ends are in the maps. Unmounted rows
 *   (collapsed subtree, scrolled-away) are simply absent and therefore
 *   skipped instead of guessed (design §S9).
 * - The output order is stable and independent of the input order: sorted by
 *   `requirementId`, so React keeps its keys and never remounts a path.
 * - A path starts at the left gutter edge `x1`, ends at the right one `x2`,
 *   and runs at row height (`top + height / 2`) on both sides.
 */

import type { AllocationEdge } from './allocation-trees';

/** Vertical extent of one rendered row, relative to the shared scroll content. */
export interface RowRect {
  top: number;
  height: number;
}

/** One allocation edge as an SVG path, keyed by its requirement. */
export interface EdgePath {
  /** Stable React key, derived from the requirement only. */
  id: string;
  /** SVG path data of the corridor Bézier. */
  d: string;
}

/**
 * Two decimals are below the visible resolution and keep the path string
 * stable across re-measurements (no `0.30000000000000004` churn).
 */
function round(value: number): number {
  return Math.round(value * 100) / 100;
}

function compareByRequirementId(a: AllocationEdge, b: AllocationEdge): number {
  if (a.requirementId === b.requirementId) return 0;
  return a.requirementId < b.requirementId ? -1 : 1;
}

/** Vertical centre of a row. */
function centreOf(rect: RowRect): number {
  return round(rect.top + rect.height / 2);
}

/**
 * Turn allocation edges into corridor Bézier paths.
 *
 * `from` maps requirement id -> requirement row rect, `to` maps element id ->
 * element row rect. `gutter.x1` is the right border of the requirement column,
 * `gutter.x2` the left border of the element column. Both control points sit on
 * the corridor's centre line, which gives horizontal tangents at the rows and a
 * smooth S-curve across the gutter.
 */
export function buildEdgePaths(
  edges: readonly AllocationEdge[],
  from: ReadonlyMap<string, RowRect>,
  to: ReadonlyMap<string, RowRect>,
  gutter: { x1: number; x2: number }
): EdgePath[] {
  const x1 = round(gutter.x1);
  const x2 = round(gutter.x2);
  const controlX = round((gutter.x1 + gutter.x2) / 2);

  const paths: EdgePath[] = [];
  const emitted = new Set<string>();
  for (const edge of edges.slice().sort(compareByRequirementId)) {
    // N:1 — at most one edge per requirement, so a duplicated edge cannot
    // produce a second path under the same React key.
    if (emitted.has(edge.requirementId)) continue;
    const source = from.get(edge.requirementId);
    const target = to.get(edge.elementId);
    if (!source || !target) continue;
    emitted.add(edge.requirementId);
    const y1 = centreOf(source);
    const y2 = centreOf(target);
    paths.push({
      id: `allocation:${edge.requirementId}`,
      d: `M ${x1} ${y1} C ${controlX} ${y1}, ${controlX} ${y2}, ${x2} ${y2}`,
    });
  }
  return paths;
}
