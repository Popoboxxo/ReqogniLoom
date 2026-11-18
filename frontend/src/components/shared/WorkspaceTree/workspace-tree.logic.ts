/**
 * WorkspaceTree — pure tree-model helpers (S4.2 WP-F decomposition).
 *
 * Extracted verbatim from `workspace-tree.tsx`: building the internal hierarchy
 * from the flat API list, flattening it into the rows that are actually
 * rendered, and naming a move target for the screen-reader announcement. The
 * functions have no React or DOM dependency, so they can be unit-tested
 * directly; the component keeps the hooks and all JSX.
 *
 * No behaviour change: the bodies are byte-for-byte the ones that used to live
 * in `workspace-tree.tsx`.
 */

import type { WorkspaceTreeNode } from './workspace-tree';

// ---------------------------------------------------------------------------
// Internal tree model
// ---------------------------------------------------------------------------

export interface InternalNode {
  node: WorkspaceTreeNode;
  children: InternalNode[];
  depth: number;
}

/**
 * Builds the internal tree from the flat `parentId` list.
 *
 * Nodes whose parent is missing (or cycles back into the visited set) become
 * roots, so a malformed list can never drop an artifact from the view.
 */
export function buildInternalTree(nodes: WorkspaceTreeNode[]): InternalNode[] {
  const byId = new Map<string, WorkspaceTreeNode>();
  for (const n of nodes) byId.set(n.id, n);

  const childrenByParent = new Map<string | null, WorkspaceTreeNode[]>();
  for (const n of nodes) {
    const parentKey =
      n.parentId && byId.has(n.parentId) ? n.parentId : null;
    const bucket = childrenByParent.get(parentKey);
    if (bucket) bucket.push(n);
    else childrenByParent.set(parentKey, [n]);
  }

  const toInternal = (
    n: WorkspaceTreeNode,
    depth: number,
    seen: Set<string>,
  ): InternalNode => {
    seen.add(n.id);
    const kids = (childrenByParent.get(n.id) ?? []).filter(
      (c) => !seen.has(c.id),
    );
    return {
      node: n,
      depth,
      children: kids.map((c) => toInternal(c, depth + 1, seen)),
    };
  };

  const seen = new Set<string>();
  return (childrenByParent.get(null) ?? []).map((root) =>
    toInternal(root, 0, seen),
  );
}

export interface FlatRow {
  internal: InternalNode;
  hasChildren: boolean;
  isExpanded: boolean;
}

/**
 * Flattens the internal tree into the currently visible rows.
 *
 * `visibleIds === null` means "no active search": only `expanded` decides which
 * subtrees are open. With a search filter, every matched subtree is
 * force-expanded and only ids in `visibleIds` are emitted.
 */
export function flattenVisible(
  roots: InternalNode[],
  expanded: Set<string>,
  visibleIds: Set<string> | null,
  out: FlatRow[] = [],
): FlatRow[] {
  for (const internal of roots) {
    if (visibleIds !== null && !visibleIds.has(internal.node.id)) continue;
    const visibleChildren =
      visibleIds === null
        ? internal.children
        : internal.children.filter((c) => visibleIds.has(c.node.id));
    const hasChildren = visibleChildren.length > 0;
    // While searching, matched subtrees are force-expanded.
    const isExpanded = visibleIds !== null ? true : expanded.has(internal.node.id);
    out.push({ internal, hasChildren, isExpanded });
    if (hasChildren && isExpanded) {
      flattenVisible(internal.children, expanded, visibleIds, out);
    }
  }
  return out;
}

/**
 * Human-readable name of a reparenting endpoint for the move announcement
 * (H-1 / F-01). Mirrors the "identifier · name" form the move dialog's own
 * options render, and falls back to the dialog's root label when there is no
 * parent node (moving to top level).
 */
export function describeMoveTarget(
  node: WorkspaceTreeNode | null | undefined,
  rootLabel: string,
): string {
  if (!node) return rootLabel;
  return node.identifier ? `${node.identifier} · ${node.name}` : node.name;
}
