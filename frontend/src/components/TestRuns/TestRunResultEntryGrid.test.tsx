/**
 * Tests for TestRunResultEntryGrid (UI-04, Systemaudit 2026-08-27).
 *
 * req_id: REQ-L2-AS-030 (Test-Run-Protokollierung), REQ-L2-AS-031 (bulk)
 *
 * Covers the three things the audit finding was about — that the SPA can
 * record results at all, that it uses both the single and the bulk endpoint,
 * and that a failed write is surfaced instead of silently swallowed — plus
 * the lifecycle gate and the `duration_ms` echo (see the component header for
 * why omitting it would null out CI-reported durations).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TestRunResultEntryGrid } from "./TestRunResultEntryGrid";
import * as testRunsModule from "../../api/test-runs";
import type { TestRunResult } from "../../types";

vi.mock("../../api/test-runs");
// Stable `t` reference: a fresh function per render would retrigger effects.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string): string => fallback ?? key;
  return { useTranslation: () => ({ t }) };
});

const makeResult = (overrides: Partial<TestRunResult> = {}): TestRunResult => ({
  id: "res-1",
  test_run_id: "run-1",
  test_case_id: "tc-1",
  test_case_title: "Boils water",
  status: "not_run",
  message: "",
  duration_ms: null,
  executed_at: null,
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const RESULTS: TestRunResult[] = [
  makeResult({ id: "res-1", test_case_id: "tc-1", test_case_title: "Boils water" }),
  makeResult({
    id: "res-2",
    test_case_id: "tc-2",
    test_case_title: "Auto shutoff",
    status: "failed",
    message: "too slow",
    duration_ms: 1200,
  }),
];

describe("TestRunResultEntryGrid (UI-04)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(testRunsModule.testRunsApi.addResult).mockResolvedValue({} as never);
    vi.mocked(testRunsModule.testRunsApi.addResultsBulk).mockResolvedValue({
      results: [],
      count: 0,
    } as never);
  });

  it("renders one editable row per result with its current status", () => {
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={RESULTS}
        editable
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByTestId("testrun-results-list")).toBeInTheDocument();
    expect(screen.getByText("Boils water")).toBeInTheDocument();
    expect(screen.getByTestId("testrun-result-status-res-2")).toHaveTextContent("Failed");
    // Both the per-row status select and the notes input are present.
    expect(screen.getByTestId("testrun-result-status-select-res-1")).toBeInTheDocument();
    expect(screen.getByTestId("testrun-result-notes-res-1")).toBeInTheDocument();
    // Nothing is dirty yet, so no write action is enabled.
    expect(screen.getByTestId("testrun-result-save-res-1")).toBeDisabled();
    expect(screen.getByTestId("testrun-results-save-all")).toBeDisabled();
  });

  it("hides every entry control and shows a hint when the run is not editable", () => {
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={RESULTS}
        editable={false}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByTestId("testrun-results-readonly-hint")).toBeInTheDocument();
    expect(screen.queryByTestId("testrun-results-toolbar")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("testrun-result-status-select-res-1"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("testrun-result-save-res-1")).not.toBeInTheDocument();
    // The read-only rendering still shows the recorded status.
    expect(screen.getByTestId("testrun-result-status-res-2")).toHaveTextContent("Failed");
  });

  it("saves a single row via addResult, echoing the stored duration_ms", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={RESULTS}
        editable
        onSaved={onSaved}
      />,
    );

    await user.selectOptions(
      screen.getByTestId("testrun-result-status-select-res-2"),
      "passed",
    );
    await user.clear(screen.getByTestId("testrun-result-notes-res-2"));
    await user.type(screen.getByTestId("testrun-result-notes-res-2"), "retested ok");
    await user.click(screen.getByTestId("testrun-result-save-res-2"));

    await waitFor(() => {
      expect(testRunsModule.testRunsApi.addResult).toHaveBeenCalledWith("run-1", {
        test_case_id: "tc-2",
        status: "passed",
        message: "retested ok",
        // Echoed back, not dropped — the backend upsert overwrites defaults.
        duration_ms: 1200,
      });
    });
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("testrun-results-save-success")).toBeInTheDocument();
  });

  it("bulk-applies a status to the selection and saves only dirty rows", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={RESULTS}
        editable
        onSaved={onSaved}
      />,
    );

    await user.click(screen.getByTestId("testrun-result-select-res-1"));
    await user.click(screen.getByTestId("testrun-results-bulk-apply"));
    await user.click(screen.getByTestId("testrun-results-save-all"));

    await waitFor(() => {
      expect(testRunsModule.testRunsApi.addResultsBulk).toHaveBeenCalledWith("run-1", [
        {
          test_case_id: "tc-1",
          status: "passed",
          message: "",
          duration_ms: null,
        },
      ]);
    });
    // res-2 was untouched, so it must not be re-reported.
    expect(testRunsModule.testRunsApi.addResultsBulk).toHaveBeenCalledTimes(1);
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("marks only the still-unreported rows as passed", async () => {
    const user = userEvent.setup();
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={RESULTS}
        editable
        onSaved={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId("testrun-results-mark-remaining-passed"));

    expect(screen.getByTestId("testrun-result-status-select-res-1")).toHaveValue("passed");
    // res-2 already carries a reported outcome and stays untouched.
    expect(screen.getByTestId("testrun-result-status-select-res-2")).toHaveValue("failed");
  });

  it("surfaces a failed write instead of swallowing it", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    vi.mocked(testRunsModule.testRunsApi.addResult).mockRejectedValue({
      error: { message: "Invalid status 'nope'." },
    });
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={RESULTS}
        editable
        onSaved={onSaved}
      />,
    );

    await user.selectOptions(
      screen.getByTestId("testrun-result-status-select-res-1"),
      "blocked",
    );
    await user.click(screen.getByTestId("testrun-result-save-res-1"));

    await waitFor(() => {
      expect(screen.getByTestId("testrun-results-save-error")).toHaveTextContent(
        "Invalid status 'nope'.",
      );
    });
    expect(screen.getByTestId("testrun-result-error-res-1")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.queryByTestId("testrun-results-save-success")).not.toBeInTheDocument();
  });

  it("keeps a result whose TestCase was deleted read-only", () => {
    render(
      <TestRunResultEntryGrid
        testRunId="run-1"
        results={[makeResult({ id: "res-3", test_case_id: null, status: "passed" })]}
        editable
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByTestId("testrun-result-status-select-res-3")).toBeDisabled();
    expect(screen.getByTestId("testrun-result-notes-res-3")).toBeDisabled();
    expect(screen.getByTestId("testrun-result-select-res-3")).toBeDisabled();
    expect(screen.getByTestId("testrun-result-save-res-3")).toBeDisabled();
  });
});
