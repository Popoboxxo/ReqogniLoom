import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import { ArtifactMemoryPanel } from "./ArtifactMemoryPanel";

vi.mock("../../api/memory", () => ({
  memoryApi: {
    listArtifactMemory: vi.fn(),
    createArtifactMemory: vi.fn(),
    forgetEntry: vi.fn(),
  },
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

const ARTIFACT_ID = "art-1";

function entry(overrides: Partial<MemoryEntry> = {}): MemoryEntry {
  return {
    entry_id: "e1",
    content: "The API must be idempotent",
    scope: "artifact",
    workspace_id: null,
    user_id: null,
    artifact_id: ARTIFACT_ID,
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

describe("ArtifactMemoryPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(memoryApi.listArtifactMemory).mockResolvedValue(
      page({ items: [entry()], total: 1 })
    );
    vi.mocked(memoryApi.createArtifactMemory).mockResolvedValue(entry());
    vi.mocked(memoryApi.forgetEntry).mockResolvedValue({ deleted: true });
  });

  it("lists artifact facts and shows the count badge", async () => {
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);

    expect(await screen.findByTestId("artifact-memory-count")).toHaveTextContent("1");
    expect(screen.getByTestId("artifact-memory-row-e1")).toBeInTheDocument();
    expect(memoryApi.listArtifactMemory).toHaveBeenCalledWith(
      ARTIFACT_ID,
      expect.objectContaining({ page_size: 25 })
    );
  });

  it("shows the empty state when there are no facts", async () => {
    vi.mocked(memoryApi.listArtifactMemory).mockResolvedValue(page());

    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);

    expect(await screen.findByTestId("artifact-memory-empty")).toBeInTheDocument();
  });

  it("shows a degraded notice when the response reports degraded", async () => {
    vi.mocked(memoryApi.listArtifactMemory).mockResolvedValue(
      page({ items: [entry()], total: 1, degraded: true })
    );

    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);

    expect(await screen.findByTestId("artifact-memory-degraded")).toBeInTheDocument();
  });

  it("creates a fact bound to the artifact", async () => {
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-add-btn"));
    const dialog = await screen.findByTestId("memory-add-fact-dialog");
    await user.type(within(dialog).getByTestId("memory-add-content"), "New artifact fact");
    await user.click(within(dialog).getByTestId("memory-add-submit"));

    await waitFor(() => {
      expect(memoryApi.createArtifactMemory).toHaveBeenCalledWith(ARTIFACT_ID, {
        content: "New artifact fact",
      });
    });
  });

  it("forget asks for confirmation and calls the delete endpoint", async () => {
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-forget-e1"));
    await user.click(await screen.findByTestId("artifact-memory-forget-confirm-confirm"));

    await waitFor(() => {
      expect(memoryApi.forgetEntry).toHaveBeenCalledWith("e1");
    });
  });

  it("shows an error state when loading fails", async () => {
    vi.mocked(memoryApi.listArtifactMemory).mockRejectedValue({
      error: { message: "boom" },
    });

    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);

    expect(await screen.findByTestId("artifact-memory-error")).toHaveTextContent("boom");
  });
});
