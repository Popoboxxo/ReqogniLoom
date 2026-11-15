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
});
