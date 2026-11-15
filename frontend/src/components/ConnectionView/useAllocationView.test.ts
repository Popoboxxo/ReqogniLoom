/**
 * P3 Task 3.2 — URL <-> filter mapping.
 *
 * These are the pure halves of `useAllocationView`: every filter must reach
 * the backend query, and a URL must round-trip losslessly (bookmark, reload,
 * renderer switch).
 */

import { describe, expect, it } from "vitest";

import {
  CONNECTION_VIEW_MODES,
  DEFAULT_CONNECTION_VIEW,
  DEFAULT_PAGE_SIZE,
  SERVER_PAGE_SIZE,
  buildConnectionSearch,
  elementFiltersToQuery,
  filtersToQuery,
  parseConnectionSearch,
  parseConnectionView,
  type ConnectionFilters,
} from "./useAllocationView";

const FULL_FILTERS: ConnectionFilters = {
  allocated: false,
  open: true,
  locked: true,
  hasFindings: true,
  intent: "unassigned",
  tier: "tier-first",
  type: "SyReq",
  category: "functional",
  state: "draft",
  elementSubtree: "element-1",
  q: "bremse",
  group: "group-1",
  page: 3,
  pageSize: 25,
};

describe("filtersToQuery", () => {
  it("maps every server-supported filter to a query parameter", () => {
    const query = filtersToQuery(FULL_FILTERS);
    expect(query).toEqual({
      allocated: false,
      open: true,
      intent: "unassigned",
      tier: "tier-first",
      type: "SyReq",
      category: "functional",
      state: "draft",
      element_subtree: "element-1",
      q: "bremse",
      page_size: SERVER_PAGE_SIZE,
      offset: 0,
    });
  });

  it("keeps the two UI-only quick filters out of the request", () => {
    const query = filtersToQuery(FULL_FILTERS);
    expect(query).not.toHaveProperty("locked");
    expect(query).not.toHaveProperty("has_findings");
    // P6: group membership is a client-side join, not a server filter.
    expect(query).not.toHaveProperty("group");
    expect(query).not.toHaveProperty("page");
    expect(query).not.toHaveProperty("page_size_client");
  });

  it("uses the committable default windows", () => {
    expect(filtersToQuery({ page: 1, pageSize: DEFAULT_PAGE_SIZE })).toEqual({
      page_size: SERVER_PAGE_SIZE,
      offset: 0,
    });
  });
});

describe("elementFiltersToQuery (V2/B-4)", () => {
  it("forwards the filters an element row can answer", () => {
    expect(elementFiltersToQuery(FULL_FILTERS)).toEqual({
      type: "SyReq",
      state: "draft",
      element_subtree: "element-1",
      q: "bremse",
      page_size: SERVER_PAGE_SIZE,
      offset: 0,
    });
  });

  it("never forwards the requirement-state filters that empty the element column", () => {
    const query = elementFiltersToQuery(FULL_FILTERS);
    expect(query).not.toHaveProperty("allocated");
    expect(query).not.toHaveProperty("open");
    expect(query).not.toHaveProperty("intent");
    expect(query).not.toHaveProperty("category");
    // Element rows are built with `tier_key: None`, so a tier filter would
    // empty the column just like the allocation-state filters.
    expect(query).not.toHaveProperty("tier");
  });

  it("keeps the UI-only and client-side filters out of the request", () => {
    const query = elementFiltersToQuery(FULL_FILTERS);
    expect(query).not.toHaveProperty("locked");
    expect(query).not.toHaveProperty("has_findings");
    expect(query).not.toHaveProperty("group");
    expect(query).not.toHaveProperty("kind");
  });

  it.each<[string, Partial<ConnectionFilters>]>([
    ["type", { type: "component" }],
    ["state", { state: "approved" }],
    ["element_subtree", { elementSubtree: "element-1" }],
    ["q", { q: "bremse" }],
  ])("forwards %s when it is the only active filter", (key, patch) => {
    const query = elementFiltersToQuery({ page: 1, pageSize: 25, ...patch });
    expect(Object.keys(query).sort()).toEqual(
      ["offset", "page_size", key].sort()
    );
  });

  it("uses the committed server window", () => {
    expect(elementFiltersToQuery({ page: 3, pageSize: 25 })).toEqual({
      page_size: SERVER_PAGE_SIZE,
      offset: 0,
    });
  });
});

