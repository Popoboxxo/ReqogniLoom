/**
 * Tests for TestRunDetailEditor's result-entry wiring (UI-04).
 *
 * req_id: REQ-L2-AS-030, REQ-012 (close-in-place)
 *
 * Complements TestRunResultEntryGrid.test.tsx (which covers the grid in
 * isolation) by exercising the two things that only exist at this boundary:
 * the lifecycle gate that decides whether the grid is editable at all, and
 * the post-write refresh — a result write can re-derive the *run's* status
 * server-side (TestRunService._sync_run_status_from_results), so the panel
 * must refetch the run, not just its results.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TestRunDetailEditor } from "./TestRunDetailEditor";
import * as testRunsModule from "../../api/test-runs";
import type { TestRun, TestRunResult } from "../../types";

vi.mock("../../api/test-runs");
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string): string => fallback ?? key;
  return { useTranslation: () => ({ t }) };
});

const RESULT: TestRunResult = {
  id: "res-1",
  test_run_id: "run-1",
  test_case_id: "tc-1",
  test_case_title: "Boils water",
  status: "not_run",
  message: "",
  duration_ms: null,
  executed_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const makeRun = (status: TestRun["status"]): TestRun => ({
  id: "run-1",
  workspace_id: "ws-1",
  name: "Sprint 1 QA Run",
  status,
  ci_job_id: "",
  started_at: null,
  finished_at: null,
  result_summary: { total: 1, passed: 0, failed: 0, blocked: 0, not_run: 1 },
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

describe("TestRunDetailEditor result entry (UI-04)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(testRunsModule.testRunsApi.listResults).mockResolvedValue([RESULT]);
    vi.mocked(testRunsModule.testRunsApi.addResult).mockResolvedValue({} as never);
  });

  it("allows result entry while the run is still open", async () => {
    render(
      <TestRunDetailEditor
        testRun={makeRun("in_progress")}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    expect(
      await screen.findByTestId("testrun-result-status-select-res-1"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("testrun-results-readonly-hint")).not.toBeInTheDocument();
  });

  it.each(["passed", "failed", "partial"] as const)(
    "still allows corrective entry on a derived-terminal run (%s)",
    async (status) => {
      render(
        <TestRunDetailEditor
          testRun={makeRun(status)}
          onClose={vi.fn()}
          onRefresh={vi.fn()}
          onUpdated={vi.fn()}
        />,
      );

      // The backend documents these as re-derivable from later results
      // (see acceptsResultEntry in the component), so the grid stays editable.
      expect(
        await screen.findByTestId("testrun-result-status-select-res-1"),
      ).toBeInTheDocument();
    },
  );

  it("locks result entry once the run is closed", async () => {
    render(
      <TestRunDetailEditor
        testRun={makeRun("closed")}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    expect(await screen.findByTestId("testrun-results-readonly-hint")).toBeInTheDocument();
    expect(
      screen.queryByTestId("testrun-result-status-select-res-1"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("testrun-results-toolbar")).not.toBeInTheDocument();
  });

  it("refetches results and the run itself after a successful write", async () => {
    const user = userEvent.setup();
    const refreshedRun = makeRun("passed");
    vi.mocked(testRunsModule.testRunsApi.get).mockResolvedValue(refreshedRun);
    const onUpdated = vi.fn();
    const onRefresh = vi.fn();

    render(
      <TestRunDetailEditor
        testRun={makeRun("in_progress")}
        onClose={vi.fn()}
        onRefresh={onRefresh}
        onUpdated={onUpdated}
      />,
    );

    await user.selectOptions(
      await screen.findByTestId("testrun-result-status-select-res-1"),
      "passed",
    );
    await user.click(screen.getByTestId("testrun-result-save-res-1"));

    await waitFor(() => {
      expect(onUpdated).toHaveBeenCalledWith(refreshedRun);
    });
    expect(testRunsModule.testRunsApi.get).toHaveBeenCalledWith("run-1");
    // Initial load + post-write reload.
    expect(testRunsModule.testRunsApi.listResults).toHaveBeenCalledTimes(2);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("reports a failed post-write refresh instead of leaving a stale badge", async () => {
    const user = userEvent.setup();
    vi.mocked(testRunsModule.testRunsApi.get).mockRejectedValue(new Error("boom"));

    render(
      <TestRunDetailEditor
        testRun={makeRun("in_progress")}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    await user.selectOptions(
      await screen.findByTestId("testrun-result-status-select-res-1"),
      "passed",
    );
    await user.click(screen.getByTestId("testrun-result-save-res-1"));

    expect(await screen.findByTestId("testrun-results-sync-error")).toBeInTheDocument();
    // The write itself succeeded, so the grid must not claim failure.
    expect(screen.queryByTestId("testrun-results-save-error")).not.toBeInTheDocument();
  });
});

// -----------------------------------------------------------------------
// UI-56 (Systemaudit 2026-08-27 AP-5): close-terminality must be explicit.
// -----------------------------------------------------------------------
describe("TestRunDetailEditor close-terminality (UI-56)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(testRunsModule.testRunsApi.listResults).mockResolvedValue([RESULT]);
  });

  it("shows the terminal hint once a run is closed", async () => {
    render(
      <TestRunDetailEditor
        testRun={makeRun("closed")}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    expect(await screen.findByTestId("testrun-closed-terminal-hint")).toBeInTheDocument();
    // A closed run has no Close button to begin with (already gated on
    // status === "in_progress").
    expect(screen.queryByTestId("testrun-close-btn")).not.toBeInTheDocument();
  });

  it("does not show the terminal hint for a still-open run", async () => {
    render(
      <TestRunDetailEditor
        testRun={makeRun("in_progress")}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    await screen.findByTestId("testrun-close-btn");
    expect(screen.queryByTestId("testrun-closed-terminal-hint")).not.toBeInTheDocument();
  });

  it("warns that closing is irreversible in the close-confirmation prompt", async () => {
    const user = userEvent.setup();
    render(
      <TestRunDetailEditor
        testRun={makeRun("in_progress")}
        onClose={vi.fn()}
        onRefresh={vi.fn()}
        onUpdated={vi.fn()}
      />,
    );

    await user.click(await screen.findByTestId("testrun-close-btn"));

    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
  });
});
