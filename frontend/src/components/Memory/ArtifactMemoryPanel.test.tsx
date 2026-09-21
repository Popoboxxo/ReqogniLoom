import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import { ArtifactMemoryPanel } from "./ArtifactMemoryPanel";

vi.mock("../../api/memory", () => ({
  memoryApi: {
    listArtifactMemory: vi.fn(),
    createArtifactMemory: vi.fn(),
    getArtifactDigest: vi.fn(),
    forgetEntry: vi.fn(),
  },
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
    vi.mocked(memoryApi.getArtifactDigest).mockResolvedValue({
      digest: "Artifact summary line.",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "honcho",
      degraded: false,
    });
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

  // --- digest (RFC #1002 F6) -------------------------------------------

  it("loads and renders the artifact digest with backend metadata", async () => {
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-digest-btn"));

    expect(await screen.findByTestId("artifact-memory-digest-text")).toHaveTextContent(
      "Artifact summary line."
    );
    expect(memoryApi.getArtifactDigest).toHaveBeenCalledWith(ARTIFACT_ID);
    expect(screen.getByTestId("artifact-memory-digest-backend")).toHaveTextContent(
      "honcho"
    );
  });

  it("flags a degraded artifact digest", async () => {
    vi.mocked(memoryApi.getArtifactDigest).mockResolvedValue({
      digest: "Partial summary",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "pgvector",
      degraded: true,
    });
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-digest-btn"));

    expect(
      await screen.findByTestId("artifact-memory-digest-degraded")
    ).toBeInTheDocument();
  });

  it("shows a friendly empty state for a blank artifact digest", async () => {
    vi.mocked(memoryApi.getArtifactDigest).mockResolvedValue({
      digest: "",
      generated_at: "2026-09-01T12:00:00Z",
      backend: "honcho",
      degraded: false,
    });
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-digest-btn"));

    expect(
      await screen.findByTestId("artifact-memory-digest-empty")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("artifact-memory-digest-error")
    ).not.toBeInTheDocument();
  });

  it("shows an error state when the artifact digest request rejects", async () => {
    vi.mocked(memoryApi.getArtifactDigest).mockRejectedValue({
      error: { message: "digest boom" },
    });
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-digest-btn"));

    expect(await screen.findByTestId("artifact-memory-digest-error")).toHaveTextContent(
      "digest boom"
    );
  });

  it("re-invokes the artifact digest endpoint on refresh", async () => {
    const user = userEvent.setup();
    render(<ArtifactMemoryPanel artifactId={ARTIFACT_ID} />);
    await screen.findByTestId("artifact-memory-row-e1");

    await user.click(screen.getByTestId("artifact-memory-digest-btn"));
    await screen.findByTestId("artifact-memory-digest-text");
    await user.click(screen.getByTestId("artifact-memory-digest-btn"));

    await waitFor(() => {
      expect(memoryApi.getArtifactDigest).toHaveBeenCalledTimes(2);
    });
  });
});