describe("URL round-trip", () => {
  it("parses an empty URL to the documented defaults", () => {
    expect(parseConnectionSearch(new URLSearchParams())).toEqual({
      allocated: undefined,
      open: undefined,
      locked: undefined,
      hasFindings: undefined,
      intent: undefined,
      tier: undefined,
      type: undefined,
      category: undefined,
      state: undefined,
      elementSubtree: undefined,
      q: undefined,
      group: undefined,
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
    });
  });

  it("survives build -> parse -> build unchanged", () => {
    const first = buildConnectionSearch(FULL_FILTERS);
    const parsed = parseConnectionSearch(first);
    const second = buildConnectionSearch(parsed);

    expect(parsed).toEqual(FULL_FILTERS);
    expect(second.toString()).toBe(first.toString());
  });

  it("distinguishes the two allocated states from 'no filter'", () => {
    const onlyAllocated = buildConnectionSearch({
      allocated: true,
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
    });
    const onlyUnallocated = buildConnectionSearch({
      allocated: false,
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
    });

    expect(onlyAllocated.get("allocated")).toBe("true");
    expect(onlyUnallocated.get("allocated")).toBe("false");
    expect(parseConnectionSearch(onlyUnallocated).allocated).toBe(false);
  });
});

describe("parseConnectionView", () => {
  it("default_mode_matches_decision", () => {
    // S0 decision D4/O5 = option (a): a URL without `view` opens `trees`.
    expect(parseConnectionView(new URLSearchParams())).toBe("trees");
    expect(parseConnectionView(new URLSearchParams("q=bremse"))).toBe("trees");
    expect(DEFAULT_CONNECTION_VIEW).toBe("trees");
    expect(CONNECTION_VIEW_MODES[0]).toBe("trees");
    // Exactly the five renderers of the spec's mode set (S3).
    expect([...CONNECTION_VIEW_MODES].sort()).toEqual(
      ["architecture", "graph", "matrix", "trees", "two-column"].sort()
    );
  });

  it("tree_alias_opens_architecture", () => {
    // `tree` is the pre-V.5 name: saved views and bookmarks carry it.
    expect(parseConnectionView(new URLSearchParams("view=tree"))).toBe(
      "architecture"
    );
    expect(parseConnectionView(new URLSearchParams("view=architecture"))).toBe(
      "architecture"
    );
    // An unknown mode is not a mode: it falls back to the default.
    expect(parseConnectionView(new URLSearchParams("view=unknown"))).toBe(
      "trees"
    );
  });

  it("two_column_is_unchanged", () => {
    expect(parseConnectionView(new URLSearchParams("view=two-column"))).toBe(
      "two-column"
    );
    expect(parseConnectionView(new URLSearchParams("view=matrix"))).toBe(
      "matrix"
    );
    expect(parseConnectionView(new URLSearchParams("view=graph"))).toBe("graph");
    expect(parseConnectionView(new URLSearchParams("view=trees"))).toBe("trees");
    // V.5 (spec §5.8.8): the two-column URL keeps its filters untouched.
    expect(
      parseConnectionView(
        new URLSearchParams("view=two-column&q=bremse&allocated=false")
      )
    ).toBe("two-column");
  });

  it("saved_view_with_old_params_still_works", () => {
    // A saved view is a URL snapshot; the alias decides what it opens.
    const saved = new URLSearchParams("view=tree&q=bremse&allocated=false");
    expect(parseConnectionView(saved)).toBe("architecture");
    expect(parseConnectionSearch(saved).q).toBe("bremse");
    expect(parseConnectionSearch(saved).allocated).toBe(false);
  });
});
