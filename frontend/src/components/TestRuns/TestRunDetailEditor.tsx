/**
 * ARCH-L1-001 ReactFrontend — TestRun Detail Editor (Presenter).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-AS-030 (Test-Run-Protokollierung), REQ-012 (close-in-place),
 *          REQ-050 (Container/Presenter decomposition of TestRunsList)
 *
 * Right-panel detail view for a single test run. Loads the run's per-TestCase
 * results (C5), hosts the result-entry grid (UI-04) and offers the
 * close-in-place action (REQ-012). Receives the run and lifecycle callbacks
 * as props from the TestRunsList container.
 *
 * TODO(REQ-050): the results fetch (testRunsApi.listResults) still lives here
 * as local state; a future pass can lift it into a useTestRunResults query hook.
 */

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { testRunsApi } from "../../api/test-runs";
import { StatusBadge } from "../shared/StatusBadge";
import { VersionBadge } from "../shared/VersionBadge";
import type { TestRun, TestRunResult } from "../../types";
import { getTestRunStatusLabel } from "./testRunStatusLabel";
import { TestRunResultEntryGrid } from "./TestRunResultEntryGrid";
import styles from "./TestRunDetailEditor.module.css";

/**
 * UI-04 lifecycle gate: which run states still accept result entry.
 *
 * `"closed"` is the only genuinely frozen state. Per
 * `TestRunService._sync_run_status_from_results`
 * (backend/application/test_run_service.py) a run explicitly finalized as
 * `"closed"` "is never touched again" — that status is only ever produced by
 * `close_test_run()` on a run *without* results, i.e. a deliberate human
 * verdict. The derived terminal states (`passed` / `failed` / `partial`) are
 * explicitly documented as re-derivable: "a run whose last red result is
 * re-reported green must end up passed". Blocking entry there would break
 * that documented correction path, so the gate is exactly `!== "closed"`.
 *
 * Note this is a UI guard, not an enforcement boundary: the backend still
 * accepts a POST to a closed run's results (it only skips the status
 * re-derivation). Anyone needing a hard guarantee has to add it in
 * `TestRunService.add_result` / `add_results_bulk`.
 */
// UI-56: named style object instead of an inline JSX style object literal
// (ui-ratchet.test.ts style-brace ceiling).
const closedTerminalHintStyle: CSSProperties = {
  fontSize: "var(--font-size-xs)",
  color: "var(--color-text-muted)",
  fontStyle: "italic",
};

function acceptsResultEntry(run: TestRun): boolean {
  return run.status !== "closed";
}

export interface TestRunDetailEditorProps {
  testRun: TestRun;
  onClose: () => void;
  onRefresh: () => Promise<void> | void;
  onUpdated: (run: TestRun) => void;
}

