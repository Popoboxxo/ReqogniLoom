import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryVisualizationSection } from "./MemoryVisualizationSection";
import { memoryVisualizationApi } from "../../api/memory-visualization";
import * as workspaceContext from "../../context/WorkspaceContext";
// Real i18n singleton (as in MemoryManagementSection.test.tsx) — several
// assertions below rely on interpolated copy (page info, sampled/excluded
// notices, cluster labels), so `t()` must actually resolve against the
// locale bundles rather than echo the raw key back.
import "../../i18n/index";

vi.mock("../../api/memory-visualization", () => ({
  memoryVisualizationApi: {
    listEntries: vi.fn(),
    getProjection: vi.fn(),
  },
}));

vi.mock("../../context/WorkspaceContext");

const WORKSPACE = { id: "ws-11111111-1111-1111-1111-111111111111", name: "Acme Project" };

function mockActiveWorkspace(workspace: typeof WORKSPACE | null): void {
  vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
    activeWorkspace: workspace,
  } as unknown as ReturnType<typeof workspaceContext.useWorkspace>);
}

const ENTRY_ROW = {
  id: "entry-1",
  content: "The user prefers dark mode for the dashboard.",
  created_at: "2026-08-20T10:00:00Z",
  confidence: 0.87,
  owner_type: "workspace" as const,
  owner_id: WORKSPACE.id,
  owner_label: "Acme Project",
};

const PROJECTION_FIXTURE = {
  points: [
    {
      id: "entry-1",
      x: 0.1,
      y: 0.2,
      cluster_id: 0,
      owner_type: "workspace" as const,
      owner_id: WORKSPACE.id,
      owner_label: "Acme Project",
    },
    {
      id: "entry-2",
      x: -0.4,
      y: 0.9,
      cluster_id: 1,
      owner_type: "user" as const,
      owner_id: "user-1",
      owner_label: "alice@example.com",
    },
  ],
  sampled: false,
  sample_size: 2,
  total_size: 2,
  excluded_no_embedding: 0,
};

