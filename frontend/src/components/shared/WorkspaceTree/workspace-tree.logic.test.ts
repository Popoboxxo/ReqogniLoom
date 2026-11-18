/**
 * Unit tests for the extracted WorkspaceTree model helpers (S4.2 WP-F).
 *
 * These three functions used to live inside `workspace-tree.tsx` and were only
 * covered indirectly through the component. Testing them directly pins the
 * hierarchy/visibility contracts that the keyboard and DnD paths rely on.
 */

import { describe, expect, it } from 'vitest';
import {
  buildInternalTree,
  describeMoveTarget,
  flattenVisible,
} from './workspace-tree.logic';
import type { WorkspaceTreeNode } from './workspace-tree';

const node = (
  id: string,
  parentId: string | null,
  extra: Partial<WorkspaceTreeNode> = {},
): WorkspaceTreeNode => ({ id, name: id, parentId, ...extra });

describe('buildInternalTree', () => {
  it('renders a flat list as roots in input order', () => {
    const roots = buildInternalTree([node('a', null), node('b', null)]);
    expect(roots.map((r) => r.node.id)).toEqual(['a', 'b']);
    expect(roots.every((r) => r.depth === 0 && r.children.length === 0)).toBe(true);
  });

  it('nests children under their parent and assigns increasing depth', () => {
    const [root] = buildInternalTree([
      node('root', null),
      node('child', 'root'),
      node('grandchild', 'child'),
    ]);
    expect(root.node.id).toBe('root');
    expect(root.depth).toBe(0);
    expect(root.children[0].node.id).toBe('child');
    expect(root.children[0].depth).toBe(1);
    expect(root.children[0].children[0].node.id).toBe('grandchild');
    expect(root.children[0].children[0].depth).toBe(2);
  });

  it('keeps sibling order as given in the flat list', () => {
    const [root] = buildInternalTree([
      node('root', null),
      node('first', 'root'),
      node('second', 'root'),
    ]);
    expect(root.children.map((c) => c.node.id)).toEqual(['first', 'second']);
  });

  it('promotes an orphan to root when its parent is missing', () => {
    const roots = buildInternalTree([node('orphan', 'ghost')]);
    expect(roots.map((r) => r.node.id)).toEqual(['orphan']);
    expect(roots[0].depth).toBe(0);
  });

  it('does not recurse into a cycle caused by a duplicate id', () => {
    const roots = buildInternalTree([
      node('a', null),
      node('b', 'a'),
      // Last-wins in the byId map makes 'a' a child of 'b' — a cycle. `seen`
      // still cuts the recursion at the second visit.
      node('ghost', 'b', { id: 'a' }),
    ]);
    expect(roots.map((r) => r.node.id)).toEqual(['a']);
    expect(roots[0].children.map((c) => c.node.id)).toEqual(['b']);
    expect(roots[0].children[0].children).toHaveLength(0);
  });
});

describe('flattenVisible', () => {
  const tree = buildInternalTree([
    node('root', null),
    node('a', 'root'),
    node('a1', 'a'),
    node('b', 'root'),
  ]);
  const ids = (rows: ReturnType<typeof flattenVisible>) =>
    rows.map((r) => r.internal.node.id);

  it('emits only roots while nothing is expanded', () => {
    expect(ids(flattenVisible(tree, new Set(), null))).toEqual(['root']);
  });

  it('emits children of an expanded node and keeps the parent first', () => {
    const rows = flattenVisible(tree, new Set(['root']), null);
    expect(ids(rows)).toEqual(['root', 'a', 'b']);
    expect(rows[0].isExpanded).toBe(true);
    expect(rows[1].hasChildren).toBe(true);
    expect(rows[1].isExpanded).toBe(false);
  });

  it('respects nested expansion state independently', () => {
    expect(ids(flattenVisible(tree, new Set(['root', 'a']), null))).toEqual([
      'root',
      'a',
      'a1',
      'b',
    ]);
  });

  it('force-expands matched subtrees during search', () => {
    const rows = flattenVisible(tree, new Set(), new Set(['root', 'a', 'a1']));
    expect(ids(rows)).toEqual(['root', 'a', 'a1']);
    expect(rows.every((r) => r.isExpanded)).toBe(true);
  });

  it('drops non-matching branches even when their parent matches', () => {
    const rows = flattenVisible(tree, new Set(), new Set(['root', 'b']));
    expect(ids(rows)).toEqual(['root', 'b']);
  });

  it('appends into a caller-supplied accumulator', () => {
    const out = [{ internal: tree[0], hasChildren: true, isExpanded: false }];
    const result = flattenVisible(tree, new Set(['root']), null, out);
    expect(result).toBe(out);
    expect(ids(result)).toEqual(['root', 'root', 'a', 'b']);
  });
});

describe('describeMoveTarget', () => {
  it('falls back to the root label when there is no target node', () => {
    expect(describeMoveTarget(null, 'Root')).toBe('Root');
    expect(describeMoveTarget(undefined, 'Root')).toBe('Root');
  });

  it('uses "identifier · name" when a readable id is present', () => {
    expect(
      describeMoveTarget(node('n1', null, { name: 'Alpha', identifier: 'REQ-001' }), 'Root'),
    ).toBe('REQ-001 · Alpha');
  });

  it('uses the bare name when no identifier is present', () => {
    expect(describeMoveTarget(node('n1', null, { name: 'Alpha' }), 'Root')).toBe(
      'Alpha',
    );
  });
});
