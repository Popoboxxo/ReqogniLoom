/**
 * V6 (triage `docs/plans/2026-11-10-proposals-triage.md` §V6) — the level
 * filter of the requirement list.
 *
 * The REST surface already understood `?level=1..4`
 * (`RequirementViewSet.list` → `parse_int_param(..., minimum=1, maximum=4)`),
 * but the UI had no way to express it. These tests pin the four seams:
 *
 *   1. the API wrapper turns the UI's five-state filter into exactly one query
 *      parameter (and omits it entirely for "all");
 *   2. the persisting mapping (UI string union ↔ numeric parameter) and the
 *      per-workspace storage key;
 *   3. the data hook sends the parameter and hands the server-filtered rows to
 *      the list unchanged (the level is NOT re-filtered client-side);
 *   4. the list control reports the selected value and renders the fixed
 *      1..4 options next to the neighbouring filters.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { Requirement } from "../types";
import {
  isRequirementLevelFilter,
  levelToQueryParam,
  requirementLevelStorageKey,
  useRequirementData,
  type RequirementLevelFilter,
} from "../components/RequirementEditors/useRequirementData";

// ---------------------------------------------------------------------------
// 1. query string
// ---------------------------------------------------------------------------

const mockGetList = vi.fn();
const mockClientGet = vi.fn();

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockClientGet(...a),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: (...a: unknown[]) => mockGetList(...a),
  extractErrorMessage: (err: unknown) => String(err),
}));

import { requirementsApi } from "../api/requirements";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";

describe("requirementsApi level filter (V6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetList.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("sends level=2 for the '2' filter (listAll)", async () => {
    await requirementsApi.listAll(WORKSPACE, { level: 2 });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      level: "2",
      page_size: "100",
    });
  });

  it("sends level as a string, not a number (list)", async () => {
    const page = await requirementsApi.list(WORKSPACE, undefined, { level: 4 });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      level: "4",
      page_size: "100",
    });
    expect(page.count).toBe(0);
  });

  it("omits the parameter when no level filter is active", async () => {
    await requirementsApi.listAll(WORKSPACE, { level: undefined });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      page_size: "100",
    });
  });

  it("maps the UI filter onto the numeric API parameter", () => {
    expect(levelToQueryParam("all")).toBeUndefined();
    expect(levelToQueryParam(undefined)).toBeUndefined();
    expect(levelToQueryParam("1")).toBe(1);
    expect(levelToQueryParam("2")).toBe(2);
    expect(levelToQueryParam("3")).toBe(3);
    expect(levelToQueryParam("4")).toBe(4);
  });

  it("accepts exactly the five persisted values", () => {
    for (const value of ["all", "1", "2", "3", "4"]) {
      expect(isRequirementLevelFilter(value)).toBe(true);
    }
    for (const value of ["0", "5", "", null, 2, "L2"]) {
      expect(isRequirementLevelFilter(value)).toBe(false);
    }
  });

  it("scopes the persisted key per workspace", () => {
    expect(requirementLevelStorageKey("ws-a")).not.toBe(
      requirementLevelStorageKey("ws-b"),
    );
    expect(requirementLevelStorageKey(undefined)).toContain("no-workspace");
  });
});

// ---------------------------------------------------------------------------
// 2. data hook — the filter reaches the query, the rows are not re-filtered
// ---------------------------------------------------------------------------

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: WORKSPACE } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: WORKSPACE } }),
}));

import { renderWithQueryClient } from "../test/query-client";

function makeRequirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "req-1",
    workspace_id: WORKSPACE,
    title: "First requirement",
    description: "",
    category: "functional",
    status: "draft",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function LevelHarness({ level }: { level: RequirementLevelFilter }): JSX.Element {
  const { requirements, isLoading } = useRequirementData(undefined, { level });
  if (isLoading) return <p data-testid="loading">loading</p>;
  return (
    <ul data-testid="harness-list">
      {requirements.map((requirement) => (
        <li key={requirement.id} data-testid="harness-row">
          {requirement.title}
        </li>
      ))}
    </ul>
  );
}

describe("useRequirementData level filter (V6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("requests ?level=3 and renders exactly the server-filtered rows", async () => {
    mockGetList.mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      // The backend already applied the predicate — both rows are L3. The
      // client must not filter them a second time (that is how a row whose
      // `level` is stale in the payload would silently disappear).
      results: [
        makeRequirement({ id: "req-l3-a", title: "L3 A", level: 3 }),
        makeRequirement({ id: "req-l3-b", title: "L3 B", level: 3 }),
      ],
    });

    renderWithQueryClient(<LevelHarness level="3" />);

    await waitFor(() => {
      expect(screen.getAllByTestId("harness-row")).toHaveLength(2);
    });
    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      level: "3",
      page_size: "100",
    });
  });

  it("omits the parameter for 'all' and refetches when the level changes", async () => {
    mockGetList.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeRequirement()],
    });

    const first = renderWithQueryClient(<LevelHarness level="all" />);

    await waitFor(() => {
      expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
        workspace_id: WORKSPACE,
        page_size: "100",
      });
    });

    // A fresh provider per level: `level` is part of the query key, so the
    // second mount must issue its own request instead of reading a cache
    // entry that belongs to the unfiltered result set.
    first.unmount();
    renderWithQueryClient(<LevelHarness level="2" />);

    await waitFor(() => {
      expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
        workspace_id: WORKSPACE,
        level: "2",
        page_size: "100",
      });
    });
  });
});

// ---------------------------------------------------------------------------
// 3. list control
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: unknown) => {
      if (!options || typeof options !== "object") return key;
      const values = options as Record<string, unknown>;
      const parts = ["count", "shown", "total"]
        .filter((name) => name in values)
        .map((name) => String(values[name]));
      return parts.length > 0 ? `${key}:${parts.join(":")}` : key;
    },
  }),
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["editor"] }),
}));

import { RequirementList } from "../components/RequirementEditors/RequirementList";

const REQUIREMENTS: Requirement[] = [
  makeRequirement({ id: "req-1", title: "First requirement", level: 2 }),
];

describe("RequirementList level filter (V6)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("renders the filter with the current value and reports changes", () => {
    const onLevelChange = vi.fn();
    render(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        allocation="all"
        onAllocationChange={vi.fn()}
        level="2"
        onLevelChange={onLevelChange}
      />,
    );

    const select = screen.getByTestId("req-list-filter-level") as HTMLSelectElement;
    expect(select.value).toBe("2");

    fireEvent.change(select, { target: { value: "4" } });
    expect(onLevelChange).toHaveBeenCalledWith("4");

    fireEvent.change(select, { target: { value: "" } });
    expect(onLevelChange).toHaveBeenLastCalledWith("all");
  });

  it("offers the four fixed levels even when the loaded rows only cover one", () => {
    render(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        allocation="all"
        onAllocationChange={vi.fn()}
        level="all"
        onLevelChange={vi.fn()}
      />,
    );

    const select = screen.getByTestId("req-list-filter-level") as HTMLSelectElement;
    const values = Array.from(select.options).map((option) => option.value);
    // "" is the "no filter" entry, then exactly 1..4 — a level with zero
    // matches must stay selectable, otherwise the filter cannot be used to
    // show that a level is empty.
    expect(values).toEqual(["", "1", "2", "3", "4"]);
  });

  it("counts the level filter as an active list control", () => {
    render(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        allocation="all"
        onAllocationChange={vi.fn()}
        level="2"
        onLevelChange={vi.fn()}
      />,
    );

    // `editor.filteredCount` is the "shown of total" label the toolbar shows
    // only while at least one control is active.
    expect(
      screen.getByTestId("req-list-toolbar"),
    ).toHaveTextContent("editor.filteredCount:1:1");
  });
});

// ---------------------------------------------------------------------------
// 4. persistence (BUG-19 / F-02)
// ---------------------------------------------------------------------------

import { usePersistedListState } from "../hooks/usePersistedListState";

/**
 * Mirrors the container's call verbatim — same key helper, same validator, so
 * a drift between the two shows up here instead of only in the browser.
 */
function LevelPersistenceHarness({ workspaceId }: { workspaceId: string }) {
  const [value, setValue] = usePersistedListState<RequirementLevelFilter>(
    requirementLevelStorageKey(workspaceId),
    "all",
    { validate: isRequirementLevelFilter },
  );
  return (
    <button type="button" data-testid="harness" onClick={() => setValue("3")}>
      {value}
    </button>
  );
}

describe("level filter persistence", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("survives an unmount/remount cycle and is scoped per workspace", () => {
    const first = render(<LevelPersistenceHarness workspaceId="ws-a" />);
    fireEvent.click(screen.getByTestId("harness"));
    expect(screen.getByTestId("harness")).toHaveTextContent("3");

    first.unmount();
    const second = render(<LevelPersistenceHarness workspaceId="ws-a" />);
    expect(screen.getByTestId("harness")).toHaveTextContent("3");

    second.unmount();
    const other = render(<LevelPersistenceHarness workspaceId="ws-b" />);
    expect(screen.getByTestId("harness")).toHaveTextContent("all");

    other.unmount();
    render(<LevelPersistenceHarness workspaceId="ws-a" />);
    expect(screen.getByTestId("harness")).toHaveTextContent("3");
  });
});
