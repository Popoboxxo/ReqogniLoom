import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemorySection } from "./MemorySection";
import { memoryApi, type MemoryEntry } from "../../api/memory";
// Real i18n singleton — assertions rely on rendered copy resolving.
import "../../i18n/index";

vi.mock("../../api/memory", () => ({
  memoryApi: {
    getSelfOverview: vi.fn(),
    deleteSelfMemory: vi.fn(),
    forgetEntry: vi.fn(),
  },
}));

function entry(id: string, content: string): MemoryEntry {
  return {
    entry_id: id,
    content,
    scope: "user",
    workspace_id: null,
    user_id: "user-1",
    artifact_id: null,
    entity_type: "",
    contributor_user_id: null,
    source_event_id: null,
    source_session_id: null,
    confidence: 1,
    language: "de",
    created_at: "2026-08-20T10:00:00Z",
    superseded_by: null,
    backend: "pgvector",
    degraded: false,
  };
}

const OVERVIEW_EMPTY = {
  entry_count: 0,
  last_updated_at: null,
  entries: [],
  total: 0,
  page: 1,
  page_size: 100,
  backend: "pgvector",
  degraded: false,
};

const OVERVIEW_TWO = {
  ...OVERVIEW_EMPTY,
  entry_count: 2,
  last_updated_at: "2026-08-20T10:00:00Z",
  entries: [entry("e1", "Prefers dark mode"), entry("e2", "Uses TypeScript")],
  total: 2,
};

describe("MemorySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(memoryApi.getSelfOverview).mockResolvedValue({ ...OVERVIEW_TWO });
    vi.mocked(memoryApi.deleteSelfMemory).mockResolvedValue({ deleted: 2 });
    vi.mocked(memoryApi.forgetEntry).mockResolvedValue({ deleted: true });
  });

  it("shows the loading state, then resolves to the overview list", async () => {
    render(<MemorySection />);

    expect(screen.getByTestId("memory-self-service-loading")).toBeInTheDocument();

    expect(await screen.findByTestId("memory-self-service-count")).toHaveTextContent("2");
    expect(screen.queryByTestId("memory-self-service-loading")).not.toBeInTheDocument();
    expect(screen.getByTestId("memory-self-service-row-e1")).toBeInTheDocument();
  });

  it("zero-entries state: delete button disabled, empty message shown", async () => {
    vi.mocked(memoryApi.getSelfOverview).mockResolvedValue({ ...OVERVIEW_EMPTY });

    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    expect(btn).toBeDisabled();
    expect(await screen.findByTestId("memory-self-service-empty")).toBeInTheDocument();
    expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("0");
  });

  it("non-zero entries: count, last-updated and rows render", async () => {
    render(<MemorySection />);

    expect(await screen.findByTestId("memory-self-service-count")).toHaveTextContent("2");
    const lastUpdated = screen.getByTestId("memory-self-service-last-updated");
    expect(lastUpdated.textContent).not.toBe("—");
    expect(screen.getByTestId("memory-self-service-list")).toBeInTheDocument();
    expect(screen.getByTestId("memory-self-service-row-e2")).toBeInTheDocument();
    expect(screen.getByTestId("memory-self-service-delete-btn")).not.toBeDisabled();
  });

  it("delete-all flow, confirmed: calls deleteSelfMemory and resets the UI to empty", async () => {
    const user = userEvent.setup();
    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    await user.click(btn);
    await user.click(await screen.findByTestId("memory-self-service-delete-confirm-confirm"));

    await waitFor(() => {
      expect(memoryApi.deleteSelfMemory).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("0");
    });
    expect(screen.getByTestId("memory-self-service-delete-btn")).toBeDisabled();
    expect(await screen.findByTestId("memory-self-service-empty")).toBeInTheDocument();
  });

  it("delete-all flow, cancelled: does not call deleteSelfMemory", async () => {
    const user = userEvent.setup();
    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    await user.click(btn);
    await user.click(await screen.findByTestId("memory-self-service-delete-confirm-cancel"));

    expect(memoryApi.deleteSelfMemory).not.toHaveBeenCalled();
    expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("2");
  });

  it("forget single entry: confirms, calls forgetEntry and reloads", async () => {
    const user = userEvent.setup();
    render(<MemorySection />);

    await screen.findByTestId("memory-self-service-row-e1");
    vi.mocked(memoryApi.getSelfOverview).mockResolvedValue({ ...OVERVIEW_EMPTY });
    await user.click(screen.getByTestId("memory-self-service-forget-e1"));

    const dialog = await screen.findByTestId("memory-self-service-forget-confirm");
    await user.click(within(dialog).getByTestId("memory-self-service-forget-confirm-confirm"));

    await waitFor(() => {
      expect(memoryApi.forgetEntry).toHaveBeenCalledWith("e1");
    });
    await waitFor(() => {
      expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("0");
    });
    expect(screen.getByTestId("memory-self-service-empty")).toBeInTheDocument();
  });

  it("shows an error message when loading fails", async () => {
    vi.mocked(memoryApi.getSelfOverview).mockRejectedValue({
      error: { message: "boom" },
    });

    render(<MemorySection />);

    expect(await screen.findByTestId("memory-self-service-error")).toHaveTextContent("boom");
  });

  it("shows an error message when delete fails", async () => {
    vi.mocked(memoryApi.deleteSelfMemory).mockRejectedValue({
      error: { message: "delete failed" },
    });

    const user = userEvent.setup();
    render(<MemorySection />);

    const btn = await screen.findByTestId("memory-self-service-delete-btn");
    await user.click(btn);
    await user.click(await screen.findByTestId("memory-self-service-delete-confirm-confirm"));

    expect(await screen.findByTestId("memory-self-service-error")).toHaveTextContent(
      "delete failed"
    );
    // Failed delete must not silently reset the count to 0.
    expect(screen.getByTestId("memory-self-service-count")).toHaveTextContent("2");
  });
});
