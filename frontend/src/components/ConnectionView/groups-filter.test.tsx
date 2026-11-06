/**
 * P6 Task 6.3 — the connection view's `group` filter.
 *
 * The committed allocation read object has no group parameter, so the filter
 * is a client-side join over the fetched membership. These tests exercise that
 * join and the card field "group", which is filled from the same membership
 * data where the backend does not populate it.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AllocationRow } from "../../api/allocation-view";
import { allocationViewApi } from "../../api/allocation-view";
import { connectionViewsApi } from "../../api/connection-views";
import {
  loadGroupsWithMembers,
  type GroupWithMembers,
} from "../../api/groups";
import { preferenceValuesApi } from "../../api/preference-values";
import { ConnectionView } from "./ConnectionView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: string | Record<string, unknown>) =>
      typeof options === "string" ? options : key,
  }),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["editor"] }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "T", preset: "standard" },
  }),
}));

vi.mock("@xyflow/react", async () =>
  (await import("../../test/xyflow-stub")).createXyflowStub()
);

vi.mock("../../api/groups", () => ({
  loadGroupsWithMembers: vi.fn(),
  groupsApi: {
    list: vi.fn(),
    create: vi.fn(),
    members: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
    moveMember: vi.fn(),
  },
}));

vi.mock("../../api/preference-values", () => ({
  preferenceValuesApi: {
    effective: vi.fn(),
    patchLevel: vi.fn(),
    getLevel: vi.fn(),
  },
}));

vi.mock("../../api/allocation-view", () => ({
  allocationViewApi: {
    view: vi.fn(),
    tiers: vi.fn(),
    bulkAllocate: vi.fn(),
    deallocate: vi.fn(),
  },
}));

vi.mock("../../api/connection-views", () => ({
  connectionViewsApi: {
    load: vi.fn(),
    save: vi.fn(),
  },
}));

function requirement(overrides: Partial<AllocationRow>): AllocationRow {
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

const RESPONSE = {
  results: [
    requirement({ id: "r1", title: "Bremsen", artifact_id: "art-r1" }),
    requirement({
      id: "r2",
      title: "Lenken",
      artifact_id: "art-r2",
      sort_key: "b",
    }),
  ],
  meta: { total: 2, unallocated: 2, locked: 0, findings: 0, page_size: 500, offset: 0 },
};

const GROUPS: GroupWithMembers[] = [
  {
    id: "g1",
    workspace_id: "ws-1",
    title: "Bremssystem",
    description: "",
    members: [
      {
        trace_link_id: "tl-1",
        requirement_artifact_id: "art-r1",
        sort_key: "a",
      },
    ],
  },
];

/** Card-field preference that makes the `group` field visible on requirement cards. */
const CARD_FIELD_PREFERENCE = {
  "ui.allocation_graph.card_fields": {
    value: [
      JSON.stringify({
        kind: "requirement",
        fields: [
          { key: "title", visible: true },
          { key: "group", visible: true },
          { key: "lock", visible: true },
        ],
        rows: 2,
      }),
      JSON.stringify({
        kind: "element",
        fields: [
          { key: "title", visible: true },
          { key: "lock", visible: true },
        ],
        rows: 2,
      }),
    ],
  },
};

function renderView(initialPath = "/connections"): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ConnectionView />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.mocked(allocationViewApi.view).mockResolvedValue(RESPONSE);
  vi.mocked(allocationViewApi.tiers).mockResolvedValue({
    workspace_id: "ws-1",
    tiers: [],
  });
  vi.mocked(connectionViewsApi.load).mockResolvedValue([]);
  vi.mocked(connectionViewsApi.save).mockResolvedValue(undefined);
  vi.mocked(loadGroupsWithMembers).mockResolvedValue(GROUPS);
  vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
    workspace_id: "ws-1",
    values: {},
  } as never);
});

describe("ConnectionView — group filter (P6 Task 6.3)", () => {
  it("offers the workspace's groups and filters the rows by membership", async () => {
    renderView();
    await screen.findByTestId("tree-renderer");

    const select = await screen.findByTestId("filter-group");
    expect(select).toHaveTextContent("Bremssystem");

    await waitFor(() =>
      expect(screen.getByTestId("req-row-r2")).toBeInTheDocument()
    );

    fireEvent.change(select, { target: { value: "g1" } });

    await waitFor(() =>
      expect(screen.queryByTestId("req-row-r2")).not.toBeInTheDocument()
    );
    expect(screen.getByTestId("req-row-r1")).toBeInTheDocument();
  });

  it("hides the filter when the workspace has no groups", async () => {
    vi.mocked(loadGroupsWithMembers).mockResolvedValue([]);
    renderView();
    await screen.findByTestId("tree-renderer");
    expect(screen.queryByTestId("filter-group")).toBeNull();
  });

  it("shows the group name in the allocation card's group field", async () => {
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: CARD_FIELD_PREFERENCE,
    } as never);

    renderView();
    fireEvent.click(await screen.findByTestId("view-switch-graph"));

    await waitFor(() => {
      const fields = screen.getAllByTestId("card-field-group");
      expect(
        fields.some((field) => field.textContent?.includes("Bremssystem"))
      ).toBe(true);
    });
  });
});
