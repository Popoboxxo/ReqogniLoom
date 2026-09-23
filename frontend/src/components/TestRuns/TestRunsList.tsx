/**
 * ARCH-L1-001 ReactFrontend — TestRunsList (COMP-RF-003) — Container.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-040 (Unified Split-View Mask Pattern), REQ-L2-AS-030 (Test-Run-Protokollierung),
 *          REQ-050 (Container/Presenter decomposition)
 *
 * Container for the Test Runs split-view. Owns only UI state (selection, create
 * form fields); all data-fetching lives in useTestRunsData (TanStack Query) and
 * the detail view is the TestRunDetailEditor presenter.
 *
 * Left panel: scrollable list with create button. Right panel: detail editor.
 * Resizable divider between panels (REQ-002 Masken-Standardisierung).
 */

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { ListToolbar } from "../shared/ListToolbar";
import { EmptyState } from "../shared/EmptyState/EmptyState";
import { Dialog } from "../shared/Dialog";
import { StatusBadge } from "../shared/StatusBadge";
import { TestRunDetailEditor } from "./TestRunDetailEditor";
import { getTestRunStatusLabel } from "./testRunStatusLabel";
import { useTestRunsData } from "./useTestRunsData";
import styles from "./TestRunsList.module.css";

// REQ-175: TestRun.status choices — see persistence/models.py TestRun.status.
const TEST_RUN_STATUSES = [
  "in_progress",
  "passed",
  "failed",
  "partial",
  "closed",
] as const;

