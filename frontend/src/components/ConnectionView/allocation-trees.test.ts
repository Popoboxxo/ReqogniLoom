/**
 * V.1 — tests for the pure tree builders.
 *
 * The builders are pure, so the tests pin the contracts the plan names: parent
 * resolution by Artifact id, a missing parent becoming a root, `sort_key`
 * order with `null` last, cycle/duplicate safety, and allocation edges only
 * when both ends are in the rendered set.
 */

import { describe, expect, it } from 'vitest';

import type { AllocationRow } from '../../api/allocation-view';
import {
  buildAllocationEdges,
  buildRequirementTree,
  type AllocationRequirementNode,
} from './allocation-trees';

function requirement(id: string, overrides: Partial<AllocationRow> = {}): AllocationRow {
  return {
    kind: 'requirement',
    id,
    artifact_id: `a-${id}`,
    parent_id: null,
    sort_key: null,
    title: id,
    state: null,
    tier_key: null,
    tier_name: null,
    level: null,
    type: null,
    category: null,
    allocated_to: null,
    allocation_trace_link_id: null,
    element_id: null,
    allocation_intent: null,
    locked: null,
    findings: [],
    group: null,
    ...overrides,
  };
}

function element(id: string, overrides: Partial<AllocationRow> = {}): AllocationRow {
  return {
    kind: 'element',
    id,
    artifact_id: `ea-${id}`,
    parent_id: null,
    sort_key: null,
    title: id,
    state: null,
    tier_key: null,
    tier_name: null,
    level: null,
    type: null,
    category: null,
    allocated_to: null,
    allocation_trace_link_id: null,
    element_id: null,
    allocation_intent: null,
    locked: null,
    findings: [],
    group: null,
    ...overrides,
  };
}

/** Pre-order list of `[id, depth]` pairs — the shape of the rendered tree. */
function flatten(nodes: readonly AllocationRequirementNode[]): Array<[string, number]> {
  const out: Array<[string, number]> = [];
  const walk = (siblings: readonly AllocationRequirementNode[]): void => {
    for (const node of siblings) {
      out.push([node.row.id, node.depth]);
      walk(node.children);
    }
  };
  walk(nodes);
  return out;
}

describe('buildRequirementTree', () => {
  it('builds_roots_and_children', () => {
    const rows = [
      requirement('child', { parent_id: 'a-root', sort_key: 'a0' }),
      requirement('root'),
      requirement('grandchild', { parent_id: 'a-child', sort_key: 'a1' }),
      requirement('second-root'),
    ];

    const roots = buildRequirementTree(rows);

    expect(roots.map((node) => node.row.id)).toEqual(['root', 'second-root']);
    expect(flatten(roots)).toEqual([
      ['root', 0],
      ['child', 1],
      ['grandchild', 2],
      ['second-root', 0],
    ]);
  });

  it('missing_parent_becomes_root', () => {
    // The parent artifact is not part of the filtered row set — the child must
    // still be rendered, as a root (same behaviour as `useArtifactList`).
    const rows = [
      requirement('orphan', { parent_id: 'a-filtered-out' }),
      requirement('self', { parent_id: 'a-self' }),
    ];

    const roots = buildRequirementTree(rows);

    expect(flatten(roots)).toEqual([
      ['orphan', 0],
      ['self', 0],
    ]);
  });

  it('siblings_sort_by_sort_key_with_null_last', () => {
    const rows = [
      requirement('no-key-b', { parent_id: 'a-root', sort_key: null, title: 'b' }),
      requirement('second', { parent_id: 'a-root', sort_key: 'a1' }),
      requirement('first', { parent_id: 'a-root', sort_key: 'a0' }),
      requirement('no-key-a', { parent_id: 'a-root', sort_key: null, title: 'a' }),
      // Same key, different title: the tie-break must decide, not the input.
      requirement('same-key-z', { parent_id: 'a-root', sort_key: 'a1', title: 'z' }),
      requirement('same-key-a', { parent_id: 'a-root', sort_key: 'a1', title: 'a' }),
      requirement('root'),
    ];

    const roots = buildRequirementTree(rows);
    const root = roots.find((node) => node.row.id === 'root');

    expect(root?.children.map((node) => node.row.id)).toEqual([
      'first',
      'same-key-a',
      'second',
      'same-key-z',
      'no-key-a',
      'no-key-b',
    ]);
  });

  it('cycle_is_broken', () => {
    const rows = [
      requirement('a', { parent_id: 'a-b' }),
      requirement('b', { parent_id: 'a-c' }),
      requirement('c', { parent_id: 'a-a' }),
    ];

    const roots = buildRequirementTree(rows);

    // Exactly one root, every row reachable once, finite depth per level.
    expect(roots).toHaveLength(1);
    const flat = flatten(roots);
    expect(flat.map(([id]) => id).sort()).toEqual(['a', 'b', 'c']);
    expect(new Set(flat.map(([, depth]) => depth)).size).toBe(3);
  });

  it('no_node_appears_twice', () => {
    const rows = [
      requirement('root'),
      requirement('child', { parent_id: 'a-root' }),
      // A row delivered twice (duplicate page / stale cache): one node only.
      requirement('child', { parent_id: 'a-root' }),
      requirement('child', { parent_id: 'a-unknown' }),
    ];

    const roots = buildRequirementTree(rows);
    const flat = flatten(roots);

    expect(flat.map(([id]) => id)).toEqual(['root', 'child']);
    expect(flat.filter(([id]) => id === 'child')).toHaveLength(1);
  });
});

describe('buildAllocationEdges', () => {
  it('edge_only_when_both_ends_present', () => {
    const requirements = [
      requirement('in-set', { allocated_to: 'ea-brake' }),
      // Target element is filtered out: the row stays, the edge does not.
      requirement('outside-filter', { allocated_to: 'ea-filtered-out' }),
      requirement('unallocated'),
    ];
    const elements = [element('brake')];

    expect(buildAllocationEdges(requirements, elements)).toEqual([
      { requirementId: 'in-set', elementId: 'brake' },
    ]);
  });

  it('edge_count_matches_allocations', () => {
    const requirements = [
      requirement('r1', { allocated_to: 'ea-brake' }),
      requirement('r2', { allocated_to: 'ea-brake' }),
      requirement('r3', { allocated_to: 'ea-wheel' }),
      requirement('r4'),
      requirement('r5', { allocated_to: 'ea-gone' }),
    ];
    const elements = [element('brake'), element('wheel')];

    const edges = buildAllocationEdges(requirements, elements);

    // One edge per resolvable allocation (N:1 — two requirements may share an
    // element), none for unallocated or unresolvable rows.
    expect(edges).toHaveLength(3);
    expect(edges.map((edge) => edge.requirementId)).toEqual(['r1', 'r2', 'r3']);
  });
});
