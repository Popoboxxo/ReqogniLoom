/**
 * Tests for TestRunsList component.
 * REQ-L1-040 Phase 3: SE Masks Rollout — test run list view.
 * REQ-L2-AS-030: Test-Run-Protokollierung
 *
 * Verifies:
 * - list loads on mount
 * - form validation (name required)
 * - create calls testRunsApi.create with the registered contract payload
 * - list refreshes after create
 * - ModalDialogBase pattern integration
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TestRunsList } from "./TestRunsList";
import * as testRunsModule from "../../api/test-runs";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/test-runs");
vi.mock("../../context/WorkspaceContext");
// Stable t reference — a fresh t per render would re-trigger the
// useCallback([activeWorkspace, t]) load effect in an endless loop.
vi.mock("react-i18next", () => {
  const t = (key: string): string => key;
  return { useTranslation: () => ({ t }) };
});

const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };

const mockTestRuns = [
  {
    id: "tr-1",
    workspace_id: "ws-123",
    name: "Sprint 1 QA Run",
    description: "Full regression test",
    status: "completed",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "tr-2",
    workspace_id: "ws-123",
    name: "Smoke test run",
    description: "",
    status: "in-progress",
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
  },
];

describe("TestRunsList (REQ-L1-040 Phase 3, REQ-L2-AS-030)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(testRunsModule.testRunsApi.list).mockResolvedValue({
      results: mockTestRuns,
    } as any);
  });

  it("loads the test run list on mount", async () => {
    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
    });
    expect(testRunsModule.testRunsApi.list).toHaveBeenCalledWith("ws-123");
    expect(screen.getByText("Sprint 1 QA Run")).toBeInTheDocument();
    expect(screen.getByText("Smoke test run")).toBeInTheDocument();
  });

  it("displays status for each test run", async () => {
    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
    });
    expect(screen.getByText(/completed/)).toBeInTheDocument();
    expect(screen.getByText(/in-progress/)).toBeInTheDocument();
  });

  it("shows empty state when no test runs exist", async () => {
    vi.mocked(testRunsModule.testRunsApi.list).mockResolvedValue({
      results: [],
    } as any);

    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.queryByTestId(/testrun-item/)).not.toBeInTheDocument();
    });
  });

  it("validates that name is required before create", async () => {
    const user = userEvent.setup();
    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testrun-create-btn"));
    // Try submitting with only whitespace
    await user.type(screen.getByTestId("testrun-name-input"), "   ");
    expect(screen.getByTestId("testrun-create-submit-btn")).toBeDisabled();
    expect(testRunsModule.testRunsApi.create).not.toHaveBeenCalled();
  });

  it("creates a test run with the registered contract payload", async () => {
    vi.mocked(testRunsModule.testRunsApi.create).mockResolvedValue({
      id: "tr-3",
    } as any);
    const user = userEvent.setup();
    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testrun-create-btn"));

    await user.type(
      screen.getByTestId("testrun-name-input"),
      "New test run"
    );
    await user.click(screen.getByTestId("testrun-create-submit-btn"));

    await waitFor(() => {
      expect(testRunsModule.testRunsApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-123",
        name: "New test run",
      });
    });
  });

  it("refreshes the list after a successful create", async () => {
    vi.mocked(testRunsModule.testRunsApi.create).mockResolvedValue({
      id: "tr-3",
    } as any);
    const user = userEvent.setup();
    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testrun-create-btn"));
    await user.type(screen.getByTestId("testrun-name-input"), "New run");
    await user.click(screen.getByTestId("testrun-create-submit-btn"));

    await waitFor(() => {
      // initial load + refresh after create
      expect(testRunsModule.testRunsApi.list).toHaveBeenCalledTimes(2);
    });
  });

  it("shows an API error in the form alert", async () => {
    vi.mocked(testRunsModule.testRunsApi.create).mockRejectedValue({
      error: { message: "workspace not found" },
    });
    const user = userEvent.setup();
    render(<TestRunsList />);

    await waitFor(() => {
      expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testrun-create-btn"));
    await user.type(screen.getByTestId("testrun-name-input"), "Test");
    await user.click(screen.getByTestId("testrun-create-submit-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("workspace not found");
    });
  });

  describe("closing a test run (REQ-012)", () => {
    const detailRun = {
      id: "tr-1",
      workspace_id: "ws-123",
      name: "Sprint 1 QA Run",
      status: "in_progress",
      ci_job_id: "",
      started_at: null,
      finished_at: null,
      result_summary: { total: 0, passed: 0, failed: 0, not_run: 0 },
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    beforeEach(() => {
      vi.mocked(testRunsModule.testRunsApi.get).mockResolvedValue(
        detailRun as any
      );
    });

    it("shows a success message and keeps the panel open after closing", async () => {
      const closedRun = { ...detailRun, status: "closed", finished_at: "2026-01-02T00:00:00Z" };
      vi.mocked(testRunsModule.testRunsApi.close).mockResolvedValue(
        closedRun as any
      );
      const user = userEvent.setup();
      render(<TestRunsList />);

      await waitFor(() => {
        expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-item-tr-1"));

      await waitFor(() => {
        expect(screen.getByTestId("testrun-close-btn")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-close-btn"));
      await user.click(screen.getByTestId("testrun-confirm-close-btn"));

      await waitFor(() => {
        expect(testRunsModule.testRunsApi.close).toHaveBeenCalledWith("tr-1");
        expect(screen.getByTestId("testrun-close-success")).toBeInTheDocument();
      });
      // Panel stays open (no auto-dismiss) — detail heading still visible.
      expect(screen.getAllByText("Sprint 1 QA Run").length).toBeGreaterThan(0);
      // Terminal status means the Close Run button no longer offers to reopen.
      expect(screen.queryByTestId("testrun-close-btn")).not.toBeInTheDocument();
    });

    it("shows a visible error and keeps in_progress status when close fails", async () => {
      vi.mocked(testRunsModule.testRunsApi.close).mockRejectedValue({
        error: { message: "server exploded" },
      });
      const user = userEvent.setup();
      render(<TestRunsList />);

      await waitFor(() => {
        expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-item-tr-1"));

      await waitFor(() => {
        expect(screen.getByTestId("testrun-close-btn")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-close-btn"));
      await user.click(screen.getByTestId("testrun-confirm-close-btn"));

      await waitFor(() => {
        expect(screen.getByTestId("testrun-close-error")).toHaveTextContent(
          "server exploded"
        );
      });
      // Status unchanged → Close Run action is offered again.
      expect(screen.getByTestId("testrun-close-btn")).toBeInTheDocument();
    });
  });
});
