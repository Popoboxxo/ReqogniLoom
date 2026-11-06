/**
 * P3 Task 3.2 — connection view shell.
 *
 * Verifies that filters are URL state, that switching the renderer preserves
 * them, that a reloaded URL restores them, and that saved views create/apply
 * through the preference-backed saved-view API.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import de from "../../i18n/locales/de.json";

import type { AllocationRow } from "../../api/allocation-view";
import { allocationViewApi } from "../../api/allocation-view";
import { connectionViewsApi } from "../../api/connection-views";
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
    requirement({ id: "r2", title: "Lenken", sort_key: "b" }),
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

  it("offers the card graph as the fourth renderer and keeps the filters", async () => {
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

describe("ConnectionView — writes go through the atomic bulk endpoint", () => {
  it("allocates a dragged requirement via POST /trace-links/bulk/", async () => {
    renderView();
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
