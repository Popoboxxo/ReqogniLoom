/**
 * ARCH-L1-001 ReactFrontend — TestRun Result Entry Grid.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-AS-030 (Test-Run-Protokollierung), REQ-L2-AS-031 (bulk
 *          ingestion), UI-04 (Systemaudit 2026-08-27 / decision D-05)
 *
 * Editable grid for the per-TestCase execution results of a single TestRun.
 * Until UI-04 the SPA could only *display* results — `testRunsApi.addResult`
 * and `addResultsBulk` existed but had zero callers, so results could be
 * recorded via REST/MCP/CI only. This component is the missing SPA entry
 * path for both.
 *
 * Contract notes (verified against the backend, not assumed):
 *  - Allowed status values are exactly `passed | failed | blocked | not_run`
 *    — `VALID_RESULT_STATUSES` in `backend/application/test_run_service.py`
 *    and the `TestRunResult.status` choices in `backend/persistence/models.py`.
 *    Anything else is rejected with a 400 by the service.
 *  - Writes are an **upsert** keyed on `(test_run, test_case)`
 *    (`TestRunService.add_result` / `add_results_bulk` use
 *    `update_or_create`), so re-reporting a TestCase corrects its row instead
 *    of appending a duplicate. That is what makes an "edit" of an existing
 *    result possible at all — there is no PATCH endpoint for a result row.
 *  - Because the upsert writes `defaults`, every field it covers must be sent
 *    on every write: `duration_ms` is therefore echoed back from the loaded
 *    result. Omitting it would silently null out a duration reported earlier
 *    by CI, since the view forwards `request.data.get("duration_ms")` (i.e.
 *    `None`) straight into `defaults`.
 *  - A result whose `test_case_id` is `null` (the FK is `on_delete=SET_NULL`,
 *    i.e. its TestCase was deleted) cannot be re-reported — the endpoints
 *    require `test_case_id` — so those rows stay read-only.
 *
 * Styling lives in the co-located CSS Module: the inline-style ratchet in
 * `src/test/ui-ratchet.test.ts` is frozen and monotonic (and counts raw
 * occurrences, comments included), so new UI must not introduce inline style
 * object literals.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { testRunsApi } from "../../api/test-runs";
import { StatusBadge } from "../shared/StatusBadge";
import { getTestRunStatusLabel } from "./testRunStatusLabel";
import type { TestRunResult, UUID } from "../../types";
import styles from "./TestRunResultEntryGrid.module.css";

/**
 * The status values the backend accepts for a TestRunResult.
 * Source of truth: `VALID_RESULT_STATUSES` in
 * `backend/application/test_run_service.py` (mirrored by the
 * `TestRunResult.status` model choices and `TestRunResultSerializer`).
 */
export const TEST_RUN_RESULT_STATUSES = [
  "passed",
  "failed",
  "blocked",
  "not_run",
] as const;

export type TestRunResultStatus = (typeof TEST_RUN_RESULT_STATUSES)[number];

/** Locally edited, not-yet-persisted values for one result row. */
interface ResultDraft {
  status: TestRunResultStatus;
  message: string;
}

export interface TestRunResultEntryGridProps {
  /** The run the results belong to — target of the result endpoints. */
  testRunId: UUID;
  /** Results as last loaded from the server; resets the local drafts. */
  results: TestRunResult[];
  /**
   * Lifecycle gate (see `TestRunDetailEditor` for the rationale): `false`
   * renders the grid read-only.
   */
  editable: boolean;
  /** Invoked after a successful write so the caller can refetch. */
  onSaved: () => Promise<void> | void;
}

/** Extract a `{ error: { message } }`-shaped API error message, if present. */
function apiErrorMessage(err: unknown): string | null {
  const msg = (err as { error?: { message?: string } })?.error?.message;
  return msg ?? null;
}

function draftsFromResults(
  results: TestRunResult[],
): Record<string, ResultDraft> {
  const next: Record<string, ResultDraft> = {};
  for (const result of results) {
    next[result.id] = {
      status: result.status,
      message: result.message ?? "",
    };
  }
  return next;
}

