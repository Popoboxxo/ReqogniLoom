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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { SplitView } from "../SplitView/SplitView";
import { StatusBadge } from "./StatusBadge";
import { TestRunDetailEditor } from "./TestRunDetailEditor";
import { useTestRunsData } from "./useTestRunsData";

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
  const visibleItems = statusFilter
    ? items.filter((item) => item.status === statusFilter)
    : items;

  const resetCreateForm = (): void => {
    setNewName("");
    setValidationError(null);
    setSelectedTestCaseIds([]);
    resetCreateError();
  };

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
    <div style={{ height: "100%" }}>
      <SplitView
        moduleType="testruns"
        leftMinWidth={260}
        leftPanel={
          <>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--space-4)",
          }}
        >
          <h2
            style={{
              fontSize: "var(--font-size-lg)",
              fontWeight: 700,
              color: "var(--color-text)",
              margin: 0,
            }}
          >
            {t("nav.testRuns", "Test Runs")}
          </h2>
          <button
            type="button"
            data-testid="testrun-create-btn"
            onClick={() =>
              showCreateForm
                ? (resetCreateForm(), setShowCreateForm(false))
                : setShowCreateForm(true)
            }
            style={{
              padding: "var(--space-2) var(--space-3)",
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
            }}
          >
            {showCreateForm ? t("actions.cancel") : `+ ${t("actions.new")}`}
          </button>
        </div>

        {/* REQ-175: status filter */}
        <div style={{ marginBottom: "var(--space-3)" }}>
          <label htmlFor="testrun-status-filter" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
            {t("editor.allStatuses", "All Statuses")}
          </label>
          <select
            id="testrun-status-filter"
            data-testid="testrun-status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              width: "100%",
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              fontSize: "var(--font-size-sm)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
              boxSizing: "border-box",
            }}
          >
            <option value="">{t("editor.allStatuses", "All Statuses")}</option>
            {TEST_RUN_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`testRuns.status.${s}`, s)}
              </option>
            ))}
          </select>
        </div>

        {/* Create form */}
        {showCreateForm && (
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
                  {testCaseOptions.map((tc) => (
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
                onClick={() => {
                  resetCreateForm();
                  setShowCreateForm(false);
                }}
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
                  color: "white",
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
              {t("actions.reload", "Erneut versuchen")}
            </button>
          </div>
        )}

        {/* List */}
        {visibleItems.length === 0 ? (
          <p
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              marginTop: "var(--space-4)",
            }}
          >
            {statusFilter
              ? t("editor.noMatches", "No matches found.")
              : t("testRuns.empty", "No test runs yet")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {visibleItems.map((item) => {
              const isSelected = selectedId === item.id;
              return (
                <li
                  key={item.id}
                  data-testid={`testrun-item-${item.id}`}
                  onClick={() => setSelectedId(item.id)}
                  style={{
                    padding: "var(--space-3) var(--space-3)",
                    marginBottom: "var(--space-2)",
                    background: isSelected
                      ? "var(--color-primary)"
                      : "var(--color-surface)",
                    color: isSelected ? "white" : "var(--color-text)",
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
                    <StatusBadge status={item.status} />
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
  );
}
