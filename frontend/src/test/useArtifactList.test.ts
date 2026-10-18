/**
 * ARCH-L1-001 ReactFrontend — useArtifactList hook.
 *
 * REUSE finding F-13 (frontend audit 2026-10-15, plan Phase 3a): the shared
 * derivation scaffolding for the editor lists — `visible = filter → sort`,
 * `treeNodes = visible.map(toNode)` and the optional id→item `byId` lookup
 * used by `renderRow`. The tests below pin the pieces the list migrations
 * rely on for zero behavior change:
 *
 *   - the chain equals the previous per-list `useMemo` bodies 1:1
 *     (normalization, filter-then-sort order, filter receiving `''`),
 *   - `treeNodes`/`byId` are optional (IcdList/DiagramList pass no `toNode`,
 *     NeedList passes no `getKey`),
 *   - stable inputs/function identities keep the derived references stable
 *     (the lists virtualize and previous code memoized on the same inputs).
 */

import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { artifactId, useArtifactList } from "../hooks/useArtifactList";
import type { UseArtifactListOptions } from "../hooks/useArtifactList";
import type { WorkspaceTreeNode } from "../components/shared/WorkspaceTree";

interface Item {
  id: string;
  title: string;
  status: string;
}

type ItemSortKey = "default" | "title";

const ITEMS: Item[] = [
  { id: "b", title: "Beta", status: "open" },
  { id: "a", title: "Alpha", status: "done" },
  { id: "c", title: "Gamma", status: "open" },
];

