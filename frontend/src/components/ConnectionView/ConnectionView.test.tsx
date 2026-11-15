/**
 * P3 Task 3.2 — connection view shell.
 *
 * Verifies that filters are URL state, that switching the renderer preserves
 * them, that a reloaded URL restores them, and that saved views create/apply
 * through the preference-backed saved-view API.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import { allocationViewApi } from "../../api/allocation-view";
import {
  connectionViewsApi,
  loadFiltersExpanded,
  loadShowEdges,
  saveFiltersExpanded,
  saveShowEdges,
} from "../../api/connection-views";
import { loadGroupsWithMembers } from "../../api/groups";
import { preferenceValuesApi } from "../../api/preference-values";
import { ConnectionView } from "./ConnectionView";

vi.mock("react-i18next", () => {
  function lookup(key: string): string | undefined {
    const value = key
      .split(".")
      .reduce<unknown>(
        (node, segment) =>
          node && typeof node === "object"
            ? (node as Record<string, unknown>)[segment]
            : undefined,
        de
      );
    return typeof value === "string" ? value : undefined;
  }
  return {
    useTranslation: () => ({
      t: (key: string, options?: Record<string, unknown>) => {
        const template = lookup(key) ?? key;
        if (!options) return template;
        return Object.entries(options).reduce(
          (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
          template
        );
      },
    }),
  };
});

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["editor"] }),
}));

vi.mock("@xyflow/react", async () =>
  (await import("../../test/xyflow-stub")).createXyflowStub()
);

vi.mock("../../api/preference-values", () => ({
  preferenceValuesApi: {
    effective: vi.fn(),
    patchLevel: vi.fn(),
    getLevel: vi.fn(),
  },
}));

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

// P6 Task 6.3: the connection view loads group membership for the `group`
// filter and the card's group field. These tests do not exercise groups, so
// the read answers an empty list; the filter itself is covered by
// `groups-filter.test.tsx`.
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

vi.mock("../../api/connection-views", () => ({
  connectionViewsApi: {
    load: vi.fn(),
    save: vi.fn(),
  },
  // V.4: the "Weitere Filter" popover state is a user preference.
  loadFiltersExpanded: vi.fn(),
  saveFiltersExpanded: vi.fn(),
  loadShowEdges: vi.fn(),
  saveShowEdges: vi.fn(),
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

function element(id: string, title: string): AllocationRow {
  return requirement({
    kind: "element",
    id,
    artifact_id: `art-${id}`,
    title,
    state: null,
    level: null,
    type: "component",
    category: null,
    allocation_intent: null,
  });
}

const RESPONSE = {
  results: [
    requirement({ id: "r1", title: "Bremsen" }),
    // Distinct artifact ids: the tree de-duplicates by Artifact id, and two
    // requirements never share one.
    requirement({
      id: "r2",
      title: "Lenken",
      sort_key: "b",
      artifact_id: "art-r2",
    }),
    element("e1", "Bremse"),
    element("e2", "Lenkung"),
  ],
  meta: { total: 4, unallocated: 2, locked: 0, findings: 0, page_size: 500, offset: 0 },
};

function fakeDataTransfer(): {
  setData: (key: string, value: string) => void;
  getData: (key: string) => string;
  effectAllowed: string;
} {
  const store: Record<string, string> = {};
  return {
    setData: (key: string, value: string) => {
      store[key] = value;
    },
    getData: (key: string) => store[key] ?? "",
    effectAllowed: "",
  };
}

function renderView(initialPath = "/connections"): void {  const queryClient = new QueryClient({
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

/**
 * V.4: the free filters and the saved views live in the "Weitere Filter"
 * popover. Let the preference read settle first, then expand it — clicking
 * before the read resolves could be undone by the async `false`.
 */
async function openMoreFilters(): Promise<void> {
  await waitFor(() => expect(loadFiltersExpanded).toHaveBeenCalled());
  fireEvent.click(screen.getByTestId("filter-more-toggle"));
  await screen.findByTestId("filter-more");
}

beforeEach(() => {
  vi.mocked(allocationViewApi.view).mockResolvedValue(RESPONSE);
  vi.mocked(allocationViewApi.tiers).mockResolvedValue({
    workspace_id: "ws-1",
    tiers: [],
  });
  vi.mocked(allocationViewApi.bulkAllocate).mockResolvedValue({
    allocated: [],
  });
  vi.mocked(allocationViewApi.deallocate).mockResolvedValue(undefined);
  vi.mocked(connectionViewsApi.load).mockResolvedValue([]);
  vi.mocked(loadGroupsWithMembers).mockResolvedValue([]);
  vi.mocked(connectionViewsApi.save).mockResolvedValue(undefined);
  vi.mocked(loadFiltersExpanded).mockResolvedValue(false);
  vi.mocked(saveFiltersExpanded).mockResolvedValue(undefined);
  // V.5: the edge overlay switch is a user preference (default on).
  vi.mocked(loadShowEdges).mockResolvedValue(true);
  vi.mocked(saveShowEdges).mockResolvedValue(undefined);
  vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
    workspace_id: "ws-1",
    values: {},
  });
});