export function TestRunsList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [listSearch, setListSearch] = useState<string>("");
  // UI-56: the create-run test-case picker had no way to filter or bulk-select
  // from a workspace's full test-case catalog.
  const [testCaseSearch, setTestCaseSearch] = useState<string>("");

  const {
    items,
    isLoading,
    loadError,
    selectedRun,
    updateSelectedRun,
    refreshList,
    testCaseOptions,
    testCaseOptionsLoading,
    testCaseOptionsError,
    createTestRun,
    isCreating,
    createError,
    resetCreateError,
  } = useTestRunsData(selectedId, showCreateForm);

  // REQ-175: client-side status filter over the loaded runs.
  const visibleItems = items.filter((item) => {
    if (statusFilter && item.status !== statusFilter) return false;
    if (
      listSearch.trim() &&
      !item.name.toLowerCase().includes(listSearch.trim().toLowerCase())
    ) {
      return false;
    }
    return true;
  });
  const hasActiveListControls = Boolean(statusFilter || listSearch);

  const resetListFilters = (): void => {
    setStatusFilter("");
    setListSearch("");
  };

  const resetCreateForm = (): void => {
    setNewName("");
    setValidationError(null);
    setSelectedTestCaseIds([]);
    setTestCaseSearch("");
    resetCreateError();
  };

  // UI-56: filtered view of the workspace's test cases for the picker below.
  const visibleTestCaseOptions = testCaseOptions.filter(
    (tc) =>
      !testCaseSearch.trim() ||
      tc.title.toLowerCase().includes(testCaseSearch.trim().toLowerCase()),
  );
  const allVisibleSelected =
    visibleTestCaseOptions.length > 0 &&
    visibleTestCaseOptions.every((tc) => selectedTestCaseIds.includes(tc.id));

  const toggleSelectAllVisible = (): void => {
    setSelectedTestCaseIds((prev) => {
      if (allVisibleSelected) {
        const visibleIds = new Set(visibleTestCaseOptions.map((tc) => tc.id));
        return prev.filter((id) => !visibleIds.has(id));
      }
      const merged = new Set(prev);
      for (const tc of visibleTestCaseOptions) merged.add(tc.id);
      return Array.from(merged);
    });
  };

  // F-08 (Dialog migration): Escape / backdrop click / × must discard the
  // draft exactly like the existing Cancel button.
  const handleCancelCreate = (): void => {
    resetCreateForm();
    setShowCreateForm(false);
  };

  // F-08: preserve the previous `autoFocus` UX — Dialog's focus trap
  // defaults to the first focusable element in the panel (its own × close
  // button) unless told otherwise.
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  const toggleTestCaseSelection = (id: string): void => {
    setSelectedTestCaseIds((prev) =>
      prev.includes(id) ? prev.filter((tcId) => tcId !== id) : [...prev, id],
    );
  };

  const handleCreate = async (
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!newName.trim()) {
      setValidationError("Name is required");
      return;
    }
    setValidationError(null);
    try {
      await createTestRun({
        workspace_id: activeWorkspace.id,
        name: newName.trim(),
        ...(selectedTestCaseIds.length > 0
          ? { test_case_ids: selectedTestCaseIds }
          : {}),
      });
      resetCreateForm();
      setShowCreateForm(false);
    } catch {
      // Error surfaced via createError from the mutation.
    }
  };

  const formError = validationError ?? createError;

  if (!activeWorkspace) {
    return <p>{t("workspace.selectPrompt")}</p>;
  }

  if (isLoading) {
    return <p role="status">{t("loading")}</p>;
  }

  return (
    <div className={styles.page}>
      {/* Test Runs are not a Spine artifact type (no derivation chain), but
          PageHeader/ListToolbar/EmptyState still apply (task 5.2). Unlike
          Baselines, creating a test run is the routine primary action, so it
          stays a primary header button.

          #797: the label used to flip to "Cancel" while the create dialog was
          open, which made this the one primary create action that could not
          read "+ New Test Run". The three sibling routes that keep their form
          open in the page all disable the trigger instead (Architecture,
          Goals, Needs) and leave cancelling to the form's own Cancel button —
          which this dialog already has (`testrun-create-cancel-btn`). */}
      <PageHeader
        title={t("nav.testRuns", "Test Runs")}
        summary={t("testRuns.summary", { count: items.length })}
        primaryAction={{
          label: t("testRuns.create", "Create Run"),
          prefixWithPlus: true,
          onClick: () => setShowCreateForm(true),
          disabled: showCreateForm,
          testId: "testrun-create-btn",
        }}
      />

      <div className={styles.content}>
      <SplitView
        moduleType="testruns"
        leftMinWidth={260}
        leftPanel={
          <>
        {/* REQ-175: search + status filter */}
        <ListToolbar
          testIdPrefix="testrun-list"
          searchValue={listSearch}
          onSearchChange={setListSearch}
          searchPlaceholder={t("editor.searchPlaceholder", "Search...")}
          filters={[
            {
              id: "status",
              allLabel: t("editor.allStatuses", "All Statuses"),
              value: statusFilter,
              options: TEST_RUN_STATUSES.map((s) => ({
                value: s,
                label: t(`testRuns.status.${s}`, s),
              })),
              onChange: setStatusFilter,
            },
          ]}
          countLabel={
            hasActiveListControls
              ? t("editor.filteredCount", {
                  shown: visibleItems.length,
                  total: items.length,
                })
              : String(items.length)
          }
        />

        {/* Create form — F-08: wrapped in the shared Dialog primitive so it
            gets a real focus trap and Escape-to-close (GESAMTTEST_BERICHT
            2026-08-21 §5 finding 8); the form markup itself is unchanged. */}
        {showCreateForm && (
          <Dialog
            title={t("testRuns.create", "Create Run")}
            onClose={handleCancelCreate}
            initialFocusRef={nameInputRef}
            testId="testrun-create-dialog"
          >
          <form
            data-testid="testrun-create-form"
            onSubmit={(e) => void handleCreate(e)}
            className={styles.createForm}
          >
            <label
              htmlFor="testrun-name"
              className={styles.formLabel}
            >
              {t("editor.name", "Name")} *
            </label>
            <input
              id="testrun-name"
              data-testid="testrun-name-input"
              ref={nameInputRef}
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Test run name"
              autoFocus
              required
              disabled={isCreating}
              className={styles.nameInput}
            />
            <div>
              <label
                className={styles.pickerLabel}
              >
                {t("testRuns.selectTestCases", "Testfälle auswählen")}
              </label>
              {testCaseOptionsLoading ? (
                <p
                  className={styles.pickerHint}
                >
                  {t("testRuns.testCaseOptionsLoading", "Lade Testfälle...")}
                </p>
              ) : testCaseOptionsError ? (
                <p
                  role="alert"
                  className={styles.pickerError}
                >
                  {testCaseOptionsError}
                </p>
              ) : testCaseOptions.length === 0 ? (
                <p
                  data-testid="testrun-create-testcases-empty"
                  className={styles.pickerHint}
                >
                  {t("testRuns.noTestCases", "Keine Testfälle im Workspace vorhanden")}
                </p>
              ) : (
                <>
                  {/* UI-56: search + select-all were missing, forcing manual
                      one-by-one scrolling/ticking through the full workspace
                      test-case catalog to build a run. */}
                  <div className={styles.pickerToolbar}>
                    <input
                      type="search"
                      data-testid="testrun-create-testcases-search"
                      value={testCaseSearch}
                      onChange={(e) => setTestCaseSearch(e.target.value)}
                      placeholder={t("testRuns.testCaseSearchPlaceholder", "Testfälle filtern...")}
                      disabled={isCreating}
                      className={styles.pickerSearch}
                    />
                    <label
                      htmlFor="testrun-create-testcases-select-all"
                      className={`${styles.selectAllLabel} ${visibleTestCaseOptions.length === 0 ? styles.selectAllLabelDisabled : styles.selectAllLabelEnabled}`}
                    >
                      <input
                        id="testrun-create-testcases-select-all"
                        data-testid="testrun-create-testcases-select-all"
                        type="checkbox"
                        checked={allVisibleSelected}
                        onChange={toggleSelectAllVisible}
                        disabled={isCreating || visibleTestCaseOptions.length === 0}
                      />
                      {t("testRuns.selectAllTestCases", "Alle auswählen")}
                    </label>
                  </div>
                  {selectedTestCaseIds.length > 0 && (
                    <p
                      data-testid="testrun-create-testcases-selected-count"
                      className={styles.pickerSelectedCount}
                    >
                      {t("testRuns.selectedCount", "{{count}} ausgewählt", {
                        count: selectedTestCaseIds.length,
                      })}
                    </p>
                  )}
                  {visibleTestCaseOptions.length === 0 ? (
                    <p
                      data-testid="testrun-create-testcases-no-match"
                      className={styles.pickerNoMatch}
                    >
                      {t("testRuns.testCaseSearchNoResults", "Keine passenden Testfälle.")}
                    </p>
                  ) : (
                    <div
                      data-testid="testrun-create-testcases-list"
                      className={styles.pickerList}
                    >
                      {visibleTestCaseOptions.map((tc) => (
                        <label
                          key={tc.id}
                          htmlFor={`testrun-create-testcase-${tc.id}`}
                          className={styles.pickerItem}
                        >
                          <input
                            id={`testrun-create-testcase-${tc.id}`}
                            data-testid={`testrun-create-testcase-${tc.id}`}
                            type="checkbox"
                            checked={selectedTestCaseIds.includes(tc.id)}
                            onChange={() => toggleTestCaseSelection(tc.id)}
                            disabled={isCreating}
                          />
                          {tc.title}
                        </label>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            {formError && (
              <p
                role="alert"
                className={styles.pickerError}
              >
                {formError}
              </p>
            )}
            <div
              className={styles.formActions}
            >
              <button
                type="button"
                data-testid="testrun-create-cancel-btn"
                onClick={handleCancelCreate}
                disabled={isCreating}
                className={`${styles.cancelBtn} ${isCreating ? styles.cancelBtnDisabled : styles.cancelBtnEnabled}`}
              >
                {t("actions.cancel")}
              </button>
              <button
                type="submit"
                data-testid="testrun-create-submit-btn"
                disabled={!newName.trim() || isCreating}
                className={`${styles.submitBtn} ${!newName.trim() || isCreating ? styles.submitBtnDisabled : styles.submitBtnEnabled}`}
              >
                {isCreating
                  ? t("actions.creating", "Creating...")
                  : t("actions.create")}
              </button>
            </div>
          </form>
          </Dialog>
        )}

        {/* Load error */}
        {loadError && (
          <div role="alert" className={styles.loadError}>
            <p
              className={styles.loadErrorText}
            >
              {loadError}
            </p>
            <button
              type="button"
              data-testid="testrun-retry-btn"
              onClick={() => void refreshList()}
              className={styles.retryBtn}
            >
              {t("actions.retry")}
            </button>
          </div>
        )}

        {/* List */}
        {visibleItems.length === 0 ? (
          items.length === 0 ? (
            // ch. 13.3: "there is nothing" — offer the create action.
            <EmptyState
              variant="empty"
              testId="testrun-list-empty"
              title={t("testRuns.emptyTitle", "No test runs yet")}
              description={t(
                "testRuns.emptyDescription",
                "Test runs record the execution of your test cases against a build.",
              )}
              actions={[
                {
                  label: t("testRuns.create", "Create Run"),
                  prefixWithPlus: true,
                  onClick: () => setShowCreateForm(true),
                  testId: "testrun-list-empty-create",
                },
              ]}
            />
          ) : (
            // ch. 13.3: "there is something, just not under this filter" —
            // offer only a filter reset, never a create action.
            <EmptyState
              variant="no-match"
              testId="testrun-list-no-match"
              onResetFilters={resetListFilters}
            />
          )
        ) : (
          <ul className={styles.list}>
            {visibleItems.map((item) => {
              const isSelected = selectedId === item.id;
              return (
                <li
                  key={item.id}
                  data-testid={`testrun-item-${item.id}`}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  onClick={() => setSelectedId(item.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedId(item.id);
                    }
                  }}
                  className={`${styles.item} ${isSelected ? styles.itemSelected : ""}`}
                >
                  <div
                    className={styles.itemHeader}
                  >
                    <strong>{item.name}</strong>
                    <StatusBadge status={item.status} label={getTestRunStatusLabel(item.status)} />
                  </div>
                  {item.ci_job_id && (
                    <p
                      className={styles.itemCi}
                    >
                      CI: {item.ci_job_id}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
          </>
        }
        rightPanel={
          selectedRun ? (
          <TestRunDetailEditor
            key={selectedRun.id}
            testRun={selectedRun}
            onClose={() => setSelectedId(null)}
            onRefresh={refreshList}
            onUpdated={updateSelectedRun}
          />
        ) : (
          <p
            className={styles.selectPrompt}
          >
            {t("testRuns.selectPrompt", "Select a test run from the list to view details.")}
          </p>
          )
        }
      />
      </div>
    </div>
  );
}
