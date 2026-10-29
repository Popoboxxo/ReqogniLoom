import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemorySection } from "./MemorySection";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import {
  memoryMeSettingsApi,
  type MemorySelfServiceSettings,
} from "../../api/memory-me-settings";
import { memorySettingsApi, type MemorySettings } from "../../api/memory-settings";
// Real i18n singleton — assertions rely on rendered copy resolving.
import { i18n } from "../../i18n/index";

vi.mock("../../api/memory", () => ({
  memoryApi: {
    getSelfOverview: vi.fn(),
    deleteSelfMemory: vi.fn(),
    forgetEntry: vi.fn(),
  },
}));

vi.mock("../../api/memory-me-settings", () => ({
  memoryMeSettingsApi: { get: vi.fn(), update: vi.fn() },
}));

vi.mock("../../api/memory-settings", () => ({
  memorySettingsApi: { get: vi.fn(), update: vi.fn() },
}));

// The slot catalogue comes from the workspace surface (the self-service
// payload carries no `available_slots`); the component reads the active
// workspace through the non-throwing context reader.
vi.mock("../../context/WorkspaceContext", () => ({
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
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

/** Full current self-service payload (Plan A T-A1-4) with overrides. */
function meSettings(
  overrides: Partial<MemorySelfServiceSettings> = {}
): MemorySelfServiceSettings {
  return {
    enabled: true,
    disabled_slots: [],
    effective: { workspace_id: "ws-1", opt_out_allowed: true },
    ...overrides,
  };
}

/** The workspace payload supplies `available_slots` (T-A1-3). */
const WORKSPACE_SLOTS: MemorySettings = {
  enabled: true,
  disabled_slots: [],
  allow_user_opt_out: true,
  effective_disabled_slots: [],
  available_slots: [
    { name: "bundle_compression", hard_off: true },
    { name: "testcase_derive", hard_off: false },
  ],
};

describe("MemorySection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    vi.clearAllMocks();
    vi.mocked(memoryApi.getSelfOverview).mockResolvedValue({ ...OVERVIEW_TWO });
    vi.mocked(memoryApi.deleteSelfMemory).mockResolvedValue({ deleted: 2 });
    vi.mocked(memoryApi.forgetEntry).mockResolvedValue({ deleted: true });
    vi.mocked(memoryMeSettingsApi.get).mockResolvedValue(meSettings());
    vi.mocked(memoryMeSettingsApi.update).mockResolvedValue(meSettings({ enabled: false }));
    vi.mocked(memorySettingsApi.get).mockResolvedValue({ ...WORKSPACE_SLOTS });
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

  // Plan A T-A1-7 (ENT-A7 = B): the workspace may forbid the personal
  // opt-out. The switch is still stored, so the only honest UI signal is the
  // `effective.opt_out_allowed === false` hint.
  it("shows the opt-out blocked hint when the workspace forbids opting out", async () => {
    vi.mocked(memoryMeSettingsApi.get).mockResolvedValue(
      meSettings({ effective: { workspace_id: "ws-1", opt_out_allowed: false } })
    );

    render(<MemorySection />);

    expect(await screen.findByTestId("memory-self-service-optout-blocked-hint")).toHaveTextContent(
      "Not honoured for workspace memory in this workspace — your personal memory stays off."
    );
    // The self-service payload is what the hint is read from: the workspace
    // id must be on the query.
    expect(memoryMeSettingsApi.get).toHaveBeenCalledWith("ws-1");
  });

  it("does not show the opt-out blocked hint when the workspace allows it", async () => {
    render(<MemorySection />);

    await screen.findByTestId("memory-self-service-enabled-toggle");
    expect(
      screen.queryByTestId("memory-self-service-optout-blocked-hint")
    ).not.toBeInTheDocument();
  });

  it("the self-service toggle sends only {enabled: …} to the me endpoint", async () => {
    const user = userEvent.setup();
    render(<MemorySection />);

    const toggle = await screen.findByTestId("memory-self-service-enabled-toggle");
    expect(toggle).toBeChecked();

    await user.click(toggle);

    // Exact partial body: no `disabled_slots` key, no workspace id.
    await waitFor(() =>
      expect(memoryMeSettingsApi.update).toHaveBeenCalledWith({ enabled: false })
    );
    await waitFor(() => expect(toggle).not.toBeChecked());
    expect(memorySettingsApi.update).not.toHaveBeenCalled();
  });

  it("renders the self-service slot list and sends a partial disabled_slots PUT", async () => {
    const user = userEvent.setup();
    render(<MemorySection />);

    const hardOff = await screen.findByTestId(
      "memory-self-service-slot-toggle-bundle-compression"
    );
    expect(hardOff).toBeDisabled();

    const slot = await screen.findByTestId("memory-self-service-slot-toggle-testcase-derive");
    expect(slot).toBeChecked();
    await user.click(slot);

    await waitFor(() =>
      expect(memoryMeSettingsApi.update).toHaveBeenCalledWith({
        disabled_slots: ["testcase_derive"],
      })
    );
  });
});