export function TestRunDetailEditor({
  testRun,
  onClose,
  onRefresh,
  onUpdated,
}: TestRunDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [isClosing, setIsClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [closeSuccess, setCloseSuccess] = useState(false);
  const [results, setResults] = useState<TestRunResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [resultsError, setResultsError] = useState<string | null>(null);
  // Bumped after a successful result write to re-run the load effect below
  // without giving up its cancellation guard (UI-04).
  const [resultsReloadToken, setResultsReloadToken] = useState(0);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Load the per-TestCase results belonging to this run (C5): the assigned
  // test cases are otherwise invisible inside a TestRun's detail view.
  useEffect(() => {
    let cancelled = false;
    setResultsLoading(true);
    setResultsError(null);
    testRunsApi
      .listResults(testRun.id)
      .then((items) => {
        if (!cancelled) setResults(items);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("Failed to load test run results:", err);
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          t("testRuns.resultsLoadFailed", "Testfälle konnten nicht geladen werden.");
        setResultsError(msg);
      })
      .finally(() => {
        if (!cancelled) setResultsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [testRun.id, t, resultsReloadToken]);

  /**
   * Post-write refresh (UI-04). A result write can change the *run's* status
   * as a side effect — `TestRunService._sync_run_status_from_results` re-derives
   * `passed`/`failed`/`partial`/`in_progress` inside the same transaction — so
   * the header badge and the "Close Run" action (gated on `in_progress`) are
   * stale until the run itself is refetched, not just its results.
   */
  const handleResultsSaved = async (): Promise<void> => {
    setSyncError(null);
    setResultsReloadToken((token) => token + 1);
    try {
      const refreshed = await testRunsApi.get(testRun.id);
      onUpdated(refreshed);
    } catch (err) {
      // Non-fatal: the write itself succeeded and the grid already reports
      // its own failures. Surfaced rather than swallowed because the header
      // badge is now knowingly stale.
      console.error("Failed to refresh test run after result save:", err);
      setSyncError(
        t(
          "testRuns.resultEntry.refreshFailed",
          "Ergebnisse gespeichert, der Testlauf konnte aber nicht neu geladen werden.",
        ),
      );
    }
    await onRefresh();
  };

  const handleClose = async (): Promise<void> => {
    setIsClosing(true);
    setCloseError(null);
    setCloseSuccess(false);
    try {
      const closedRun = await testRunsApi.close(testRun.id);
      // Update the detail panel in place with the closed run's new status
      // instead of dismissing the panel — the user needs to see that the
      // action actually took effect (REQ-012).
      onUpdated(closedRun);
      setConfirmClose(false);
      setCloseSuccess(true);
      await onRefresh();
    } catch (err) {
      console.error("Failed to close test run:", err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t("testRuns.closeFailed", "Test-Run konnte nicht geschlossen werden.");
      setCloseError(msg);
      setConfirmClose(false);
    } finally {
      setIsClosing(false);
    }
  };

  return (
    <div
      style={{
        background: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-card)",
        padding: "var(--space-6)",
      }}
    >
      <div style={{ marginBottom: "var(--space-6)" }}>
        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            margin: 0,
            marginBottom: "var(--space-2)",
          }}
        >
          {testRun.name}
        </h2>
        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            alignItems: "center",
          }}
        >
          <StatusBadge status={testRun.status} label={getTestRunStatusLabel(testRun.status)} />
          {/* UI-56: "closed" is the one genuinely terminal status (see
              acceptsResultEntry() above) — make that explicit instead of
              leaving the user to infer it from the missing Close button. */}
          {testRun.status === "closed" && (
            <span
              data-testid="testrun-closed-terminal-hint"
              style={closedTerminalHintStyle}
            >
              {t(
                "testRuns.closedTerminalHint",
                "This test run is closed and cannot be reopened or edited.",
              )}
            </span>
          )}
          {typeof testRun.version === "number" && (
            <VersionBadge version={testRun.version} />
          )}
          {testRun.uid ? (
            <span
              style={{
                fontFamily: "monospace",
                fontSize: "0.75rem",
                color: "var(--color-text-muted)",
                userSelect: "all",
              }}
              title="Unique Identifier"
            >
              {testRun.uid}
            </span>
          ) : (
            <span
              style={{
                fontFamily: "monospace",
                fontSize: "0.75rem",
                color: "var(--color-text-muted)",
                userSelect: "all",
                opacity: 0.6,
              }}
              title="Short ID (UUID prefix, no semantic uid assigned yet)"
            >
              {testRun.id.slice(0, 8)}
            </span>
          )}
          {testRun.ci_job_id && (
            <span
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-text-muted)",
              }}
            >
              CI: {testRun.ci_job_id}
            </span>
          )}
        </div>
      </div>

      {/* Summary */}
      {testRun.result_summary && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "var(--space-3)",
            marginBottom: "var(--space-6)",
          }}
        >
          {[
            {
              label: "Total",
              value: testRun.result_summary.total,
              color: "var(--color-text)",
            },
            {
              label: "Passed",
              value: testRun.result_summary.passed,
              color: "var(--color-summary-passed)",
            },
            {
              label: "Failed",
              value: testRun.result_summary.failed,
              color: "var(--color-summary-failed)",
            },
            {
              label: "Not Run",
              value: testRun.result_summary.not_run,
              color: "var(--color-summary-notrun)",
            },
          ].map((s) => (
            <div
              key={s.label}
              style={{
                padding: "var(--space-3)",
                background: "var(--color-surface-raised)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                textAlign: "center",
              }}
            >
              <div
                style={{
                  fontSize: "1.5rem",
                  fontWeight: 700,
                  color: s.color,
                }}
              >
                {s.value}
              </div>
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--color-text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Metadata */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-4)",
          marginBottom: "var(--space-6)",
        }}
      >
        {testRun.started_at && (
          <div>
            <label
              style={{
                display: "block",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                marginBottom: "var(--space-1)",
              }}
            >
              {t("testRuns.startedAt", "Started")}
            </label>
            <p style={{ margin: 0, color: "var(--color-text-muted)" }}>
              {new Date(testRun.started_at).toLocaleString()}
            </p>
          </div>
        )}
        {testRun.finished_at && (
          <div>
            <label
              style={{
                display: "block",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                marginBottom: "var(--space-1)",
              }}
            >
              {t("testRuns.finishedAt", "Finished")}
            </label>
            <p style={{ margin: 0, color: "var(--color-text-muted)" }}>
              {new Date(testRun.finished_at).toLocaleString()}
            </p>
          </div>
        )}
      </div>

      {/* Test cases (C5, REQ-012) */}
      <div style={{ marginBottom: "var(--space-6)" }}>
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 700,
            color: "var(--color-text)",
            margin: 0,
            marginBottom: "var(--space-3)",
          }}
        >
          {t("testRuns.testCases", "Testfälle")}
        </h3>
        {resultsLoading ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
            {t("testRuns.resultsLoading", "Lade Testfälle...")}
          </p>
        ) : resultsError ? (
          <p role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)" }}>
            {resultsError}
          </p>
        ) : results.length === 0 ? (
          <p
            data-testid="testrun-results-empty"
            style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}
          >
            {t("testRuns.resultsEmpty", "Diesem Testlauf sind keine Testfälle zugewiesen.")}
          </p>
        ) : (
          <TestRunResultEntryGrid
            testRunId={testRun.id}
            results={results}
            editable={acceptsResultEntry(testRun)}
            onSaved={handleResultsSaved}
          />
        )}
        {syncError && (
          <p
            role="alert"
            data-testid="testrun-results-sync-error"
            className={styles.syncError}
          >
            {syncError}
          </p>
        )}
      </div>

      {/* Close success */}
      {closeSuccess && (
        <p
          role="status"
          data-testid="testrun-close-success"
          style={{
            color: "var(--color-text)",
            fontSize: "var(--font-size-sm)",
            marginBottom: "var(--space-3)",
          }}
        >
          {t("testRuns.closeSuccess", "Test-Run wurde abgeschlossen.")}
        </p>
      )}

      {/* Close error */}
      {closeError && (
        <p
          role="alert"
          data-testid="testrun-close-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            marginBottom: "var(--space-3)",
          }}
        >
          {closeError}
        </p>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
        {testRun.status === "in_progress" &&
          (!confirmClose ? (
            <button
              type="button"
              data-testid="testrun-close-btn"
              onClick={() => setConfirmClose(true)}
              style={{
                padding: "var(--space-2) var(--space-4)",
                background: "var(--color-primary)",
                color: "var(--color-on-primary)",
                border: "none",
                borderRadius: "var(--radius-md)",
                cursor: "pointer",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
              }}
            >
              {t("testRuns.closeRun", "Close Run")}
            </button>
          ) : (
            <>
              <span
                style={{
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                }}
              >
                {/* UI-56: previously "Close this test run?" alone gave no
                    indication that closing is a one-way, terminal action
                    (acceptsResultEntry() above / TestRunService: "closed" is
                    never re-derived, unlike passed/failed/partial). */}
                {t(
                  "testRuns.closeConfirmIrreversible",
                  "Close this test run? This cannot be undone — a closed test run can no longer be edited or reopened.",
                )}
              </span>
              <button
                type="button"
                data-testid="testrun-confirm-close-btn"
                onClick={() => void handleClose()}
                disabled={isClosing}
                style={{
                  padding: "var(--space-2) var(--space-4)",
                  background: "var(--color-primary)",
                  color: "var(--color-on-primary)",
                  border: "none",
                  borderRadius: "var(--radius-md)",
                  cursor: isClosing ? "not-allowed" : "pointer",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  opacity: isClosing ? 0.6 : 1,
                }}
              >
                {isClosing
                  ? t("actions.closing", "Closing...")
                  : t("actions.confirm", "Confirm")}
              </button>
              <button
                type="button"
                data-testid="testrun-cancel-close-btn"
                onClick={() => setConfirmClose(false)}
                disabled={isClosing}
                style={{
                  padding: "var(--space-2) var(--space-4)",
                  background: "transparent",
                  color: "var(--color-text-muted)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  cursor: isClosing ? "not-allowed" : "pointer",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {t("actions.cancel")}
              </button>
            </>
          ))}
        <button
          type="button"
          data-testid="testrun-detail-close-btn"
          onClick={onClose}
          style={{
            padding: "var(--space-2) var(--space-4)",
            background: "transparent",
            color: "var(--color-text-muted)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {t("actions.back", "Back")}
        </button>
      </div>
    </div>
  );
}
