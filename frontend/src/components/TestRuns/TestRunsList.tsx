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

import type { CSSProperties } from "react";
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

// REQ-175: TestRun.status choices — see persistence/models.py TestRun.status.
const TEST_RUN_STATUSES = [
  "in_progress",
  "passed",
  "failed",
  "partial",
  "closed",
] as const;

// UI-56: named style objects for the test-case picker's search/select-all
// row, named instead of inline JSX style object literals (ui-ratchet.test.ts
// style-brace ceiling).
const testCasePickerToolbarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
  marginBottom: "var(--space-1)",
};
const testCasePickerSearchStyle: CSSProperties = {
  flex: "1 1 auto",
  padding: "var(--space-1) var(--space-2)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
  background: "var(--color-surface)",
  color: "var(--color-text)",
};
const testCasePickerSelectedCountStyle: CSSProperties = {
  fontSize: "var(--font-size-xs)",
  color: "var(--color-text-muted)",
  margin: "0 0 var(--space-1)",
};
const testCasePickerNoMatchStyle: CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  margin: 0,
};

/** UI-56: select-all label style — cursor depends on whether any row is selectable. */
function selectAllLabelStyle(disabled: boolean): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-1)",
    fontSize: "var(--font-size-sm)",
    color: "var(--color-text)",
    whiteSpace: "nowrap",
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

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
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Test Runs are not a Spine artifact type (no derivation chain), but
          PageHeader/ListToolbar/EmptyState still apply (task 5.2). Unlike
          Baselines, creating a test run is the routine primary action, so it
          stays a primary header button. */}
      <PageHeader
        title={t("nav.testRuns", "Test Runs")}
        summary={t("testRuns.summary", { count: items.length })}
        primaryAction={{
          label: showCreateForm ? t("actions.cancel") : t("testRuns.create", "Create Run"),
          onClick: () =>
            showCreateForm ? handleCancelCreate() : setShowCreateForm(true),
          testId: "testrun-create-btn",
        }}
      />

      <div style={{ flex: "1 1 auto", minHeight: 0 }}>
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
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-2)",
              padding: "var(--space-3)",
              marginBottom: "var(--space-3)",
              background: "var(--color-surface-raised)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <label
              htmlFor="testrun-name"
              style={{
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                color: "var(--color-text)",
              }}
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
              style={{
                padding: "var(--space-2) var(--space-3)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                fontSize: "var(--font-size-sm)",
                fontFamily: "inherit",
                background: "var(--color-surface)",
                color: "var(--color-text)",
                boxSizing: "border-box",
              }}
            />
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                  marginBottom: "var(--space-1)",
                }}
              >
                {t("testRuns.selectTestCases", "Testfälle auswählen")}
              </label>
              {testCaseOptionsLoading ? (
                <p
                  style={{
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                    margin: 0,
                  }}
                >
                  {t("testRuns.testCaseOptionsLoading", "Lade Testfälle...")}
                </p>
              ) : testCaseOptionsError ? (
                <p
                  role="alert"
                  style={{
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-danger)",
                    margin: 0,
                  }}
                >
                  {testCaseOptionsError}
                </p>
              ) : testCaseOptions.length === 0 ? (
                <p
                  data-testid="testrun-create-testcases-empty"
                  style={{
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                    margin: 0,
                  }}
                >
                  {t("testRuns.noTestCases", "Keine Testfälle im Workspace vorhanden")}
                </p>
              ) : (
                <>
                  {/* UI-56: search + select-all were missing, forcing manual
                      one-by-one scrolling/ticking through the full workspace
                      test-case catalog to build a run. */}
                  <div style={testCasePickerToolbarStyle}>
                    <input
                      type="search"
                      data-testid="testrun-create-testcases-search"
                      value={testCaseSearch}
                      onChange={(e) => setTestCaseSearch(e.target.value)}
                      placeholder={t("testRuns.testCaseSearchPlaceholder", "Testfälle filtern...")}
                      disabled={isCreating}
                      style={testCasePickerSearchStyle}
                    />
                    <label
                      htmlFor="testrun-create-testcases-select-all"
                      style={selectAllLabelStyle(visibleTestCaseOptions.length === 0)}
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
                      style={testCasePickerSelectedCountStyle}
                    >
                      {t("testRuns.selectedCount", "{{count}} ausgewählt", {
                        count: selectedTestCaseIds.length,
                      })}
                    </p>
                  )}
                  {visibleTestCaseOptions.length === 0 ? (
                    <p
                      data-testid="testrun-create-testcases-no-match"
                      style={testCasePickerNoMatchStyle}
                    >
                      {t("testRuns.testCaseSearchNoResults", "Keine passenden Testfälle.")}
                    </p>
                  ) : (
                    <div
                      data-testid="testrun-create-testcases-list"
                      style={{
                        maxHeight: "160px",
                        overflowY: "auto",
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-md)",
                        padding: "var(--space-2)",
                        background: "var(--color-surface)",
                      }}
                    >
                      {visibleTestCaseOptions.map((tc) => (
                        <label
                          key={tc.id}
                          htmlFor={`testrun-create-testcase-${tc.id}`}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "var(--space-2)",
                            padding: "var(--space-1) 0",
                            fontSize: "var(--font-size-sm)",
                            color: "var(--color-text)",
                            cursor: "pointer",
                          }}
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
                style={{
                  color: "var(--color-danger)",
                  fontSize: "var(--font-size-sm)",
                  margin: 0,
                }}
              >
                {formError}
              </p>
            )}
            <div
              style={{
                display: "flex",
                gap: "var(--space-2)",
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                data-testid="testrun-create-cancel-btn"
                onClick={handleCancelCreate}
                disabled={isCreating}
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  background: "transparent",
                  color: "var(--color-text-muted)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  cursor: isCreating ? "not-allowed" : "pointer",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {t("actions.cancel")}
              </button>
              <button
                type="submit"
                data-testid="testrun-create-submit-btn"
                disabled={!newName.trim() || isCreating}
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  background: "var(--color-primary)",
                  color: "var(--color-on-primary)",
                  border: "none",
                  borderRadius: "var(--radius-md)",
                  cursor:
                    !newName.trim() || isCreating ? "not-allowed" : "pointer",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  opacity: !newName.trim() || isCreating ? 0.6 : 1,
                }}
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
          <div role="alert" style={{ marginBottom: "var(--space-3)" }}>
            <p
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                marginBottom: "var(--space-2)",
              }}
            >
              {loadError}
            </p>
            <button
              type="button"
              data-testid="testrun-retry-btn"
              onClick={() => void refreshList()}
              style={{
                padding: "var(--space-2) var(--space-3)",
                background: "transparent",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                cursor: "pointer",
                fontSize: "var(--font-size-sm)",
              }}
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
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
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
                  style={{
                    padding: "var(--space-3) var(--space-3)",
                    marginBottom: "var(--space-2)",
                    background: isSelected
                      ? "var(--color-primary)"
                      : "var(--color-surface)",
                    color: isSelected ? "var(--color-on-primary)" : "var(--color-text)",
                    borderRadius: "var(--radius-md)",
                    border: isSelected
                      ? `1px solid var(--color-primary)`
                      : "1px solid var(--color-border)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      (e.currentTarget as HTMLLIElement).style.borderColor =
                        "var(--color-border-hover)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      (e.currentTarget as HTMLLIElement).style.borderColor =
                        "var(--color-border)";
                    }
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: "var(--space-2)",
                    }}
                  >
                    <strong>{item.name}</strong>
                    <StatusBadge status={item.status} label={getTestRunStatusLabel(item.status)} />
                  </div>
                  {item.ci_job_id && (
                    <p
                      style={{
                        margin: 0,
                        marginTop: "var(--space-1)",
                        fontSize: "var(--font-size-sm)",
                        opacity: 0.7,
                      }}
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
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              textAlign: "center",
              padding: "var(--space-8)",
            }}
          >
            {t("testRuns.selectPrompt", "Select a test run to view details")}
          </p>
          )
        }
      />
      </div>
    </div>
  );
}
