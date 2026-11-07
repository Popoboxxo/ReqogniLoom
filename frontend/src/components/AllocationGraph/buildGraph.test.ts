/**
 * P5 Task 5.1 — tests for the card graph model builder.
 *
 * The model is pure, so the tests assert the four contracts the plan names:
 * sibling order comes from `sort_key`, a requirement never gets more than one
 * allocation edge, collapsing hides descendants but keeps the aggregate count,
 * dimmed rows are marked rather than removed — plus a 500-row layout budget.
 */

import { describe, expect, it } from 'vitest';

import {
  ALLOCATION_STROKE,
  HIERARCHY_STROKE,
  NODE_WIDTH,
  buildGraph,
  type AllocationRow,
} from './buildGraph';

function requirement(id: string, overrides: Partial<AllocationRow> = {}): AllocationRow {
  return {
    kind: 'requirement',
    id,
    artifact_id: `a-${id}`,
    parent_id: null,
    sort_key: null,
    title: id,
    allocated_to: null,
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
    allocated_to: null,
    ...overrides,
  };
}

function nodeById(nodes: ReturnType<typeof buildGraph>['nodes'], rowId: string) {
  const node = nodes.find((candidate) => candidate.data.row.id === rowId);
  if (!node) throw new Error(`node for row ${rowId} not found`);
  return node;
}

function emptyOptions(): { collapsed: Set<string>; dimmed: (row: AllocationRow) => boolean } {
  return { collapsed: new Set<string>(), dimmed: () => false };
}

