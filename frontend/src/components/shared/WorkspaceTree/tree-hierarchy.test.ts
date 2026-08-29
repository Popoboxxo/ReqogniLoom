/**
 * Unit tests for the shared hierarchy helper (REQ-003).
 *
 * Both parent-changing surfaces depend on this one function — the tree's drag
 * & drop and ArchitectureForm's parent dropdown — so its edge cases are worth
 * pinning down here rather than only through either UI.
 */

import { describe, expect, it } from 'vitest';
import { collectAncestorIds, collectSelfAndDescendantIds } from './tree-hierarchy';
import type { HierarchyRef } from './tree-hierarchy';

const TREE: HierarchyRef[] = [
  { id: 'root', parentId: null },
  { id: 'a', parentId: 'root' },
  { id: 'b', parentId: 'root' },
  { id: 'a1', parentId: 'a' },
  { id: 'a2', parentId: 'a' },
  { id: 'a1x', parentId: 'a1' },
];

describe('collectSelfAndDescendantIds', () => {
  it('always contains the node itself', () => {
    expect(collectSelfAndDescendantIds(TREE, 'a1x')).toEqual(new Set(['a1x']));
  });

  it('collects direct children', () => {
    expect(collectSelfAndDescendantIds(TREE, 'a1')).toEqual(
      new Set(['a1', 'a1x']),
    );
  });

  it('collects transitive descendants across several levels', () => {
    expect(collectSelfAndDescendantIds(TREE, 'a')).toEqual(
      new Set(['a', 'a1', 'a2', 'a1x']),
    );
  });

  it('excludes siblings and ancestors', () => {
    const forbidden = collectSelfAndDescendantIds(TREE, 'a');
    expect(forbidden.has('b')).toBe(false);
    expect(forbidden.has('root')).toBe(false);
  });

  it('returns just the node for an id that is not in the list', () => {
    expect(collectSelfAndDescendantIds(TREE, 'ghost')).toEqual(
      new Set(['ghost']),
    );
  });

  it('terminates on already-corrupted data containing a cycle', () => {
    // A cycle can already exist in the data (e.g. written by an API client
    // that bypassed this guard); the walk must not spin forever on it.
    const corrupted: HierarchyRef[] = [
      { id: 'x', parentId: 'y' },
      { id: 'y', parentId: 'x' },
      { id: 'z', parentId: 'y' },
    ];
    expect(collectSelfAndDescendantIds(corrupted, 'x')).toEqual(
      new Set(['x', 'y', 'z']),
    );
  });

  it('handles an empty hierarchy', () => {
    expect(collectSelfAndDescendantIds([], 'lonely')).toEqual(
      new Set(['lonely']),
    );
  });
});

describe('collectAncestorIds (#668/#665)', () => {
  it('walks up to the root, nearest parent first', () => {
    expect(collectAncestorIds(TREE, 'a1x')).toEqual(['a1', 'a', 'root']);
  });

  it('never includes the node itself', () => {
    expect(collectAncestorIds(TREE, 'a1x')).not.toContain('a1x');
  });

  it('returns an empty list for a root node', () => {
    expect(collectAncestorIds(TREE, 'root')).toEqual([]);
  });

  it('excludes siblings and descendants', () => {
    const ancestors = collectAncestorIds(TREE, 'a1');
    expect(ancestors).not.toContain('a2');
    expect(ancestors).not.toContain('a1x');
    expect(ancestors).not.toContain('b');
  });

  it('returns nothing for an id that is not in the list', () => {
    expect(collectAncestorIds(TREE, 'ghost')).toEqual([]);
  });

  it('stops at a dangling parentId instead of inventing an ancestor', () => {
    // Happens whenever the tree shows a filtered slice of the hierarchy —
    // `buildInternalTree` treats such a node as a root, so must this walk.
    const orphaned: HierarchyRef[] = [{ id: 'lone', parentId: 'not-loaded' }];
    expect(collectAncestorIds(orphaned, 'lone')).toEqual([]);
  });

  it('terminates on already-corrupted data containing a cycle', () => {
    const corrupted: HierarchyRef[] = [
      { id: 'x', parentId: 'y' },
      { id: 'y', parentId: 'x' },
    ];
    expect(collectAncestorIds(corrupted, 'x')).toEqual(['y']);
  });

  it('handles an empty hierarchy', () => {
    expect(collectAncestorIds([], 'lonely')).toEqual([]);
  });
});
