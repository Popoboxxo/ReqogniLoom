/**
 * V.2 — tests for the pure edge geometry.
 *
 * The module gets row rectangles (already measured by the renderer) and returns
 * SVG paths, so the tests pin exactly the contracts the plan names: one path
 * per resolvable edge, no path with a missing end, stable order independent of
 * the input order, and paths that start/end on the gutter borders at row
 * height.
 */

import { describe, expect, it } from 'vitest';

import type { AllocationEdge } from './allocation-trees';
import { buildEdgePaths, type RowRect } from './edge-geometry';

const GUTTER = { x1: 0, x2: 120 };

function edge(requirementId: string, elementId = `el-${requirementId}`): AllocationEdge {
  return { requirementId, elementId };
}

function rects(entries: ReadonlyArray<[string, RowRect]>): ReadonlyMap<string, RowRect> {
  return new Map(entries);
}

describe('buildEdgePaths', () => {
  it('produces_one_path_per_resolvable_edge', () => {
    const from = rects([
      ['r1', { top: 0, height: 28 }],
      ['r2', { top: 28, height: 28 }],
    ]);
    const to = rects([
      ['el-r1', { top: 0, height: 28 }],
      ['el-r2', { top: 56, height: 28 }],
    ]);

    const paths = buildEdgePaths([edge('r1'), edge('r2'), edge('r1')], from, to, GUTTER);

    expect(paths).toHaveLength(2);
    expect(paths.map((path) => path.id)).toEqual(['allocation:r1', 'allocation:r2']);
  });

  it('skips_edges_with_missing_end', () => {
    const from = rects([
      ['r1', { top: 0, height: 28 }],
      ['r2', { top: 28, height: 28 }],
      ['r3', { top: 56, height: 28 }],
    ]);
    const to = rects([['el-r1', { top: 0, height: 28 }]]);

    const paths = buildEdgePaths([edge('r1'), edge('r2'), edge('r3')], from, to, GUTTER);

    // r2 has no element rect, r3 has no requirement rect — both are skipped
    // instead of being drawn to a guessed position.
    expect(paths).toHaveLength(1);
    expect(paths[0].id).toBe('allocation:r1');
  });

  it('order_is_stable_independent_of_input_order', () => {
    const from = rects([
      ['r1', { top: 0, height: 28 }],
      ['r2', { top: 28, height: 28 }],
      ['r3', { top: 56, height: 28 }],
    ]);
    const to = rects([
      ['el-r1', { top: 0, height: 28 }],
      ['el-r2', { top: 28, height: 28 }],
      ['el-r3', { top: 56, height: 28 }],
    ]);
    const ordered = [edge('r1'), edge('r2'), edge('r3')];
    const shuffled = [edge('r3'), edge('r1'), edge('r2')];

    const first = buildEdgePaths(ordered, from, to, GUTTER);
    const second = buildEdgePaths(shuffled, from, to, GUTTER);

    expect(second).toEqual(first);
    expect(first.map((path) => path.id)).toEqual([
      'allocation:r1',
      'allocation:r2',
      'allocation:r3',
    ]);
  });

  it('path_starts_and_ends_at_gutter_edges', () => {
    const from = rects([['r1', { top: 20, height: 28 }]]);
    const to = rects([['el-r1', { top: 100, height: 20 }]]);

    const [path] = buildEdgePaths([edge('r1')], from, to, GUTTER);

    // Vertical centre of the rows: 20 + 14 = 34 and 100 + 10 = 110. The path
    // begins on the requirement gutter border (x1) and ends on the element one
    // (x2); both control points sit inside the corridor.
    expect(path.d).toBe('M 0 34 C 60 34, 60 110, 120 110');
  });
});
