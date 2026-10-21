import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    getWorkspaceDigest: vi.fn(),
    getEntry: vi.fn(),
    forgetEntry: vi.fn(),
    promoteEntry: vi.fn(),
    listArtifactMemory: vi.fn(),
    createArtifactMemory: vi.fn(),
    getSelfOverview: vi.fn(),
    deleteSelfMemory: vi.fn(),
    ask: vi.fn(),
  },
  // MemoryAskPanel imports this at module scope and maps over it on render.
  MEMORY_REASONING_LEVELS: ["minimal", "low", "medium", "high", "max"],
}));

// Keep `extractApiErrorMessage` real; only stub the artifact-pagination helper.
vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, getAllPages: vi.fn() };
});

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "Acme" } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "Acme" } }),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Mirrors the real `t(key, "default")` / `t(key, { defaultValue })`
    // shapes the component uses; interpolation keeps metadata assertions
    // meaningful (e.g. "Backend: honcho").
    t: (key: string, options?: unknown) => {
      if (typeof options === "string") return options;
      if (options && typeof options === "object") {
        const opts = options as Record<string, unknown>;
        const template =
          typeof opts.defaultValue === "string" ? opts.defaultValue : key;
        return template.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
          name in opts ? String(opts[name]) : match
        );
      }
      return key;
    },
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
    vi.mocked(memoryApi.getWorkspaceDigest).mockResolvedValue({
      digest: "Team uses TypeScript.",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "honcho",
      degraded: false,
    });
    vi.mocked(memoryApi.ask).mockResolvedValue({
      answer: "42",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "honcho",
      degraded: false,
      detail: "",
    });
  });

  it("lists workspace-scoped entries on mount", async () => {
    render(<MemoryPage />);

    expect(await screen.findByTestId("memory-row-w1")).toBeInTheDocument();
    expect(memoryApi.listWorkspaceEntries).toHaveBeenCalledWith(
      "ws-1",
      expect.objectContaining({ scope: "workspace", page: 1 })
    );
  });

  it("clears the pending filter-debounce timer on unmount (FE-04)", async () => {
    const view = render(<MemoryPage />);
    // Let the initial load settle before switching to fake timers.
    await screen.findByTestId("memory-row-w1");

    vi.useFakeTimers();
    try {
      fireEvent.change(screen.getByTestId("memory-filter-input"), {
        target: { value: "dark" },
      });
      expect(vi.getTimerCount()).toBeGreaterThan(0);

      view.unmount();
      // Without the unmount cleanup the debounce timer would still be pending.
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
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

  // --- digest (RFC #1002 F6) -------------------------------------------

  it("loads and renders the workspace digest with backend metadata", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-digest-btn"));

    expect(await screen.findByTestId("memory-digest-text")).toHaveTextContent(
      "Team uses TypeScript."
    );
    expect(memoryApi.getWorkspaceDigest).toHaveBeenCalledWith("ws-1");
    expect(screen.getByTestId("memory-digest-backend")).toHaveTextContent("honcho");
    expect(screen.getByTestId("memory-digest-generated-at")).toBeInTheDocument();
  });

  it("flags a degraded digest", async () => {
    vi.mocked(memoryApi.getWorkspaceDigest).mockResolvedValue({
      digest: "Partial summary",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "pgvector",
      degraded: true,
    });
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-digest-btn"));

    expect(await screen.findByTestId("memory-digest-degraded")).toBeInTheDocument();
  });

  it("shows a friendly empty state for a blank digest (not an error)", async () => {
    vi.mocked(memoryApi.getWorkspaceDigest).mockResolvedValue({
      digest: "",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "honcho",
      degraded: false,
    });
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-digest-btn"));

    expect(await screen.findByTestId("memory-digest-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("memory-digest-error")).not.toBeInTheDocument();
  });

  it("shows a digest error state when the request rejects", async () => {
    vi.mocked(memoryApi.getWorkspaceDigest).mockRejectedValue({
      error: { message: "digest boom" },
    });
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-digest-btn"));

    expect(await screen.findByTestId("memory-digest-error")).toHaveTextContent(
      "digest boom"
    );
  });

  it("re-invokes the digest endpoint on refresh", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-digest-btn"));
    await screen.findByTestId("memory-digest-text");
    await user.click(screen.getByTestId("memory-digest-btn"));

    await waitFor(() => {
      expect(memoryApi.getWorkspaceDigest).toHaveBeenCalledTimes(2);
    });
  });

  // --- ask (RFC #1002 #1155 Aspekt 1) ----------------------------------

  it("mounts the ask panel and asks the workspace scope", async () => {
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.type(screen.getByTestId("memory-ask-input"), "what changed?");
    await user.click(screen.getByTestId("memory-ask-submit"));

    await waitFor(() => {
      expect(memoryApi.ask).toHaveBeenCalledWith("ws-1", {
        query: "what changed?",
        artifactId: undefined,
        reasoningLevel: undefined,
      });
    });
    expect(await screen.findByTestId("memory-ask-answer")).toHaveTextContent("42");
  });

  it("targets the selected artifact when the artifact tab is active", async () => {
    vi.mocked(client.getAllPages).mockResolvedValue([
      { id: "art-1", artifact_type: "Requirement" },
    ] as never);
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-tab-artifact"));
    await user.selectOptions(screen.getByTestId("memory-artifact-select"), "art-1");
    await user.type(screen.getByTestId("memory-ask-input"), "why?");
    await user.click(screen.getByTestId("memory-ask-submit"));

    await waitFor(() => {
      expect(memoryApi.ask).toHaveBeenCalledWith(
        "ws-1",
        expect.objectContaining({ query: "why?", artifactId: "art-1" })
      );
    });
  });

  // --- #1295: active workspace name in the header -----------------------

  it("shows the active workspace name in the page header", async () => {
    render(<MemoryPage />);

    await screen.findByTestId("memory-row-w1");
    expect(screen.getByTestId("memory-active-workspace")).toHaveTextContent("Acme");
  });

  // --- #1296: error states + retry --------------------------------------

  it("renders a retry control for the load error and re-invokes the list endpoint", async () => {
    vi.mocked(memoryApi.listWorkspaceEntries).mockRejectedValue({
      error: { code: "MEMORY_UNAVAILABLE", message: "down" },
    });
    const user = userEvent.setup();
    render(<MemoryPage />);

    expect(await screen.findByTestId("memory-load-error")).toHaveTextContent("down");
    // #1296: the message is enriched with the backend error code.
    expect(screen.getByTestId("memory-load-error")).toHaveTextContent("(MEMORY_UNAVAILABLE)");

    await user.click(screen.getByTestId("memory-load-retry"));
    await waitFor(() => {
      expect(memoryApi.listWorkspaceEntries).toHaveBeenCalledTimes(2);
    });
  });

  it("enriches the error message with the HTTP status of a typed error", async () => {
    const { ForbiddenError } = await import("../../api/errors");
    vi.mocked(memoryApi.listWorkspaceEntries).mockRejectedValue(
      new ForbiddenError("Memory is admin-only")
    );

    render(<MemoryPage />);

    const alert = await screen.findByTestId("memory-load-error");
    expect(alert).toHaveTextContent("Memory is admin-only");
    expect(alert).toHaveTextContent("HTTP 403");
  });

  it("falls back to the localised message when the thrown value carries nothing", async () => {
    vi.mocked(memoryApi.listWorkspaceEntries).mockRejectedValue({});

    render(<MemoryPage />);

    expect(await screen.findByTestId("memory-load-error")).toHaveTextContent(
      "Gedächtnis konnte nicht geladen werden."
    );
    expect(screen.getByTestId("memory-load-retry")).toBeInTheDocument();
  });

  it("renders a retry control for the search error and re-invokes the search", async () => {
    vi.mocked(memoryApi.searchWorkspaceMemory).mockRejectedValue({
      error: { message: "search boom" },
    });
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.type(screen.getByTestId("memory-search-input"), "dark");
    await user.click(screen.getByTestId("memory-search-submit"));

    expect(await screen.findByTestId("memory-search-error")).toHaveTextContent("search boom");
    await user.click(screen.getByTestId("memory-search-retry"));
    await waitFor(() => {
      expect(memoryApi.searchWorkspaceMemory).toHaveBeenCalledTimes(2);
    });
  });

  it("renders a retry control for a failed row action and re-runs it", async () => {
    vi.mocked(memoryApi.promoteEntry).mockRejectedValue({
      error: { message: "promote boom" },
    });
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");
    await user.click(screen.getByTestId("memory-tab-user"));
    await screen.findByTestId("memory-row-u1");

    await user.click(screen.getByTestId("memory-promote-u1"));

    expect(await screen.findByTestId("memory-action-error")).toHaveTextContent("promote boom");
    await user.click(screen.getByTestId("memory-action-retry"));
    await waitFor(() => {
      expect(memoryApi.promoteEntry).toHaveBeenCalledTimes(2);
    });
  });

  it("renders a retry control for the digest error and re-invokes the digest", async () => {
    vi.mocked(memoryApi.getWorkspaceDigest).mockRejectedValue({
      error: { message: "digest boom" },
    });
    const user = userEvent.setup();
    render(<MemoryPage />);
    await screen.findByTestId("memory-row-w1");

    await user.click(screen.getByTestId("memory-digest-btn"));

    expect(await screen.findByTestId("memory-digest-error")).toHaveTextContent("digest boom");
    await user.click(screen.getByTestId("memory-digest-retry"));
    await waitFor(() => {
      expect(memoryApi.getWorkspaceDigest).toHaveBeenCalledTimes(2);
    });
  });
});