describe("MemoryVisualizationSection", () => {
  beforeEach(() => {
    // No global `clearMocks`/`resetMocks` is configured (see vite.config.ts's
    // `test` block) — mock call counts otherwise accumulate across `it`
    // blocks in this file, which would silently corrupt the exact
    // `toHaveBeenCalledTimes(...)` assertions below (client-side projection
    // caching is asserted on precise call counts, not just "was called").
    vi.clearAllMocks();
    mockActiveWorkspace(WORKSPACE);
    vi.mocked(memoryVisualizationApi.listEntries).mockResolvedValue({
      results: [ENTRY_ROW],
      count: 1,
      page: 1,
      page_size: 25,
    });
    vi.mocked(memoryVisualizationApi.getProjection).mockResolvedValue(PROJECTION_FIXTURE);
  });

  it("loads the List view on mount, scoped to the active workspace", async () => {
    render(<MemoryVisualizationSection />);

    await screen.findByTestId("memory-viz-row-entry-1");
    expect(memoryVisualizationApi.listEntries).toHaveBeenCalledWith(
      expect.objectContaining({ scope: "workspace", workspaceId: WORKSPACE.id, page: 1 })
    );
  });

  it("switching scope re-fetches entries with the new scope", async () => {
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");

    vi.mocked(memoryVisualizationApi.listEntries).mockClear();
    await user.click(screen.getByTestId("memory-viz-scope-global"));

    await waitFor(() => {
      expect(memoryVisualizationApi.listEntries).toHaveBeenCalledWith(
        expect.objectContaining({ scope: "global", page: 1 })
      );
    });
  });

  it("disables the workspace scope button when there is no active workspace", async () => {
    mockActiveWorkspace(null);
    render(<MemoryVisualizationSection />);

    await screen.findByTestId("memory-viz-row-entry-1");
    expect(memoryVisualizationApi.listEntries).toHaveBeenCalledWith(
      expect.objectContaining({ scope: "global" })
    );
    expect(screen.getByTestId("memory-viz-scope-workspace")).toBeDisabled();
  });

  it("filter input triggers a re-fetch with q, debounced", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<MemoryVisualizationSection />);
    await vi.waitFor(() => {
      expect(memoryVisualizationApi.listEntries).toHaveBeenCalled();
    });

    vi.mocked(memoryVisualizationApi.listEntries).mockClear();
    fireEvent.change(screen.getByTestId("memory-viz-filter-input"), {
      target: { value: "dark mode" },
    });

    // Not yet fired before the debounce window elapses.
    expect(memoryVisualizationApi.listEntries).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(500);

    expect(memoryVisualizationApi.listEntries).toHaveBeenCalledWith(
      expect.objectContaining({ q: "dark mode", page: 1 })
    );
    vi.useRealTimers();
  });

  it("List pagination: Next/Prev call listEntries with the adjacent page", async () => {
    vi.mocked(memoryVisualizationApi.listEntries).mockResolvedValue({
      results: [ENTRY_ROW],
      count: 60,
      page: 1,
      page_size: 25,
    });
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");

    vi.mocked(memoryVisualizationApi.listEntries).mockResolvedValueOnce({
      results: [ENTRY_ROW],
      count: 60,
      page: 2,
      page_size: 25,
    });
    await user.click(screen.getByTestId("memory-viz-list-next"));

    await waitFor(() => {
      expect(memoryVisualizationApi.listEntries).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 })
      );
    });

    await user.click(screen.getByTestId("memory-viz-list-prev"));
    await waitFor(() => {
      expect(memoryVisualizationApi.listEntries).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1 })
      );
    });
  });

  it("switching to Cluster view fetches the projection once", async () => {
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");
    expect(memoryVisualizationApi.getProjection).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("memory-viz-view-cluster"));

    const clusterList = await screen.findByTestId("memory-viz-cluster-list");
    expect(within(clusterList).getByTestId("memory-viz-cluster-group-0")).toBeInTheDocument();
    expect(within(clusterList).getByTestId("memory-viz-cluster-group-1")).toBeInTheDocument();
    expect(memoryVisualizationApi.getProjection).toHaveBeenCalledTimes(1);
  });

  it("switching Cluster -> Scatter -> Cluster does not re-fetch the cached projection", async () => {
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");

    await user.click(screen.getByTestId("memory-viz-view-cluster"));
    await screen.findByTestId("memory-viz-cluster-list");
    expect(memoryVisualizationApi.getProjection).toHaveBeenCalledTimes(1);

    await user.click(screen.getByTestId("memory-viz-view-scatter"));
    const plot = await screen.findByTestId("memory-viz-scatter-plot");
    expect(within(plot).getByTestId("memory-viz-scatter-point-entry-1")).toBeInTheDocument();
    expect(within(plot).getByTestId("memory-viz-scatter-point-entry-2")).toBeInTheDocument();

    await user.click(screen.getByTestId("memory-viz-view-cluster"));
    await screen.findByTestId("memory-viz-cluster-list");

    // Still just the one call from the first switch — client-side cache hit.
    expect(memoryVisualizationApi.getProjection).toHaveBeenCalledTimes(1);
  });

  it("shows the sampled and excluded-no-embedding notices when the API reports them", async () => {
    vi.mocked(memoryVisualizationApi.getProjection).mockResolvedValue({
      ...PROJECTION_FIXTURE,
      sampled: true,
      sample_size: 5000,
      total_size: 12000,
      excluded_no_embedding: 3,
    });
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");

    await user.click(screen.getByTestId("memory-viz-view-scatter"));

    const sampledNotice = await screen.findByTestId("memory-viz-sampled-notice");
    expect(sampledNotice).toHaveTextContent("5000");
    expect(sampledNotice).toHaveTextContent("12000");

    const excludedNotice = await screen.findByTestId("memory-viz-excluded-notice");
    expect(excludedNotice).toHaveTextContent("3");
  });

  it("does not show sampled/excluded notices when the API reports none", async () => {
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");

    await user.click(screen.getByTestId("memory-viz-view-scatter"));
    await screen.findByTestId("memory-viz-scatter-plot");

    expect(screen.queryByTestId("memory-viz-sampled-notice")).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-viz-excluded-notice")).not.toBeInTheDocument();
  });

  it("shows a list error state when listEntries rejects", async () => {
    vi.mocked(memoryVisualizationApi.listEntries).mockRejectedValue(new Error("boom"));
    render(<MemoryVisualizationSection />);

    expect(await screen.findByTestId("memory-viz-list-error")).toBeInTheDocument();
  });

  it("shows a projection error state when getProjection rejects", async () => {
    vi.mocked(memoryVisualizationApi.getProjection).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(<MemoryVisualizationSection />);
    await screen.findByTestId("memory-viz-row-entry-1");

    await user.click(screen.getByTestId("memory-viz-view-scatter"));

    expect(await screen.findByTestId("memory-viz-projection-error")).toBeInTheDocument();
  });

  it("shows the empty state when the list scope has no entries", async () => {
    vi.mocked(memoryVisualizationApi.listEntries).mockResolvedValue({
      results: [],
      count: 0,
      page: 1,
      page_size: 25,
    });
    render(<MemoryVisualizationSection />);

    expect(await screen.findByTestId("memory-viz-list-empty")).toBeInTheDocument();
  });
});
