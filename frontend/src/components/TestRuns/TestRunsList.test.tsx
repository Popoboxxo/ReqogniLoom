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
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TestRunsList } from "./TestRunsList";

// TestRunsList now fetches through TanStack Query (REQ-050) — every render
// needs a QueryClientProvider. retry:false keeps rejected queries fast.
const renderList = (): ReturnType<typeof render> => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TestRunsList />
    </QueryClientProvider>,
  );
};
import * as testRunsModule from "../../api/test-runs";
import * as testcasesModule from "../../api/testcases";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/test-runs");
vi.mock("../../api/testcases");
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
    status: "closed",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "tr-2",
    workspace_id: "ws-123",
    name: "Smoke test run",
    description: "",
    status: "in_progress",
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
    vi.mocked(testRunsModule.testRunsApi.listAll).mockResolvedValue(mockTestRuns as any);
    // Detail panel now loads per-run results (C5) — default to an empty
    // list so tests that don't care about results don't have to mock it.
    vi.mocked(testRunsModule.testRunsApi.listResults).mockResolvedValue([]);
    // Create form now loads assignable test cases (C4) — default to an
    // empty list for tests that don't exercise the selection UI.
    vi.mocked(testcasesModule.testcasesApi.listAll).mockResolvedValue([] as any);
  });

  it("loads the test run list on mount", async () => {
    renderList();

    await waitFor(() => {
      expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
    });
    expect(testRunsModule.testRunsApi.listAll).toHaveBeenCalledWith("ws-123");
    expect(screen.getByText("Sprint 1 QA Run")).toBeInTheDocument();
    expect(screen.getByText("Smoke test run")).toBeInTheDocument();
  });

  it("displays status for each test run", async () => {
    renderList();

    await waitFor(() => {
      expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
    });
    expect(
      within(screen.getByTestId("testrun-item-tr-1")).getByText(/closed/i)
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("testrun-item-tr-2")).getByText(/in progress/i)
    ).toBeInTheDocument();
  });

  it("shows empty state when no test runs exist", async () => {
    vi.mocked(testRunsModule.testRunsApi.listAll).mockResolvedValue([] as any);

    renderList();

    await waitFor(() => {
      expect(screen.queryByTestId(/testrun-item/)).not.toBeInTheDocument();
    });
  });

  it("validates that name is required before create", async () => {
    const user = userEvent.setup();
    renderList();

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
    renderList();

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
    renderList();

    await waitFor(() => {
      expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testrun-create-btn"));
    await user.type(screen.getByTestId("testrun-name-input"), "New run");
    await user.click(screen.getByTestId("testrun-create-submit-btn"));

    await waitFor(() => {
      // initial load + refresh after create
      expect(testRunsModule.testRunsApi.listAll).toHaveBeenCalledTimes(2);
    });
  });

  it("shows an API error in the form alert", async () => {
    vi.mocked(testRunsModule.testRunsApi.create).mockRejectedValue({
      error: { message: "workspace not found" },
    });
    const user = userEvent.setup();
    renderList();

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
      renderList();

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
      renderList();

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

  describe("test cases assigned to a run (C5)", () => {
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

    it("shows the test cases (results) assigned to the run", async () => {
      vi.mocked(testRunsModule.testRunsApi.listResults).mockResolvedValue([
        {
          id: "res-1",
          test_run_id: "tr-1",
          test_case_id: "tc-1",
          test_case_title: "Login works",
          status: "passed",
          message: "",
          duration_ms: null,
          executed_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "res-2",
          test_run_id: "tr-1",
          test_case_id: "tc-2",
          test_case_title: "Logout works",
          status: "failed",
          message: "",
          duration_ms: null,
          executed_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ] as any);
      const user = userEvent.setup();
      renderList();

      await waitFor(() => {
        expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-item-tr-1"));

      await waitFor(() => {
        expect(testRunsModule.testRunsApi.listResults).toHaveBeenCalledWith(
          "tr-1"
        );
        expect(screen.getByTestId("testrun-results-list")).toBeInTheDocument();
      });
      expect(screen.getByText("Login works")).toBeInTheDocument();
      expect(screen.getByText("Logout works")).toBeInTheDocument();
    });

    it("shows an empty state when no test cases are assigned", async () => {
      vi.mocked(testRunsModule.testRunsApi.listResults).mockResolvedValue([]);
      const user = userEvent.setup();
      renderList();

      await waitFor(() => {
        expect(screen.getByTestId("testrun-item-tr-1")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-item-tr-1"));

      await waitFor(() => {
        expect(screen.getByTestId("testrun-results-empty")).toBeInTheDocument();
      });
    });
  });

  describe("assigning test cases when creating a run (C4)", () => {
    const testCases = [
      { id: "tc-1", workspace_id: "ws-123", title: "Login works", description: "", status: "active", version: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
      { id: "tc-2", workspace_id: "ws-123", title: "Logout works", description: "", status: "active", version: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
    ];

    it("loads and lists assignable test cases when the create form opens", async () => {
      vi.mocked(testcasesModule.testcasesApi.listAll).mockResolvedValue(testCases as any);
      const user = userEvent.setup();
      renderList();

      await waitFor(() => {
        expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-create-btn"));

      await waitFor(() => {
        expect(testcasesModule.testcasesApi.listAll).toHaveBeenCalledWith(
          "ws-123"
        );
        expect(
          screen.getByTestId("testrun-create-testcases-list")
        ).toBeInTheDocument();
      });
      expect(screen.getByText("Login works")).toBeInTheDocument();
      expect(screen.getByText("Logout works")).toBeInTheDocument();
    });

    it("sends the selected test_case_ids when creating a run", async () => {
      vi.mocked(testcasesModule.testcasesApi.listAll).mockResolvedValue(testCases as any);
      vi.mocked(testRunsModule.testRunsApi.create).mockResolvedValue({
        id: "tr-3",
      } as any);
      const user = userEvent.setup();
      renderList();

      await waitFor(() => {
        expect(screen.getByTestId("testrun-create-btn")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-create-btn"));

      await waitFor(() => {
        expect(
          screen.getByTestId("testrun-create-testcase-tc-1")
        ).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("testrun-create-testcase-tc-1"));
      await user.type(
        screen.getByTestId("testrun-name-input"),
        "New test run"
      );
      await user.click(screen.getByTestId("testrun-create-submit-btn"));

      await waitFor(() => {
        expect(testRunsModule.testRunsApi.create).toHaveBeenCalledWith({
          workspace_id: "ws-123",
          name: "New test run",
          test_case_ids: ["tc-1"],
        });
      });
    });
  });
});
