/**
 * P3 Task 3.2 — URL <-> filter mapping.
 *
 * These are the pure halves of `useAllocationView`: every filter must reach
 * the backend query, and a URL must round-trip losslessly (bookmark, reload,
 * renderer switch).
 */

import { describe, expect, it } from "vitest";

import {
  DEFAULT_PAGE_SIZE,
  SERVER_PAGE_SIZE,
  buildConnectionSearch,
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
  it("defaults to the tree and only accepts the four known renderers", () => {
    expect(parseConnectionView(new URLSearchParams())).toBe("tree");
    expect(parseConnectionView(new URLSearchParams("view=matrix"))).toBe("matrix");
    expect(parseConnectionView(new URLSearchParams("view=two-column"))).toBe(
      "two-column"
    );
    expect(parseConnectionView(new URLSearchParams("view=graph"))).toBe("graph");
    expect(parseConnectionView(new URLSearchParams("view=unknown"))).toBe("tree");
  });
});
