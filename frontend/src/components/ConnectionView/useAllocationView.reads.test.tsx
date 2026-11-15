/**
 * V2 Task V2.3 (B-3) — the connection view reads requirements and elements
 * separately.
 *
 * The read object now takes a `kind` filter, so the hook issues two targeted
 * reads instead of two full loads. The element column depends exclusively on
 * the element read: the requirement page carries no element rows and must not
 * be used as a fallback.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type {
  AllocationRow,
  AllocationViewQuery,
  AllocationViewResponse,
} from "../../api/allocation-view";
import { allocationViewApi } from "../../api/allocation-view";
import { loadGroupsWithMembers } from "../../api/groups";
import {
  filtersToQuery,
  buildConnectionSearch,
  useAllocationView,
  type ConnectionFilters,
} from "./useAllocationView";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "T", preset: "standard" },
  }),
}));

vi.mock("../../api/allocation-view", () => ({
  allocationViewApi: {
    view: vi.fn(),
    tiers: vi.fn(),
    bulkAllocate: vi.fn(),
    deallocate: vi.fn(),
    suggestArchitecture: vi.fn(),
  },
}));

vi.mock("../../api/groups", () => ({
  loadGroupsWithMembers: vi.fn(),
}));

const mockedView = vi.mocked(allocationViewApi.view);

function row(overrides: Partial<AllocationRow>): AllocationRow {
  return {
    kind: "requirement",
    id: "r1",
    artifact_id: "art-r1",
    parent_id: null,
    sort_key: "a",
    title: "Bremsen",
    state: "draft",
    tier_key: null,
    tier_name: null,
    level: 1,
    type: "SyReq",
    category: "functional",
    allocated_to: null,
    allocation_trace_link_id: null,
    element_id: null,
    allocation_intent: "unassigned",
    locked: null,
    findings: [],
    group: null,
    ...overrides,
  };
}

function elementRow(id: string, title: string, sortKey = "a"): AllocationRow {
  return row({
    kind: "element",
    id,
    artifact_id: `art-${id}`,
    title,
    sort_key: sortKey,
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
  });
}

function response(results: AllocationRow[]): AllocationViewResponse {
  return {
    results,
    meta: {
      total: 4,
      unallocated: 2,
      locked: 0,
      findings: 0,
      page_size: 500,
      offset: 0,
    },
  };
}

function wrapper(initialPath = "/connections") {
  return function Wrapper({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(loadGroupsWithMembers).mockResolvedValue([]);
});

/** The query the hook handed to the read of one row kind. */
function queryForKind(kind: "requirement" | "element"): AllocationViewQuery {
  const call = mockedView.mock.calls.find(([, query]) => query?.kind === kind);
  if (!call) throw new Error(`no ${kind} read was issued`);
  return call[1] ?? {};
}

function resultForKind(query: AllocationViewQuery): AllocationViewResponse {
  // Simulate the server: `kind` narrows the page, meta stays global.
  if (query.kind === "requirement") {
    return response([
      row({ id: "r1", title: "Bremsen" }),
      row({ id: "r2", title: "Lenken", sort_key: "b" }),
    ]);
  }
  if (query.kind === "element") {
    return response([
      elementRow("e1", "Bremse"),
      elementRow("e2", "Lenkung", "b"),
    ]);
  }
  return response([
    row({ id: "r1", title: "Bremsen" }),
    row({ id: "r2", title: "Lenken", sort_key: "b" }),
    elementRow("e1", "Bremse"),
    elementRow("e2", "Lenkung", "b"),
  ]);
}

