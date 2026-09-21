import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import * as client from "../../api/client";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import { MemoryPage } from "./MemoryPage";

vi.mock("../../api/memory", () => ({
  memoryApi: {
    listWorkspaceEntries: vi.fn(),
    createWorkspaceEntry: vi.fn(),
    searchWorkspaceMemory: vi.fn(),
    getEntry: vi.fn(),
    forgetEntry: vi.fn(),
    promoteEntry: vi.fn(),
    listArtifactMemory: vi.fn(),
    createArtifactMemory: vi.fn(),
    getSelfOverview: vi.fn(),
    deleteSelfMemory: vi.fn(),
  },
}));

// Keep `extractApiErrorMessage` real; only stub the artifact-pagination helper.
vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, getAllPages: vi.fn() };
});

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "Acme" } }),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key,
  }),
}));

function entry(overrides: Partial<MemoryEntry>): MemoryEntry {
  return {
    entry_id: "entry-1",
    content: "Prefers dark mode",
    scope: "workspace",
    workspace_id: "ws-1",
    user_id: null,
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
    ...overrides,
  };
}

function page(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    items: [] as MemoryEntry[],
    total: 0,
    page: 1,
    page_size: 25,
    backend: "pgvector",
    degraded: false,
    ...overrides,
  };
}

const WORKSPACE_ENTRY = entry({ entry_id: "w1", scope: "workspace" });
const USER_ENTRY = entry({
  entry_id: "u1",
  scope: "user",
  workspace_id: null,
  user_id: "user-1",
});

describe("MemoryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.getAllPages).mockResolvedValue([]);
    vi.mocked(memoryApi.listWorkspaceEntries).mockResolvedValue(
      page({ items: [WORKSPACE_ENTRY], total: 1 })
    );
    vi.mocked(memoryApi.getSelfOverview).mockResolvedValue({
      entry_count: 1,
      last_updated_at: "2026-08-20T10:00:00Z",
      entries: [USER_ENTRY],
      total: 1,
      page: 1,
      page_size: 25,
      backend: "pgvector",
      degraded: false,
    });
    vi.mocked(memoryApi.searchWorkspaceMemory).mockResolvedValue({
      items: [entry({ entry_id: "s1", content: "Found via search" })],
      query: "dark",
      scopes: ["workspace"],
      backend: "pgvector",
      degraded: false,
    });
    vi.mocked(memoryApi.createWorkspaceEntry).mockResolvedValue(WORKSPACE_ENTRY);
    vi.mocked(memoryApi.forgetEntry).mockResolvedValue({ deleted: true });
    vi.mocked(memoryApi.promoteEntry).mockResolvedValue(
      entry({ entry_id: "u1-promoted", scope: "workspace" })
    );
  });

  it("lists workspace-scoped entries on mount", async () => {
    render(<MemoryPage />);

    expect(await screen.findByTestId("memory-row-w1")).toBeInTheDocument();
    expect(memoryApi.listWorkspaceEntries).toHaveBeenCalledWith(
      "ws-1",
      expect.objectContaining({ scope: "workspace", page: 1 })
    );
  });

  it("switching to the Meins tab loads the user's own entries and offers promote", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-tab-user"));

    expect(await screen.findByTestId("memory-row-u1")).toBeInTheDocument();
    expect(memoryApi.getSelfOverview).toHaveBeenCalledWith(
      expect.objectContaining({ includeEntries: true })
    );
    expect(screen.getByTestId("memory-promote-u1")).toBeInTheDocument();
  });

  it("promote calls the promote endpoint with the active workspace", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");
    await user.click(screen.getByTestId("memory-tab-user"));
    await screen.findByTestId("memory-row-u1");

    await user.click(screen.getByTestId("memory-promote-u1"));

    await waitFor(() => {
      expect(memoryApi.promoteEntry).toHaveBeenCalledWith("u1", { workspace_id: "ws-1" });
    });
  });

  it("semantic search calls the search endpoint and renders hits", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.type(screen.getByTestId("memory-search-input"), "dark");
    await user.click(screen.getByTestId("memory-search-submit"));

    expect(await screen.findByTestId("memory-row-s1")).toBeInTheDocument();
    expect(memoryApi.searchWorkspaceMemory).toHaveBeenCalledWith(
      "ws-1",
      expect.objectContaining({ q: "dark", scope: "workspace" })
    );
    expect(screen.getByTestId("memory-search-list")).toBeInTheDocument();
  });

  it("shows the degraded banner when the response reports degraded", async () => {
    vi.mocked(memoryApi.listWorkspaceEntries).mockResolvedValue(
      page({ items: [WORKSPACE_ENTRY], total: 1, degraded: true })
    );

    render(<MemoryPage />);

    expect(await screen.findByTestId("memory-degraded-banner")).toBeInTheDocument();
  });

  it("forget asks for confirmation and calls the delete endpoint", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-forget-w1"));
    await user.click(await screen.findByTestId("memory-forget-confirm-confirm"));

    await waitFor(() => {
      expect(memoryApi.forgetEntry).toHaveBeenCalledWith("w1");
    });
  });

  it("add-fact dialog creates a workspace fact", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-add-fact-btn"));
    const dialog = await screen.findByTestId("memory-add-fact-dialog");
    await user.type(within(dialog).getByTestId("memory-add-content"), "New team fact");
    await user.click(within(dialog).getByTestId("memory-add-submit"));

    await waitFor(() => {
      expect(memoryApi.createWorkspaceEntry).toHaveBeenCalledWith("ws-1", {
        content: "New team fact",
      });
    });
  });

  it("artifact tab requires an artifact before loading", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");
    vi.mocked(memoryApi.listWorkspaceEntries).mockClear();

    await user.click(screen.getByTestId("memory-tab-artifact"));

    expect(await screen.findByTestId("memory-empty")).toBeInTheDocument();
    expect(screen.getByTestId("memory-artifact-select")).toBeInTheDocument();
    // No artifact chosen yet -> no list request for the artifact scope.
    expect(memoryApi.listWorkspaceEntries).not.toHaveBeenCalled();
  });

  it("shows a load error state when the list request rejects", async () => {
    vi.mocked(memoryApi.listWorkspaceEntries).mockRejectedValue({
      error: { message: "boom" },
    });

    render(<MemoryPage />);

    expect(await screen.findByTestId("memory-load-error")).toHaveTextContent("boom");
  });

  it("paginates when the total exceeds the page size", async () => {
    vi.mocked(memoryApi.listWorkspaceEntries).mockResolvedValue(
      page({ items: [WORKSPACE_ENTRY], total: 60 })
    );
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-page-next"));

    await waitFor(() => {
      expect(memoryApi.listWorkspaceEntries).toHaveBeenCalledWith(
        "ws-1",
        expect.objectContaining({ page: 2 })
      );
    });
  });
});
