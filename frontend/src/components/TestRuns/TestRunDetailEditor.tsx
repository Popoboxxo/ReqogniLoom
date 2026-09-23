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
  // UI-LOW-2 (Systemaudit 2026-08-27/29, LOW finding): distinct from
  // `resultsLoading` so the *initial* load can still show the "Lade
  // Testfälle..." placeholder while a post-write reload (see
  // `handleResultsSaved` below) does not. Before this, every reload swapped
  // <TestRunResultEntryGrid/> out for that placeholder in the same JSX slot
  // — a different element type at the same position unmounts the previous
  // one — which destroyed the grid's local `saveSuccess` state before a real
  // (macrotask-latency) network round trip ever let the user see the
  // "Ergebnisse gespeichert." banner it had just set.
  const [hasLoadedResultsOnce, setHasLoadedResultsOnce] = useState(false);
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
        if (!cancelled) {
          setResults(items);
          setHasLoadedResultsOnce(true);
        }
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
    <div className={styles.panel}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          {testRun.name}
        </h2>
        <div className={styles.badgeRow}>
          <StatusBadge status={testRun.status} label={getTestRunStatusLabel(testRun.status)} />
          {/* UI-56: "closed" is the one genuinely terminal status (see
              acceptsResultEntry() above) — make that explicit instead of
              leaving the user to infer it from the missing Close button. */}
          {testRun.status === "closed" && (
            <span
              data-testid="testrun-closed-terminal-hint"
              className={styles.closedTerminalHint}
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
              className={styles.uid}
              title="Unique Identifier"
            >
              {testRun.uid}
            </span>
          ) : (
            <span
              className={styles.shortId}
              title="Short ID (UUID prefix, no semantic uid assigned yet)"
            >
              {testRun.id.slice(0, 8)}
            </span>
          )}
          {testRun.ci_job_id && (
            <span
              className={styles.ciBadge}
            >
              CI: {testRun.ci_job_id}
            </span>
          )}
        </div>
      </div>

      {/* Summary */}
      {testRun.result_summary && (
        <div
          // issue #947: stable handle for E2E — the aggregate check used to
          // locate this block via the bare text "Total", which the surrounding
          // page can contain for unrelated reasons.
          data-testid="testrun-result-summary"
          className={styles.summaryGrid}
        >
          {[
            {
              label: "Total",
              value: testRun.result_summary.total,
              colorClass: styles.summaryValueTotal,
            },
            {
              label: "Passed",
              value: testRun.result_summary.passed,
              colorClass: styles.summaryValuePassed,
            },
            {
              label: "Failed",
              value: testRun.result_summary.failed,
              colorClass: styles.summaryValueFailed,
            },
            {
              label: "Not Run",
              value: testRun.result_summary.not_run,
              colorClass: styles.summaryValueNotRun,
            },
          ].map((s) => (
            <div key={s.label} className={styles.summaryItem}>
              <div className={`${styles.summaryValue} ${s.colorClass}`}>
                {s.value}
              </div>
              <div className={styles.summaryLabel}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Metadata */}
      <div className={styles.metaGrid}>
        {testRun.started_at && (
          <div>
            <label className={styles.fieldLabel}>
              {t("testRuns.startedAt", "Started")}
            </label>
            <p className={styles.fieldValue}>
              {new Date(testRun.started_at).toLocaleString()}
            </p>
          </div>
        )}
        {testRun.finished_at && (
          <div>
            <label className={styles.fieldLabel}>
              {t("testRuns.finishedAt", "Finished")}
            </label>
            <p className={styles.fieldValue}>
              {new Date(testRun.finished_at).toLocaleString()}
            </p>
          </div>
        )}
      </div>

      {/* Test cases (C5, REQ-012) */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>
          {t("testRuns.testCases", "Testfälle")}
        </h3>
        {resultsLoading && !hasLoadedResultsOnce ? (
          <p className={styles.mutedSmall}>
            {t("testRuns.resultsLoading", "Lade Testfälle...")}
          </p>
        ) : resultsError ? (
          <p role="alert" className={styles.errorSmall}>
            {resultsError}
          </p>
        ) : results.length === 0 ? (
          <p
            data-testid="testrun-results-empty"
            className={styles.mutedSmall}
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
          className={styles.successNote}
        >
          {t("testRuns.closeSuccess", "Test-Run wurde abgeschlossen.")}
        </p>
      )}

      {/* Close error */}
      {closeError && (
        <p
          role="alert"
          data-testid="testrun-close-error"
          className={styles.errorNote}
        >
          {closeError}
        </p>
      )}

      {/* Actions */}
      <div className={styles.actions}>
        {testRun.status === "in_progress" &&
          (!confirmClose ? (
            <button
              type="button"
              data-testid="testrun-close-btn"
              onClick={() => setConfirmClose(true)}
              className={styles.btnPrimary}
            >
              {t("testRuns.closeRun", "Close Run")}
            </button>
          ) : (
            <>
              <span
                className={styles.confirmHint}
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
                className={`${styles.btnPrimary} ${isClosing ? styles.btnPrimaryDisabled : styles.btnPrimaryEnabled}`}
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
                className={`${styles.btnSecondary} ${isClosing ? styles.btnSecondaryDisabled : styles.btnSecondaryEnabled}`}
              >
                {t("actions.cancel")}
              </button>
            </>
          ))}
        <button
          type="button"
          data-testid="testrun-detail-close-btn"
          onClick={onClose}
          className={styles.btnSecondary}
        >
          {t("actions.back", "Back")}
        </button>
      </div>
    </div>
  );
}
