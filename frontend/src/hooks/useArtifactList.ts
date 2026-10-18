/**
 * ARCH-L1-001 ReactFrontend — shared editor-list derivation scaffolding.
 *
 * REUSE finding F-13 (frontend audit 2026-10-15, plan Phase 3a): the editor
 * lists (RequirementList, RiskList, IssueList, TestCaseList, AdrList,
 * NeedList — plus IcdList/DiagramList/InterviewList) each re-implemented the
 * same pure derivation chain:
 *
 *   visible   = items.filter(predicate(listSearch, …filters)) → sortItems(…)
 *   treeNodes = visible.map(toNode)
 *   byId      = Map from visible, keyed by item.id (renderRow hydration)
 *
 * This hook owns exactly that chain, verbatim: normalization of the search
 * box value is the one piece of logic it takes over from the call sites
 * (`query.trim().toLowerCase()`, historically written out in every list).
 * Everything else stays with the caller, because the precheck (plan §3.6,
 * re-baselined) shows the lists differ exactly there:
 *
 *   - `filter`  — text-match fields and extra filters differ per list
 *                 (title / title+id / title+uid / artifact_type+id /
 *                 name; category/status/type), same for the sort key union;
 *   - `sortItems` — each list keeps its own module-scope sorter
 *                 (`sortItems(list, sortKey)`), including the lists that
 *                 never sort (omit it);
 *   - `toNode`  — flat vs. hierarchical node mapping, some need `t` labels
 *                 (IcdList/DiagramList do not render a tree at all and
 *                 simply omit it — `treeNodes` is then the empty array);
 *   - `getKey`  — the byId lookup is opt-in: NeedList renders through the
 *                 tree's own nodes and never built one (plan §3.6).
 *
 * Stability contract: `filter`/`sortItems`/`toNode`/`getKey` are memo
 * dependencies. Callers must pass referentially stable functions (module
 * scope, like the existing `sortItems`/`xToNode` helpers, or `useCallback`
 * for closures over state) — otherwise the memoized chain degenerates to
 * "recompute everything on every render" (behaviorally identical, but the
 * hot-path lists virtualize and rely on stable identities). The derived
 * arrays are memoized on exactly the inputs the previous per-list `useMemo`
 * blocks used, so call sites keep their recomputation semantics 1:1.
 */

import { useMemo } from 'react';

import type { WorkspaceTreeNode } from '../components/shared/WorkspaceTree';

/**
 * Shared `treeNodes` result for callers that pass no `toNode` (IcdList,
 * DiagramList): a module-level constant so the identity is stable across
 * renders — the property still exists, it is simply always empty. Frozen at
 * runtime so a caller mutating `result.treeNodes` throws (strict mode)
 * instead of silently corrupting the shared array for every later render
 * (review nit); chosen over a fresh `[]` per render to keep the stable
 * identity documented above.
 */
const EMPTY_TREE_NODES: WorkspaceTreeNode[] = [];
Object.freeze(EMPTY_TREE_NODES);

/** Options every call passes; the coupled sort pair is added by the union below. */
interface UseArtifactListBaseOptions<T> {
  /** Source collection (already loaded); never mutated by the hook. */
  items: readonly T[];
  /**
   * Raw search-box value. Trimmed and lowercased once per derivation and
   * handed to `filter` as `normalizedQuery`; empty string when omitted.
   */
  query?: string;
  /**
   * Keep/turn-down predicate, called once per item with the normalized
   * query. Call sites keep their existing guards (`if (q && …)`), so an
   * empty query arrives as `''` and matches unconditionally.
   */
  filter?: (item: T, normalizedQuery: string) => boolean;
  /**
   * `WorkspaceTreeNode` mapper for the filtered list (flat rows use
   * `parentId: null`; RequirementList keeps its hierarchy). Omit for lists
   * not rendered through `WorkspaceTree`.
   */
  toNode?: (item: T) => WorkspaceTreeNode;
  /**
   * Key selector for the `byId` lookup (stable). Omit to skip building the
   * map — `byId` is then `undefined`. Artifact entities all key by `id`;
   * `artifactId` is the shared selector.
   */
  getKey?: (item: T) => string;
}

/**
 * `sortItems` and `sortKey` are coupled: the sorter needs the key, so either
 * both are provided or neither is. The union encodes that at the call site,
 * so the hook body no longer relies on an unchecked `sortKey as S` cast
 * (review nit) — previously `sortItems` without `sortKey` type-checked and
 * silently sorted by `undefined`.
 */
export type UseArtifactListOptions<T, S = string> =
  | (UseArtifactListBaseOptions<T> & {
      /**
       * Sorter applied to the filtered copy — typically the list's existing
       * module-scope `sortItems(list, sortKey)`. Omit together with
       * `sortKey` for no sorting.
       */
      sortItems: (list: T[], sortKey: S) => T[];
      /** Current sort key, forwarded to `sortItems`. */
      sortKey: S;
    })
  | (UseArtifactListBaseOptions<T> & {
      sortItems?: undefined;
      sortKey?: undefined;
    });

export interface UseArtifactListResult<T> {
  /** Items after filter + sort (always a fresh array). */
  visible: T[];
  /** `visible` mapped through `toNode`; `[]` when no `toNode` was given. */
  treeNodes: WorkspaceTreeNode[];
  /** id→item lookup for `renderRow` hydration; present iff `getKey` was given. */
  byId?: Map<string, T>;
}

/**
 * Shared key selector — every artifact list entity is keyed by its `id`
 * (UUID or fixture string), so callers pass this instead of a local
 * `(item) => item.id` closure that would change identity every render.
 */
export function artifactId<T extends { id: string }>(item: T): string {
  return item.id;
}

export function useArtifactList<T, S = string>(
  options: UseArtifactListOptions<T, S>,
): UseArtifactListResult<T> {
  const { items, query = '', filter, sortItems, sortKey, toNode, getKey } = options;

  const visible = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = filter ? items.filter((item) => filter(item, normalizedQuery)) : [...items];
    // The options union already couples the pair; the guard is the
    // type-level witness, so no `sortKey as S` assertion is needed.
    return sortItems && sortKey !== undefined ? sortItems(filtered, sortKey) : filtered;
  }, [items, query, filter, sortItems, sortKey]);

  const treeNodes = useMemo(
    () => (toNode ? visible.map((item) => toNode(item)) : EMPTY_TREE_NODES),
    [visible, toNode],
  );

  const byId = useMemo(() => {
    if (!getKey) return undefined;
    const lookup = new Map<string, T>();
    for (const item of visible) lookup.set(getKey(item), item);
    return lookup;
  }, [visible, getKey]);

  return { visible, treeNodes, byId };
}
