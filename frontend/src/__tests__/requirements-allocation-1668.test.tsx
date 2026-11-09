/**
 * #1668 — "allocated / not allocated" filter for the requirement list.
 *
 * The REST surface already understands `?allocated=true|false`
 * (`RequirementViewSet.list` → `RequirementService.list_requirements`), but the
 * UI had no way to express it. These tests pin the three seams:
 *
 *   1. the API wrapper turns the UI's tri-state filter into exactly one query
 *      parameter (and omits it entirely for "all");
 *   2. the list control reports the selected value and renders the
 *      "unallocated" count while that filter is active;
 *   3. the persisted selection survives an unmount/remount cycle and is scoped
 *      per workspace (BUG-19 / review finding F-02).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { Requirement } from "../types";
import {
  allocationToQueryParam,
  isRequirementAllocationFilter,
  requirementAllocationStorageKey,
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

describe("requirementsApi allocation filter (#1668)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetList.mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("sends allocated=true for the 'allocated' filter", async () => {
    await requirementsApi.listAll(WORKSPACE, { allocated: true });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      allocated: "true",
      page_size: "100",
    });
  });

  it("sends allocated=false for the 'unallocated' filter", async () => {
    await requirementsApi.listAll(WORKSPACE, { allocated: false });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      allocated: "false",
      page_size: "100",
    });
  });

  it("omits the parameter when the filter is 'all'", async () => {
    await requirementsApi.listAll(WORKSPACE, { allocated: undefined });

    expect(mockGetList).toHaveBeenCalledWith("/requirements/", {
      workspace_id: WORKSPACE,
      page_size: "100",
    });
  });

  it("maps the UI filter onto the tri-state API parameter", () => {
    expect(allocationToQueryParam("all")).toBeUndefined();
    expect(allocationToQueryParam("allocated")).toBe(true);
    expect(allocationToQueryParam("unallocated")).toBe(false);
    expect(allocationToQueryParam(undefined)).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// 2. list control
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: unknown) =>
      options && typeof options === "object" && "count" in options
        ? `${key}:${String((options as { count: unknown }).count)}`
        : key,
  }),
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-a" } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-a" } }),
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["editor"] }),
}));

import { RequirementList } from "../components/RequirementEditors/RequirementList";

function makeRequirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "req-1",
    workspace_id: "ws-a",
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

const REQUIREMENTS: Requirement[] = [makeRequirement({ id: "req-1" })];

describe("RequirementList allocation filter (#1668)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("renders the filter with the current value and reports changes", () => {
    const onAllocationChange = vi.fn();
    render(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        allocation="allocated"
        onAllocationChange={onAllocationChange}
      />,
    );

    const select = screen.getByTestId(
      "req-list-filter-allocation",
    ) as HTMLSelectElement;
    expect(select.value).toBe("allocated");

    fireEvent.change(select, { target: { value: "unallocated" } });
    expect(onAllocationChange).toHaveBeenCalledWith("unallocated");

    fireEvent.change(select, { target: { value: "" } });
    expect(onAllocationChange).toHaveBeenLastCalledWith("all");
  });

  it("shows the unallocated count only while that filter is active", () => {
    const { rerender } = render(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        allocation="unallocated"
        onAllocationChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId("req-list-unallocated-count")).toHaveTextContent(
      "editor.unallocatedCount:1",
    );

    rerender(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        allocation="all"
        onAllocationChange={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("req-list-unallocated-count")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 3. persistence (BUG-19 / F-02)
// ---------------------------------------------------------------------------

import { usePersistedListState } from "../hooks/usePersistedListState";
import type { RequirementAllocationFilter } from "../components/RequirementEditors/useRequirementData";

/**
 * Mirrors the container's call verbatim — same key helper, same validator.
 * The container itself (``RequirementEditors``) is not rendered here: it wires
 * a large module graph (artifact form, AI panels, split view) whose failure
 * modes are unrelated to filter persistence.
 */
function AllocationHarness({ workspaceId }: { workspaceId: string }) {
  const [value, setValue] = usePersistedListState<RequirementAllocationFilter>(
    requirementAllocationStorageKey(workspaceId),
    "all",
    { validate: isRequirementAllocationFilter },
  );
  return (
    <button type="button" data-testid="harness" onClick={() => setValue("unallocated")}>
      {value}
    </button>
  );
}

describe("allocation filter persistence", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("survives an unmount/remount cycle and is scoped per workspace", () => {
    const first = render(<AllocationHarness workspaceId="ws-a" />);
    fireEvent.click(screen.getByTestId("harness"));
    expect(screen.getByTestId("harness")).toHaveTextContent("unallocated");

    // Route change away and back.
    first.unmount();
    const second = render(<AllocationHarness workspaceId="ws-a" />);
    expect(screen.getByTestId("harness")).toHaveTextContent("unallocated");

    // Another workspace starts from the default; switching back restores ws-a.
    second.unmount();
    const other = render(<AllocationHarness workspaceId="ws-b" />);
    expect(screen.getByTestId("harness")).toHaveTextContent("all");

    other.unmount();
    render(<AllocationHarness workspaceId="ws-a" />);
    expect(screen.getByTestId("harness")).toHaveTextContent("unallocated");
  });
});
