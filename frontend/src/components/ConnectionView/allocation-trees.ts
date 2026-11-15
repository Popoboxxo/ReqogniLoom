/**
 * ARCH-L1-001 ReactFrontend — connection view "Bäume" tree construction (V.1).
 *
 * Pure module: no React hook, no JSX, no DOM access. It turns the flat
 * `allocation-view` rows into the two hierarchies the renderer draws and into
 * the allocation edges that cross the corridor between them.
 *
 * Only `compareRows` is imported from `useAllocationView`, so the row order has
 * exactly one definition (plan V.1); the module itself uses no React API.
 *
 * Contracts (plan V.1):
 *
 * - A requirement's parent is resolved through its **Artifact** id
 *   (`row.parent_id` -> `requirementByArtifact`), like `useArtifactList` does
 *   for the artifact tree. A missing parent node (filtered out, or no
 *   requirement artifact) makes the row a root — never a dropped row.
 * - Siblings sort by `sort_key` with a missing key **last**, tie-break `title`.
 * - Cycles and duplicate rows can never produce a node twice: a visited set
 *   guards the walk (same pattern as `AllocationGraph/buildGraph.ts`).
 * - The caller passes rows of **one** kind (the two reads are kind-scoped);
 *   a row of another kind is treated like any other row, not filtered here.
 * - `row.allocated_to` is the target element's **Artifact** id, so an edge only
 *   exists when that element is part of the rendered set. A requirement whose
 *   target sits outside the filter keeps its row but gets no edge — the row is
 *   "outside the filter", not "unallocated" (design §5.3).
 */

import type { AllocationRow } from '../../api/allocation-view';
import { compareRows } from './useAllocationView';

/** One requirement row placed in the requirement tree. */
export interface AllocationRequirementNode {
  row: AllocationRow;
  children: AllocationRequirementNode[];
  /** Distance from its root; roots are 0. */
  depth: number;
}

/** One allocation, both ends present in the rendered row set. */
export interface AllocationEdge {
  /** Requirement **entity** id (the tree row / React key). */
  requirementId: string;
  /** Element **entity** id (the element tree row / React key). */
  elementId: string;
}

/**
 * Identity of a row inside the tree.
 *
 * Parent links are Artifact ids, so the Artifact id is the natural key. A row
 * without one can never be the target of a `parent_id`, so its entity id is
 * used instead of dropping the row.
 */
function keyOf(row: AllocationRow): string {
  return row.artifact_id || row.id;
}

/**
 * Sibling order: `sort_key` ascending, a missing key **last**, `title` as the
 * tie-break.
 *
 * `compareRows` (reused from `useAllocationView`, per plan V.1) owns the key
 * comparison and the title tie-break, but it maps a missing key to `""` and
 * therefore sorts `null` *first* — the opposite of the tree contract. The
 * missing-key case is decided here before delegating, so the shared comparator
 * stays untouched and no other renderer changes its order.
 */
function compareSiblings(a: AllocationRow, b: AllocationRow): number {
  const aMissing = a.sort_key == null;
  const bMissing = b.sort_key == null;
  if (aMissing !== bMissing) return aMissing ? 1 : -1;
  return compareRows(a, b);
}

/**
 * Build the requirement hierarchy.
 *
 * Every row of `rows` appears exactly once in the result (as a root or as a
 * descendant of exactly one node). The input order is irrelevant: parents are
 * looked up by id, siblings are sorted.
 */
export function buildRequirementTree(rows: readonly AllocationRow[]): AllocationRequirementNode[] {
  const nodes = new Map<string, AllocationRequirementNode>();
  const rowByKey = new Map<string, AllocationRow>();
  const parentKeyByKey = new Map<string, string>();

  // One node per key — the first occurrence wins, so duplicate rows cannot
  // produce the same node twice.
  for (const row of rows) {
    const key = keyOf(row);
    if (nodes.has(key)) continue;
    nodes.set(key, { row, children: [], depth: 0 });
    rowByKey.set(key, row);
  }

  // Parent link per key. A parent outside the row set (filtered out) or a
  // self-link is no parent at all: the row becomes a root.
  for (const [key, row] of rowByKey) {
    const parentId = row.parent_id;
    if (!parentId || parentId === key) continue;
    if (!nodes.has(parentId)) continue;
    parentKeyByKey.set(key, parentId);
  }

  // Break cycles: walking up from a node must terminate. When the chain meets
  // itself, the edge of the node currently closing the loop is dropped, so the
  // cycle becomes a finite chain with one root (deterministic, no data loss).
  for (const startKey of nodes.keys()) {
    const chain = new Set<string>([startKey]);
    let current = startKey;
    for (;;) {
      const parentKey = parentKeyByKey.get(current);
      if (parentKey === undefined) break;
      if (chain.has(parentKey)) {
        parentKeyByKey.delete(current);
        break;
      }
      chain.add(parentKey);
      current = parentKey;
    }
  }

  const roots: AllocationRequirementNode[] = [];
  for (const [key, node] of nodes) {
    const parentKey = parentKeyByKey.get(key);
    const parent = parentKey === undefined ? undefined : nodes.get(parentKey);
    if (parent) parent.children.push(node);
    else roots.push(node);
  }

  // Depth assignment and sibling order in one walk. The visited set is the
  // duplicate guard: a key is placed once, whatever the assembled links say.
  const visited = new Set<string>();
  const sortSubtree = (siblings: AllocationRequirementNode[], depth: number): void => {
    siblings.sort((a, b) => compareSiblings(a.row, b.row));
    for (const node of siblings) {
      const key = keyOf(node.row);
      if (visited.has(key)) continue;
      visited.add(key);
      node.depth = depth;
      sortSubtree(node.children, depth + 1);
    }
  };
  sortSubtree(roots, 0);

  return roots;
}

/**
 * Build the allocation edges whose two ends are part of the rendered set.
 *
 * `allocated_to` carries the element's Artifact id; `elementId` in the result
 * is the element's **entity** id, because that is the element tree row's key.
 * A requirement without a resolvable target (unallocated, or the element is
 * outside the filter) yields no edge. At most one edge per requirement — the
 * relation is N:1.
 */
export function buildAllocationEdges(
  requirements: readonly AllocationRow[],
  elements: readonly AllocationRow[]
): AllocationEdge[] {
  const elementByArtifact = new Map<string, AllocationRow>();
  for (const element of elements) {
    const artifactId = element.artifact_id;
    if (!artifactId || elementByArtifact.has(artifactId)) continue;
    elementByArtifact.set(artifactId, element);
  }

  const edges: AllocationEdge[] = [];
  const emitted = new Set<string>();
  for (const requirement of requirements) {
    const targetArtifactId = requirement.allocated_to;
    if (!targetArtifactId) continue;
    if (emitted.has(requirement.id)) continue;
    const element = elementByArtifact.get(targetArtifactId);
    if (!element) continue;
    emitted.add(requirement.id);
    edges.push({ requirementId: requirement.id, elementId: element.id });
  }
  return edges;
}