/** Module-scope sorter — mirrors the lists' stable `sortItems` helpers. */
function sortItems(list: Item[], sortKey: ItemSortKey): Item[] {
  const sorted = [...list];
  if (sortKey === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
  return sorted;
}

/** Module-scope node mapper — mirrors `riskToNode`/`adrToNode`/… */
function toNode(item: Item): WorkspaceTreeNode {
  return { id: item.id, name: item.title, parentId: null };
}

describe("useArtifactList", () => {
  it("falls back to a fresh copy of the items when no options beyond `items` are given", () => {
    const { result } = renderHook(() => useArtifactList({ items: ITEMS }));

    expect(result.current.visible).toEqual(ITEMS);
    expect(result.current.visible).not.toBe(ITEMS);
    expect(result.current.treeNodes).toEqual([]);
    expect(result.current.byId).toBeUndefined();
  });

  it("passes the trimmed, lowercased query to `filter` and filters with it", () => {
    const seen: string[] = [];
    const filter = (item: Item, q: string): boolean => {
      seen.push(q);
      return !q || item.title.toLowerCase().includes(q);
    };

    const { result } = renderHook(() =>
      useArtifactList({ items: ITEMS, query: "  BETA ", filter }),
    );

    expect(seen.every((q) => q === "beta")).toBe(true);
    expect(seen).toHaveLength(ITEMS.length);
    expect(result.current.visible.map((i) => i.id)).toEqual(["b"]);
  });

  it("normalizes an empty query to '' (callers keep their `if (q && …)` guard)", () => {
    const filter = vi.fn((_item: Item, _q: string) => true);

    renderHook(() => useArtifactList({ items: ITEMS, query: "   ", filter }));

    expect(filter).toHaveBeenCalledTimes(ITEMS.length);
    expect(filter.mock.calls.every(([, q]) => q === "")).toBe(true);
  });

  it("combines filter and sort: predicate first, then `sortItems(filtered, sortKey)`", () => {
    const filter = (item: Item, q: string): boolean =>
      (!q || item.title.toLowerCase().includes(q)) && item.status === "open";

    const { result } = renderHook(() =>
      useArtifactList({
        items: ITEMS,
        query: "",
        filter,
        sortItems,
        sortKey: "title",
      }),
    );

    // "Beta" and "Gamma" are open; sorted by title.
    expect(result.current.visible.map((i) => i.id)).toEqual(["b", "c"]);
  });

  it("keeps the filtered order when no sortItems is given", () => {
    const filter = (item: Item): boolean => item.status === "open";

    const { result } = renderHook(() =>
      useArtifactList({ items: ITEMS, filter }),
    );

    expect(result.current.visible.map((i) => i.id)).toEqual(["b", "c"]);
  });

  it("returns empty results for empty input — including an empty byId map", () => {
    const { result } = renderHook(() =>
      useArtifactList({ items: [], filter: () => true, toNode, getKey: artifactId }),
    );

    expect(result.current.visible).toEqual([]);
    expect(result.current.treeNodes).toEqual([]);
    expect(result.current.byId).toBeInstanceOf(Map);
    expect(result.current.byId?.size).toBe(0);
  });

  it("returns empty results when the filter matches nothing", () => {
    const filter = () => false;

    const { result } = renderHook(() =>
      useArtifactList({ items: ITEMS, query: "zzz", filter, toNode, getKey: artifactId }),
    );

    expect(result.current.visible).toEqual([]);
    expect(result.current.treeNodes).toEqual([]);
    expect(result.current.byId?.size).toBe(0);
  });

  it("maps treeNodes through toNode in visible order", () => {
    const { result } = renderHook(() =>
      useArtifactList({ items: ITEMS, sortItems, sortKey: "title", toNode }),
    );

    expect(result.current.treeNodes).toEqual([
      { id: "a", name: "Alpha", parentId: null },
      { id: "b", name: "Beta", parentId: null },
      { id: "c", name: "Gamma", parentId: null },
    ]);
  });

  it("builds byId only when getKey is given, keyed over exactly the visible items", () => {
    const withoutKey = renderHook(() =>
      useArtifactList({ items: ITEMS, toNode }),
    );
    expect(withoutKey.result.current.byId).toBeUndefined();

    const filter = (item: Item): boolean => item.status === "open";
    const withKey = renderHook(() =>
      useArtifactList({ items: ITEMS, filter, getKey: artifactId }),
    );

    expect(withKey.result.current.byId).toBeInstanceOf(Map);
    expect([...(withKey.result.current.byId?.keys() ?? [])]).toEqual(["b", "c"]);
    expect(withKey.result.current.byId?.get("b")).toBe(ITEMS[0]);
  });

  it("never passes the original items array to the sorter — with and without a filter", () => {
    const items = [...ITEMS];
    const seenBySorter: Array<Item[]> = [];
    // Spy sorter: records its input so a regression that hands over the
    // caller's array (instead of a fresh `[...items]` / `items.filter(…)`
    // copy) fails loudly (review nit — the previous version asserted only
    // that a copying sorter had copied).
    const spySortItems = (list: Item[], sortKey: ItemSortKey): Item[] => {
      seenBySorter.push(list);
      return sortItems(list, sortKey);
    };

    const noFilter = renderHook(() =>
      useArtifactList({ items, sortItems: spySortItems, sortKey: "title" }),
    );

    const withFilter = renderHook(() =>
      useArtifactList({
        items,
        query: "open",
        filter: (item: Item, q: string): boolean => !q || item.status === q,
        sortItems: spySortItems,
        sortKey: "title",
      }),
    );

    expect(seenBySorter).toHaveLength(2);
    // No-filter path: the hook must copy (`[...items]`) before sorting.
    expect(seenBySorter[0]).not.toBe(items);
    expect(seenBySorter[0].map((i) => i.id)).toEqual(["b", "a", "c"]);
    // Filter path: the sorter sees the filter output, not the input.
    expect(seenBySorter[1]).not.toBe(items);
    expect(seenBySorter[1].map((i) => i.id)).toEqual(["b", "c"]);

    expect(noFilter.result.current.visible.map((i) => i.id)).toEqual(["a", "b", "c"]);
    expect(withFilter.result.current.visible.map((i) => i.id)).toEqual(["b", "c"]);
    // The caller's array is untouched either way.
    expect(items.map((i) => i.id)).toEqual(["b", "a", "c"]);
  });

  // The lists virtualize; the previous per-list `useMemo` blocks kept the
  // derived references stable while inputs and callbacks stayed stable.
  // The hook must reproduce that, or `WorkspaceTree` re-renders on every
  // parent render (e.g. selection clicks).
  it("keeps visible/treeNodes/byId references stable across rerenders with stable inputs", () => {
    const filter = (item: Item, q: string): boolean => !q || item.title.includes(q);
    const initial: UseArtifactListOptions<Item, ItemSortKey> = {
      items: ITEMS,
      query: "",
      filter,
      sortItems,
      sortKey: "title",
      toNode,
      getKey: artifactId,
    };

    const { result, rerender } = renderHook(
      (props: UseArtifactListOptions<Item, ItemSortKey>) => useArtifactList(props),
      { initialProps: initial },
    );

    const first = result.current;
    // A new options object with identical values — the memo deps are the
    // individual fields, not the object.
    rerender({ ...initial });

    expect(result.current.visible).toBe(first.visible);
    expect(result.current.treeNodes).toBe(first.treeNodes);
    expect(result.current.byId).toBe(first.byId);
  });

  it("recomputes when the sort key changes", () => {
    const { result, rerender } = renderHook(
      (props: UseArtifactListOptions<Item, ItemSortKey>) => useArtifactList(props),
      { initialProps: { items: ITEMS, sortItems, sortKey: "default" } },
    );

    expect(result.current.visible.map((i) => i.id)).toEqual(["b", "a", "c"]);

    rerender({ items: ITEMS, sortItems, sortKey: "title" });
    expect(result.current.visible.map((i) => i.id)).toEqual(["a", "b", "c"]);
  });
});