function isDirty(result: TestRunResult, draft: ResultDraft | undefined): boolean {
  if (!draft) return false;
  return draft.status !== result.status || draft.message !== (result.message ?? "");
}

/** A row can only be written back when its TestCase FK still resolves. */
function isWritable(result: TestRunResult): boolean {
  return result.test_case_id !== null && result.test_case_id !== undefined;
}

export function TestRunResultEntryGrid({
  testRunId,
  results,
  editable,
  onSaved,
}: TestRunResultEntryGridProps): JSX.Element {
  const { t } = useTranslation();
  const [drafts, setDrafts] = useState<Record<string, ResultDraft>>(() =>
    draftsFromResults(results),
  );
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [bulkStatus, setBulkStatus] = useState<TestRunResultStatus>("passed");
  const [savingRowId, setSavingRowId] = useState<string | null>(null);
  const [isSavingAll, setIsSavingAll] = useState(false);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Server state is authoritative: a reload (own save, or the parent's
  // refetch) discards local drafts rather than silently keeping an edit that
  // the backend may have already normalised.
  useEffect(() => {
    setDrafts(draftsFromResults(results));
    setSelected({});
    setRowErrors({});
  }, [results]);

  const writableResults = useMemo(
    () => results.filter(isWritable),
    [results],
  );

  const dirtyResults = useMemo(
    () => writableResults.filter((r) => isDirty(r, drafts[r.id])),
    [writableResults, drafts],
  );

  const selectedIds = useMemo(
    () => writableResults.filter((r) => selected[r.id]).map((r) => r.id),
    [writableResults, selected],
  );

  const remainingCount = useMemo(
    () => writableResults.filter((r) => r.status === "not_run").length,
    [writableResults],
  );

  const isBusy = isSavingAll || savingRowId !== null;

  const setDraft = (id: string, patch: Partial<ResultDraft>): void => {
    setDrafts((prev) => ({
      ...prev,
      [id]: { ...prev[id], ...patch } as ResultDraft,
    }));
  };

  const applyStatusTo = (ids: string[], status: TestRunResultStatus): void => {
    if (ids.length === 0) return;
    setDrafts((prev) => {
      const next = { ...prev };
      for (const id of ids) {
        next[id] = { ...next[id], status };
      }
      return next;
    });
  };

  const toggleSelectAll = (checked: boolean): void => {
    const next: Record<string, boolean> = {};
    if (checked) {
      for (const result of writableResults) next[result.id] = true;
    }
    setSelected(next);
  };

  /** Reset the banners before a write so stale feedback is never shown. */
  const beginWrite = (): void => {
    setSaveError(null);
    setSaveSuccess(false);
  };

  const handleWriteFailure = (err: unknown, rowId?: string): void => {
    console.error("Failed to save test run result(s):", err);
    const msg =
      apiErrorMessage(err) ??
      t("testRuns.resultEntry.saveFailed", "Ergebnis konnte nicht gespeichert werden.");
    setSaveError(msg);
    if (rowId) {
      setRowErrors((prev) => ({ ...prev, [rowId]: msg }));
    }
  };

  const handleSaveRow = async (result: TestRunResult): Promise<void> => {
    const draft = drafts[result.id];
    if (!draft || !isWritable(result)) return;
    beginWrite();
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[result.id];
      return next;
    });
    setSavingRowId(result.id);
    try {
      await testRunsApi.addResult(testRunId, {
        test_case_id: result.test_case_id as UUID,
        status: draft.status,
        message: draft.message,
        // Echoed back on purpose — see the upsert note in the file header.
        duration_ms: result.duration_ms,
      });
      setSaveSuccess(true);
      await onSaved();
    } catch (err) {
      handleWriteFailure(err, result.id);
    } finally {
      setSavingRowId(null);
    }
  };

  const handleSaveAll = async (): Promise<void> => {
    if (dirtyResults.length === 0) return;
    beginWrite();
    setRowErrors({});
    setIsSavingAll(true);
    try {
      await testRunsApi.addResultsBulk(
        testRunId,
        dirtyResults.map((result) => ({
          test_case_id: result.test_case_id as UUID,
          status: drafts[result.id].status,
          message: drafts[result.id].message,
          duration_ms: result.duration_ms,
        })),
      );
      setSaveSuccess(true);
      await onSaved();
    } catch (err) {
      handleWriteFailure(err);
    } finally {
      setIsSavingAll(false);
    }
  };

  const allSelected =
    writableResults.length > 0 && selectedIds.length === writableResults.length;

  return (
    <div className={styles.wrapper} data-testid="testrun-result-entry-grid">
      {!editable && (
        <p className={styles.hint} data-testid="testrun-results-readonly-hint">
          {t(
            "testRuns.resultEntry.readOnlyHint",
            "Dieser Testlauf ist abgeschlossen — Ergebnisse können nicht mehr erfasst werden.",
          )}
        </p>
      )}

      {editable && (
        <div className={styles.toolbar} data-testid="testrun-results-toolbar">
          <span className={styles.toolbarLabel}>
            {t("testRuns.resultEntry.bulkStatusLabel", "Status für Auswahl")}
          </span>
          <select
            className={styles.select}
            data-testid="testrun-results-bulk-status"
            aria-label={t("testRuns.resultEntry.bulkStatusLabel", "Status für Auswahl")}
            value={bulkStatus}
            disabled={isBusy}
            onChange={(e) => setBulkStatus(e.target.value as TestRunResultStatus)}
          >
            {TEST_RUN_RESULT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(
                  `testRuns.resultEntry.status.${status}`,
                  getTestRunStatusLabel(status),
                )}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={styles.button}
            data-testid="testrun-results-bulk-apply"
            disabled={isBusy || selectedIds.length === 0}
            onClick={() => applyStatusTo(selectedIds, bulkStatus)}
          >
            {t("testRuns.resultEntry.applyToSelected", "Auf Auswahl anwenden")}
            {` (${selectedIds.length})`}
          </button>
          <button
            type="button"
            className={styles.button}
            data-testid="testrun-results-mark-remaining-passed"
            disabled={isBusy || remainingCount === 0}
            onClick={() =>
              applyStatusTo(
                writableResults.filter((r) => r.status === "not_run").map((r) => r.id),
                "passed",
              )
            }
          >
            {t(
              "testRuns.resultEntry.markRemainingPassed",
              "Verbleibende als bestanden markieren",
            )}
            {` (${remainingCount})`}
          </button>
          <span className={styles.toolbarSpacer} />
          <button
            type="button"
            className={`${styles.button} ${styles.buttonPrimary}`}
            data-testid="testrun-results-save-all"
            disabled={isBusy || dirtyResults.length === 0}
            onClick={() => void handleSaveAll()}
          >
            {isSavingAll
              ? t("actions.saving", "Speichert...")
              : `${t("testRuns.resultEntry.saveAll", "Alle Änderungen speichern")} (${dirtyResults.length})`}
          </button>
        </div>
      )}

      {saveSuccess && (
        <p
          role="status"
          className={`${styles.banner} ${styles.bannerSuccess}`}
          data-testid="testrun-results-save-success"
        >
          {t("testRuns.resultEntry.saveSuccess", "Ergebnisse gespeichert.")}
        </p>
      )}

      {saveError && (
        <p
          role="alert"
          className={`${styles.banner} ${styles.bannerError}`}
          data-testid="testrun-results-save-error"
        >
          {saveError}
        </p>
      )}

      <table
        className={styles.table}
        data-testid="testrun-results-list"
        aria-label={t("testRuns.testCases", "Testfälle")}
      >
        <thead>
          <tr>
            {editable && (
              <th scope="col" className={`${styles.th} ${styles.thSelect}`}>
                <input
                  type="checkbox"
                  className={styles.checkbox}
                  data-testid="testrun-results-select-all"
                  aria-label={t("testRuns.resultEntry.selectAll", "Alle auswählen")}
                  checked={allSelected}
                  disabled={isBusy || writableResults.length === 0}
                  onChange={(e) => toggleSelectAll(e.target.checked)}
                />
              </th>
            )}
            <th scope="col" className={styles.th}>
              {t("testRuns.resultEntry.columnTestCase", "Testfall")}
            </th>
            <th scope="col" className={styles.th}>
              {t("testRuns.resultEntry.columnCurrentStatus", "Aktueller Status")}
            </th>
            {editable && (
              <>
                <th scope="col" className={styles.th}>
                  {t("testRuns.resultEntry.columnNewStatus", "Neuer Status")}
                </th>
                <th scope="col" className={styles.th}>
                  {t("testRuns.resultEntry.columnNotes", "Notiz")}
                </th>
                <th scope="col" className={styles.th}>
                  {t("testRuns.resultEntry.columnActions", "Aktion")}
                </th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            const draft = drafts[result.id];
            const writable = isWritable(result);
            const dirty = isDirty(result, draft);
            const rowSaving = savingRowId === result.id;
            return (
              <tr
                key={result.id}
                data-testid={`testrun-result-${result.id}`}
                className={dirty ? styles.rowDirty : undefined}
              >
                {editable && (
                  <td className={styles.td}>
                    <input
                      type="checkbox"
                      className={styles.checkbox}
                      data-testid={`testrun-result-select-${result.id}`}
                      aria-label={t("testRuns.resultEntry.selectRow", "Zeile auswählen")}
                      checked={!!selected[result.id]}
                      disabled={isBusy || !writable}
                      onChange={(e) =>
                        setSelected((prev) => ({
                          ...prev,
                          [result.id]: e.target.checked,
                        }))
                      }
                    />
                  </td>
                )}
                <td className={`${styles.td} ${styles.cellTitle}`}>
                  {result.test_case_title || result.test_case_id}
                  {!writable && (
                    <span className={styles.rowError}>
                      {t(
                        "testRuns.resultEntry.missingTestCase",
                        "Zugehöriger Testfall wurde gelöscht — nicht mehr erfassbar.",
                      )}
                    </span>
                  )}
                  {rowErrors[result.id] && (
                    <span
                      role="alert"
                      className={styles.rowError}
                      data-testid={`testrun-result-error-${result.id}`}
                    >
                      {rowErrors[result.id]}
                    </span>
                  )}
                </td>
                <td className={styles.td}>
                  <StatusBadge
                    status={result.status}
                    label={getTestRunStatusLabel(result.status)}
                    testId={`testrun-result-status-${result.id}`}
                  />
                </td>
                {editable && (
                  <>
                    <td className={styles.td}>
                      <select
                        className={styles.select}
                        data-testid={`testrun-result-status-select-${result.id}`}
                        aria-label={t("testRuns.resultEntry.columnNewStatus", "Neuer Status")}
                        value={draft?.status ?? result.status}
                        disabled={isBusy || !writable}
                        onChange={(e) =>
                          setDraft(result.id, {
                            status: e.target.value as TestRunResultStatus,
                          })
                        }
                      >
                        {TEST_RUN_RESULT_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {t(
                              `testRuns.resultEntry.status.${status}`,
                              getTestRunStatusLabel(status),
                            )}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={`${styles.td} ${styles.cellNotes}`}>
                      <input
                        type="text"
                        className={styles.input}
                        data-testid={`testrun-result-notes-${result.id}`}
                        aria-label={t("testRuns.resultEntry.columnNotes", "Notiz")}
                        placeholder={t(
                          "testRuns.resultEntry.notesPlaceholder",
                          "Optionale Notiz...",
                        )}
                        // TestRunResultSerializer caps `message` at 10000 chars.
                        maxLength={10000}
                        value={draft?.message ?? ""}
                        disabled={isBusy || !writable}
                        onChange={(e) =>
                          setDraft(result.id, { message: e.target.value })
                        }
                      />
                    </td>
                    <td className={`${styles.td} ${styles.cellActions}`}>
                      <button
                        type="button"
                        className={styles.button}
                        data-testid={`testrun-result-save-${result.id}`}
                        disabled={isBusy || !writable || !dirty}
                        onClick={() => void handleSaveRow(result)}
                      >
                        {rowSaving
                          ? t("actions.saving", "Speichert...")
                          : t("actions.save", "Speichern")}
                      </button>
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