describe('buildGraph', () => {
  it('lays siblings out in sort_key order, not input order', () => {
    const rows = [
      requirement('root', { sort_key: 'a0' }),
      // deliberately shuffled input order
      requirement('third', { parent_id: 'a-root', sort_key: 'a2' }),
      requirement('first', { parent_id: 'a-root', sort_key: 'a0' }),
      requirement('second', { parent_id: 'a-root', sort_key: 'a1' }),
    ];

    const { nodes } = buildGraph(rows, emptyOptions());

    const first = nodeById(nodes, 'first').position.x;
    const second = nodeById(nodes, 'second').position.x;
    const third = nodeById(nodes, 'third').position.x;

    expect(first).toBeLessThan(second);
    expect(second).toBeLessThan(third);
  });

  it('keeps requirement cards in the left band and element cards in the right band', () => {
    const rows = [requirement('req', { sort_key: 'a0', allocated_to: 'ea-el' }), element('el')];

    const { nodes, edges } = buildGraph(rows, emptyOptions());
    const requirementNode = nodeById(nodes, 'req');
    const elementNode = nodeById(nodes, 'el');

    expect(requirementNode.position.x + NODE_WIDTH).toBeLessThan(elementNode.position.x);
    expect(edges).toHaveLength(1);
    expect(edges[0].data?.kind).toBe('allocation');
  });

  it('creates at most one allocation edge per requirement', () => {
    const rows = [
      requirement('r1', { sort_key: 'a0', allocated_to: 'ea-e1' }),
      // duplicate id with a different target: still one node / one edge
      requirement('r1', { sort_key: 'a0', allocated_to: 'ea-e2' }),
      requirement('r2', { sort_key: 'a1', allocated_to: 'ea-e1' }),
      element('e1'),
      element('e2'),
    ];

    const { nodes, edges } = buildGraph(rows, emptyOptions());
    const allocationEdges = edges.filter((edge) => edge.data?.kind === 'allocation');

    expect(nodes.filter((node) => node.data.row.id === 'r1')).toHaveLength(1);
    expect(allocationEdges).toHaveLength(2);
    expect(new Set(allocationEdges.map((edge) => edge.data?.requirementId))).toEqual(
      new Set(['r1', 'r2'])
    );
  });

  it('styles hierarchy edges grey and allocation edges dashed blue', () => {
    const rows = [
      requirement('root', { sort_key: 'a0' }),
      requirement('child', { parent_id: 'a-root', sort_key: 'a1', allocated_to: 'ea-el' }),
      element('el'),
    ];

    const { edges } = buildGraph(rows, emptyOptions());
    const hierarchy = edges.find((edge) => edge.data?.kind === 'hierarchy');
    const allocation = edges.find((edge) => edge.data?.kind === 'allocation');

    expect(hierarchy?.style?.stroke).toBe(HIERARCHY_STROKE);
    expect(allocation?.style?.stroke).toBe(ALLOCATION_STROKE);
    expect(allocation?.style?.strokeDasharray).toBe('6 4');
  });

  it('collapsing a branch hides descendants but keeps the aggregate count', () => {
    const rows = [
      requirement('root', { sort_key: 'a0' }),
      requirement('child', { parent_id: 'a-root', sort_key: 'a1' }),
      requirement('grandchild', { parent_id: 'a-child', sort_key: 'a2' }),
      requirement('sibling', { parent_id: 'a-root', sort_key: 'a3' }),
    ];

    const { nodes, edges } = buildGraph(rows, {
      collapsed: new Set(['root']),
      dimmed: () => false,
    });

    expect(nodes.map((node) => node.data.row.id)).toEqual(['root']);
    const root = nodeById(nodes, 'root');
    expect(root.data.collapsed).toBe(true);
    expect(root.data.descendantCount).toBe(3);
    expect(root.data.hiddenDescendantCount).toBe(3);
    expect(edges).toHaveLength(0);
  });

  it('accepts the node id as collapse key as well', () => {
    const rows = [
      requirement('root', { sort_key: 'a0' }),
      requirement('child', { parent_id: 'a-root', sort_key: 'a1' }),
    ];

    const { nodes } = buildGraph(rows, {
      collapsed: new Set(['req:root']),
      dimmed: () => false,
    });

    expect(nodes).toHaveLength(1);
    expect(nodes[0].data.hiddenDescendantCount).toBe(1);
  });

  it('marks dimmed rows but never removes them', () => {
    const rows = [
      requirement('keep', { sort_key: 'a0' }),
      requirement('dimmed', { sort_key: 'a1' }),
    ];

    const { nodes } = buildGraph(rows, {
      collapsed: new Set(),
      dimmed: (row) => row.id === 'dimmed',
    });

    expect(nodes).toHaveLength(2);
    expect(nodeById(nodes, 'dimmed').data.dimmed).toBe(true);
    expect(nodeById(nodes, 'dimmed').className).toContain('dimmed');
    expect(nodeById(nodes, 'keep').data.dimmed).toBe(false);
  });

  it('exposes unallocated and frozen flags on the node data', () => {
    const rows = [
      requirement('open', { sort_key: 'a0' }),
      requirement('frozen', {
        sort_key: 'a1',
        allocated_to: 'ea-el',
        locked: 'user-1',
      }),
      element('el'),
    ];

    const { nodes } = buildGraph(rows, emptyOptions());

    const open = nodeById(nodes, 'open');
    expect(open.data.unallocated).toBe(true);
    expect(open.data.frozen).toBe(false);

    const frozen = nodeById(nodes, 'frozen');
    expect(frozen.data.unallocated).toBe(false);
    expect(frozen.data.frozen).toBe(true);
  });

  it('lays out 500 rows well inside the time budget', () => {
    const rows: AllocationRow[] = [];
    const requirementCount = 250;
    const elementCount = 250;

    for (let index = 0; index < requirementCount; index += 1) {
      rows.push(
        requirement(`r${index}`, {
          sort_key: String(index).padStart(4, '0'),
          parent_id: index === 0 ? null : `a-r${index - 1}`,
          allocated_to: `ea-e${index % elementCount}`,
        })
      );
    }
    for (let index = 0; index < elementCount; index += 1) {
      rows.push(
        element(`e${index}`, {
          parent_id: index === 0 ? null : `e${index - 1}`,
        })
      );
    }

    const started = performance.now();
    const { nodes, edges } = buildGraph(rows, emptyOptions());
    const duration = performance.now() - started;

    expect(nodes).toHaveLength(requirementCount + elementCount);
    // 249 + 249 hierarchy edges plus one allocation per requirement.
    expect(edges).toHaveLength(requirementCount - 1 + (elementCount - 1) + requirementCount);
    expect(duration).toBeLessThan(1500);
  });
});