describe("ConnectionView — filters are URL state", () => {
  it("pushes a changed filter into the request query", async () => {
    renderView();
    fireEvent.change(screen.getByTestId("filter-q"), {
      target: { value: "bremse" },
    });

    await waitFor(() =>
      expect(allocationViewApi.view).toHaveBeenLastCalledWith(
        "ws-1",
        expect.objectContaining({ q: "bremse" })
      )
    );
  });

  it("keeps the filters when the renderer is switched", async () => {
    renderView();
    fireEvent.change(screen.getByTestId("filter-q"), {
      target: { value: "bremse" },
    });
    fireEvent.click(screen.getByTestId("quick-unallocated"));

    fireEvent.click(screen.getByTestId("view-switch-matrix"));

    expect(await screen.findByTestId("matrix-renderer")).toBeInTheDocument();
    expect(screen.getByTestId("filter-q")).toHaveValue("bremse");
    expect(screen.getByTestId("quick-unallocated")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("view-switch-matrix")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(allocationViewApi.view).toHaveBeenLastCalledWith(
      "ws-1",
      expect.objectContaining({ q: "bremse", allocated: false })
    );
  });

  it("offers the card graph as the fifth renderer and keeps the filters", async () => {
    renderView();
    fireEvent.change(screen.getByTestId("filter-q"), {
      target: { value: "bremse" },
    });

    fireEvent.click(screen.getByTestId("view-switch-graph"));

    expect(await screen.findByTestId("allocation-graph")).toBeInTheDocument();
    expect(screen.getByTestId("view-switch-graph")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("filter-q")).toHaveValue("bremse");
    expect(allocationViewApi.view).toHaveBeenLastCalledWith(
      "ws-1",
      expect.objectContaining({ q: "bremse" })
    );
  });

  it("restores filters and the renderer from the URL on load", async () => {
    renderView("/connections?q=bremse&allocated=false&view=two-column");

    expect(await screen.findByTestId("two-column-renderer")).toBeInTheDocument();
    expect(screen.getByTestId("filter-q")).toHaveValue("bremse");
    expect(screen.getByTestId("quick-unallocated")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });

  it("renders the counters from the read object's meta", async () => {
    renderView();
    await waitFor(() =>
      expect(screen.getByTestId("counter-total")).toHaveTextContent("4")
    );
    expect(screen.getByTestId("counter-unallocated")).toHaveTextContent("2");
    expect(screen.getByTestId("counter-locked")).toHaveTextContent("0");
    expect(screen.getByTestId("counter-findings")).toHaveTextContent("0");
  });
});

describe("ConnectionView — default mode, alias and the edge switch (V.5)", () => {
  it("default_mode_matches_decision", async () => {
    renderView();

    // S0 = option (a): a URL without `view` opens the two trees.
    expect(
      await screen.findByTestId("allocation-trees-renderer")
    ).toBeInTheDocument();
    expect(screen.getByTestId("view-switch-trees")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("view-switch-architecture")).toHaveAttribute(
      "aria-pressed",
      "false"
    );

    // V.4: the assistant is presentational — the tree checkboxes are the one
    // selection, the action bar only reads it.
    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "0 ausgewählt"
    );
    expect(screen.queryByTestId("assistant-check-r1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-row-r1")).not.toBeInTheDocument();
  });

  it("tree_alias_opens_architecture", async () => {
    // Saved views written before V.5 carry `view=tree`.
    renderView("/connections?view=tree");

    expect(await screen.findByTestId("tree-renderer")).toBeInTheDocument();
    expect(
      screen.queryByTestId("allocation-trees-renderer")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("view-switch-architecture")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });

  it("five_switch_entries", async () => {
    renderView();
    await screen.findByTestId("allocation-trees-renderer");

    for (const mode of [
      "trees",
      "architecture",
      "two-column",
      "matrix",
      "graph",
    ]) {
      expect(screen.getByTestId(`view-switch-${mode}`)).toBeInTheDocument();
    }
    // The pre-V.5 test id is gone — `tree` is not a mode any more.
    expect(screen.queryByTestId("view-switch-tree")).not.toBeInTheDocument();

    const group = screen.getByRole("group", { name: "Ansicht wechseln" });
    expect(within(group).getAllByRole("button")).toHaveLength(5);
  });

  it("show_edges_preference_persists_across_mode_switch", async () => {
    renderView();
    await screen.findByTestId("allocation-trees-renderer");

    const toggle = await screen.findByTestId("connection-view-show-edges");
    await waitFor(() => expect(toggle).toBeChecked());

    fireEvent.click(toggle);
    await waitFor(() => expect(saveShowEdges).toHaveBeenCalledWith(false));
    expect(toggle).not.toBeChecked();

    // Switch away and back: the state is page state and was persisted, so the
    // switch comes back off instead of resetting to the default.
    fireEvent.click(screen.getByTestId("view-switch-matrix"));
    await screen.findByTestId("matrix-renderer");
    fireEvent.click(screen.getByTestId("view-switch-trees"));
    await screen.findByTestId("allocation-trees-renderer");

    expect(screen.getByTestId("connection-view-show-edges")).not.toBeChecked();
    expect(saveShowEdges).toHaveBeenCalledTimes(1);
  });

  it("show_edges_off_hides_overlay_keeps_target_text", async () => {
    vi.mocked(allocationViewApi.view).mockResolvedValue({
      ...RESPONSE,
      results: [
        requirement({
          id: "r1",
          title: "Bremsen",
          allocated_to: "art-e1",
          element_id: "e1",
          allocation_trace_link_id: "link-1",
        }),
        element("e1", "Bremse"),
        element("e2", "Lenkung"),
      ],
    });
    vi.mocked(loadShowEdges).mockResolvedValue(false);

    renderView();
    expect(
      await screen.findByTestId("allocation-trees-renderer")
    ).toBeInTheDocument();

    // Spec §5.8.13: no overlay …
    await waitFor(() =>
      expect(screen.queryByTestId("allocation-edges")).not.toBeInTheDocument()
    );
    // … but the target text on the row stays.
    expect(screen.getByTestId("alloc-target-r1")).toHaveTextContent("Bremse");
  });

  it("saved_view_with_old_params_still_works", async () => {
    // A saved view is a URL snapshot; `view=tree` still opens `Architektur`.
    renderView("/connections?q=bremse&allocated=false&view=tree");

    expect(await screen.findByTestId("tree-renderer")).toBeInTheDocument();
    expect(screen.getByTestId("view-switch-architecture")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("filter-q")).toHaveValue("bremse");
    expect(screen.getByTestId("quick-unallocated")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });
});

describe("ConnectionView — writes go through the atomic bulk endpoint", () => {
  it("allocates a dragged requirement via POST /trace-links/bulk/", async () => {
    // `Architektur` is a mode of its own since V.5, so the flow opts in.
    renderView("/connections?view=architecture");
    await screen.findByTestId("tree-renderer");

    const dataTransfer = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("req-row-r1"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("element-node-e2"), { dataTransfer });

    await waitFor(() =>
      expect(allocationViewApi.bulkAllocate).toHaveBeenCalledWith([
        { requirement_id: "r1", element_id: "e2" },
      ])
    );
  });
});

describe("ConnectionView — saved views", () => {  it("creates a saved view from the current filters and reapplies it", async () => {
    renderView();
    await openMoreFilters();

    fireEvent.change(screen.getByTestId("filter-q"), {
      target: { value: "bremse" },
    });
    fireEvent.change(screen.getByTestId("saved-view-name"), {
      target: { value: "Meine Sicht" },
    });
    fireEvent.click(screen.getByTestId("saved-view-save"));

    await waitFor(() => expect(connectionViewsApi.save).toHaveBeenCalled());
    const saved = vi.mocked(connectionViewsApi.save).mock.calls[0][0];
    expect(saved).toHaveLength(1);
    expect(saved[0].name).toBe("Meine Sicht");
    expect(saved[0].params.q).toBe("bremse");

    // Clear the filter, then re-apply the saved view.
    fireEvent.change(screen.getByTestId("filter-q"), {
      target: { value: "" },
    });
    await waitFor(() => expect(screen.getByTestId("filter-q")).toHaveValue(""));

    fireEvent.click(await screen.findByText("Meine Sicht"));
    await waitFor(() =>
      expect(screen.getByTestId("filter-q")).toHaveValue("bremse")
    );
  });

  it("surfaces a rejected save instead of swallowing it", async () => {
    vi.mocked(connectionViewsApi.save).mockRejectedValue(
      new Error("preference store unavailable")
    );
    renderView();
    await openMoreFilters();

    fireEvent.change(screen.getByTestId("saved-view-name"), {
      target: { value: "Meine Sicht" },
    });
    fireEvent.click(screen.getByTestId("saved-view-save"));

    const alert = await screen.findByTestId(
      "connection-view-saved-views-error"
    );
    expect(alert).toHaveTextContent("preference store unavailable");
  });
});

describe("ConnectionView — action bar and filter row (V.4)", () => {
  it("assistant_has_no_list", async () => {
    renderView();
    await screen.findByTestId("allocation-trees-renderer");

    // The bar is present, the second requirement list is not.
    expect(screen.getByTestId("allocation-assistant")).toBeInTheDocument();
    expect(screen.queryByTestId("assistant-row-r1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-check-r1")).not.toBeInTheDocument();
  });

  it("action_bar_visible_without_selection", async () => {
    renderView();
    await screen.findByTestId("allocation-trees-renderer");

    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "0 ausgewählt"
    );
    expect(screen.getByTestId("assistant-allocate")).toBeDisabled();
    expect(screen.getByTestId("assistant-suggest")).toBeEnabled();
  });

  it("select_all_counts_visible_unlocked_only", async () => {
    vi.mocked(allocationViewApi.view).mockResolvedValue({
      ...RESPONSE,
      results: [
        ...RESPONSE.results,
        requirement({
          id: "r3",
          title: "Gesperrt",
          sort_key: "c",
          artifact_id: "art-r3",
          locked: "Freigegeben",
        }),
      ],
    });
    renderView();
    await screen.findByTestId("allocation-trees-renderer");

    fireEvent.click(screen.getByTestId("assistant-select-all"));

    // r3 is frozen: the visible selection is the two unlocked rows.
    expect(screen.getByTestId("assistant-selection-count")).toHaveTextContent(
      "2 ausgewählt"
    );
  });

  it("filter_more_state_follows_preference", async () => {
    vi.mocked(loadFiltersExpanded).mockResolvedValue(true);
    renderView();

    // The stored preference opens the row without a click.
    expect(await screen.findByTestId("filter-more")).toBeInTheDocument();
    expect(screen.getByTestId("filter-more-toggle")).toHaveAttribute(
      "aria-expanded",
      "true"
    );

    fireEvent.click(screen.getByTestId("filter-more-toggle"));

    await waitFor(() =>
      expect(screen.queryByTestId("filter-more")).not.toBeInTheDocument()
    );
    expect(saveFiltersExpanded).toHaveBeenCalledWith(false);
  });

  it("filters_expanded_survives_reload", async () => {
    vi.mocked(loadFiltersExpanded).mockResolvedValue(true);
    renderView();

    // A reload restores the row from the preference, not from the URL.
    expect(await screen.findByTestId("filter-more")).toBeInTheDocument();
    expect(loadFiltersExpanded).toHaveBeenCalled();
  });

  it("failed_preference_write_keeps_popover_open", async () => {
    vi.mocked(saveFiltersExpanded).mockRejectedValue(
      new Error("preference store unavailable")
    );
    renderView();
    await waitFor(() => expect(loadFiltersExpanded).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("filter-more-toggle"));

    expect(await screen.findByTestId("filter-more")).toBeInTheDocument();
    expect(await screen.findByTestId("filter-more-error")).toHaveTextContent(
      "preference store unavailable"
    );
  });

  it("unallocated_block_is_gone_and_marker_exists", async () => {
    renderView();
    await screen.findByTestId("allocation-trees-renderer");

    // The counted block is gone — the number lives in the header counter.
    expect(screen.queryByTestId("unallocated-block")).not.toBeInTheDocument();
    expect(screen.queryByTestId("unallocated-count")).not.toBeInTheDocument();
    expect(screen.getByTestId("counter-unallocated")).toHaveTextContent("2");

    // The state is now a row marker.
    expect(screen.getByTestId("unallocated-marker-r1")).toBeInTheDocument();
    expect(screen.getByTestId("unallocated-marker-r2")).toBeInTheDocument();
  });

  it("url_still_carries_filter_values", async () => {
    vi.mocked(allocationViewApi.tiers).mockResolvedValue({
      workspace_id: "ws-1",
      tiers: [
        {
          tier_key: "L1",
          name: { de: "System", en: "System" },
          position: 1,
          rule: "",
          from_end: null,
          level: 1,
        },
      ],
    });
    renderView();
    await openMoreFilters();

    fireEvent.change(screen.getByTestId("filter-q"), {
      target: { value: "bremse" },
    });
    fireEvent.change(screen.getByTestId("filter-tier"), {
      target: { value: "L1" },
    });

    await waitFor(() =>
      expect(allocationViewApi.view).toHaveBeenCalledWith(
        "ws-1",
        expect.objectContaining({
          q: "bremse",
          tier: "L1",
          kind: "requirement",
        })
      )
    );
    // Expanding the popover is a preference, not a filter: the URL keeps the
    // values (and gains nothing for the popover).
    expect(screen.getByTestId("filter-more")).toBeInTheDocument();
  });
});