describe("useAllocationView — targeted element read (V2/B-3)", () => {
  it("elements_come_only_from_the_element_read", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) => {
      // The requirement read deliberately leaks an element row (legacy shape);
      // it must not show up in the element column.
      if (query.kind === "requirement") {
        return response([row({ id: "r1" }), elementRow("ghost", "Ghost")]);
      }
      return resultForKind(query);
    });

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.elements).toHaveLength(2));

    expect(result.current.elements.map((item) => item.id)).toEqual(["e1", "e2"]);
    expect(result.current.requirements.map((item) => item.id)).toEqual(["r1"]);
  });

  it("no_element_rows_when_element_read_is_empty", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) => {
      if (query.kind === "element") return response([]);
      if (query.kind === "requirement") {
        return response([row({ id: "r1" }), elementRow("ghost", "Ghost")]);
      }
      return resultForKind(query);
    });

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(mockedView).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.requirements).toHaveLength(1));

    // No fallback to the requirement page: the column stays empty.
    expect(result.current.elements).toEqual([]);
  });

  it("issues one targeted read per kind", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) =>
      resultForKind(query)
    );

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.elements).toHaveLength(2));

    const kinds = mockedView.mock.calls.map(([, query]) => query?.kind);
    expect(kinds).toEqual(expect.arrayContaining(["requirement", "element"]));
    expect(kinds).toHaveLength(2);
    // Both reads take the full page: the 500 cap applies per kind.
    for (const [, query] of mockedView.mock.calls) {
      expect(query?.page_size).toBe(500);
    }
  });

  it("element_subtree_restricts_elements", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) =>
      resultForKind(query)
    );

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper("/connections?element_subtree=element-1"),
    });

    await waitFor(() => expect(result.current.elements).toHaveLength(2));

    const elementCall = mockedView.mock.calls.find(
      ([, query]) => query?.kind === "element"
    );
    expect(elementCall?.[1].element_subtree).toBe("element-1");
    const requirementCall = mockedView.mock.calls.find(
      ([, query]) => query?.kind === "requirement"
    );
    expect(requirementCall?.[1].element_subtree).toBe("element-1");
  });

  it("url_has_no_kind_parameter", () => {
    const filters: ConnectionFilters = {
      allocated: false,
      elementSubtree: "element-1",
      q: "bremse",
      page: 1,
      pageSize: 25,
    };

    const params = buildConnectionSearch(filters);
    expect(params.has("kind")).toBe(false);
    expect(filtersToQuery(filters)).not.toHaveProperty("kind");
    expect(filtersToQuery(filters)).not.toHaveProperty("view");
  });

  it("element_query_omits_requirement_state_filters", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) =>
      resultForKind(query)
    );

    renderHook(() => useAllocationView(), {
      wrapper: wrapper(
        "/connections?allocated=false&open=true&intent=unassigned&category=functional&tier=tier-first&element_subtree=element-1&q=bremse"
      ),
    });

    await waitFor(() => expect(mockedView).toHaveBeenCalledTimes(2));

    const elementQuery = queryForKind("element");
    // An element row is never allocated, never "open" and carries no tier, so
    // the server would drop every element row (V2/B-4) and the column would go
    // empty.
    expect(elementQuery).not.toHaveProperty("allocated");
    expect(elementQuery).not.toHaveProperty("open");
    expect(elementQuery).not.toHaveProperty("intent");
    expect(elementQuery).not.toHaveProperty("category");
    expect(elementQuery).not.toHaveProperty("tier");
    // The element-relevant filters still apply.
    expect(elementQuery.element_subtree).toBe("element-1");
    expect(elementQuery.q).toBe("bremse");
  });

  it("element_query_keeps_kind_element", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) =>
      resultForKind(query)
    );

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper("/connections?allocated=false"),
    });

    await waitFor(() => expect(result.current.elements).toHaveLength(2));

    const elementQuery = queryForKind("element");
    expect(elementQuery.kind).toBe("element");
    expect(elementQuery.page_size).toBe(500);
    expect(elementQuery.offset).toBe(0);
  });

  it("requirement_query_keeps_its_filters", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) =>
      resultForKind(query)
    );

    renderHook(() => useAllocationView(), {
      wrapper: wrapper(
        "/connections?allocated=false&open=true&intent=unassigned&category=functional&element_subtree=element-1&q=bremse"
      ),
    });

    await waitFor(() => expect(mockedView).toHaveBeenCalledTimes(2));

    const requirementQuery = queryForKind("requirement");
    expect(requirementQuery.allocated).toBe(false);
    expect(requirementQuery.open).toBe(true);
    expect(requirementQuery.intent).toBe("unassigned");
    expect(requirementQuery.category).toBe("functional");
    expect(requirementQuery.element_subtree).toBe("element-1");
    expect(requirementQuery.q).toBe("bremse");
    expect(requirementQuery.kind).toBe("requirement");
  });
});

describe("useAllocationView — element read error/loading (V2 follow-up)", () => {
  it("hook_reports_error_when_elements_query_fails", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) => {
      if (query.kind === "element") throw new Error("element read down");
      return resultForKind(query);
    });

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper(),
    });

    await waitFor(() =>
      expect(result.current.elementsError?.message).toBe("element read down")
    );

    // The requirement read succeeded, so no requirement rows are lost.
    expect(result.current.requirements).toHaveLength(2);
    // …but the failure is not swallowed by the aggregate error surface.
    expect(result.current.error?.message).toBe("element read down");
  });

  it("elements_loading_is_exposed_separately", async () => {
    let resolveElements:
      | ((value: AllocationViewResponse) => void)
      | undefined;
    mockedView.mockImplementation(async (_workspace, query = {}) => {
      if (query.kind === "element") {
        return new Promise<AllocationViewResponse>((resolve) => {
          resolveElements = resolve;
        });
      }
      return resultForKind(query);
    });

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper(),
    });

    // Requirements are in, the element read is still pending.
    await waitFor(() => expect(result.current.requirements).toHaveLength(2));
    expect(result.current.elementsLoading).toBe(true);
    expect(result.current.isLoading).toBe(true);

    resolveElements?.(resultForKind({ kind: "element" }));

    await waitFor(() => expect(result.current.elementsLoading).toBe(false));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.elements).toHaveLength(2);
    expect(result.current.elementsError).toBeNull();
  });

  it("requirements_error_is_unchanged", async () => {
    mockedView.mockImplementation(async (_workspace, query = {}) => {
      if (query.kind === "requirement") throw new Error("rows read down");
      return resultForKind(query);
    });

    const { result } = renderHook(() => useAllocationView(), {
      wrapper: wrapper(),
    });

    await waitFor(() =>
      expect(result.current.error?.message).toBe("rows read down")
    );
    expect(result.current.elementsError).toBeNull();
    // The element read still delivers its rows.
    expect(result.current.elements).toHaveLength(2);
  });
});

