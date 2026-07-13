/**
 * ARCH-L1-001 ReactFrontend — TestRunsList (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-040 (Unified Split-View Mask Pattern), REQ-L2-AS-030 (Test-Run-Protokollierung)
 *
 * Lists all Test Runs for the active workspace in a split-view layout.
 * Left panel: scrollable list with create button. Right panel: detail editor (when selected).
 * Resizable divider between panels (REQ-002 Masken-Standardisierung).
 */

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { testRunsApi } from "../../api/test-runs";
import { testcasesApi } from "../../api/testcases";
import type { TestCase } from "../../api/testcases";
import { SplitView } from "../SplitView/SplitView";
import { VersionBadge } from "../shared/VersionBadge";
import { getStatusBadgeStyle } from "../../utils/statusBadge";
import type { TestRun, TestRunResult } from "../../types";

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }): JSX.Element {
  // Shared token-based colors; keep the uppercase pill look specific to test runs.
  return (
    <span
      style={{
        ...getStatusBadgeStyle(status),
        display: "inline-block",
        borderRadius: "var(--radius-sm)",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// TestRun Detail Editor (right panel)
// ---------------------------------------------------------------------------

interface TestRunDetailEditorProps {
  testRun: TestRun;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onUpdated: (run: TestRun) => void;
}

function TestRunDetailEditor({
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
  }, [testRun.id, t]);

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
          <StatusBadge status={testRun.status} />
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
              color: "#22c55e",
            },
            {
              label: "Failed",
              value: testRun.result_summary.failed,
              color: "#ef4444",
            },
            {
              label: "Not Run",
              value: testRun.result_summary.not_run,
              color: "#64748b",
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
          <ul
            data-testid="testrun-results-list"
            style={{ listStyle: "none", padding: 0, margin: 0 }}
          >
            {results.map((result) => (
              <li
                key={result.id}
                data-testid={`testrun-result-${result.id}`}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  padding: "var(--space-2) var(--space-3)",
                  marginBottom: "var(--space-2)",
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                }}
              >
                <span style={{ color: "var(--color-text)" }}>
                  {result.test_case_title || result.test_case_id}
                </span>
                <StatusBadge status={result.status} />
              </li>
            ))}
          </ul>
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
                color: "white",
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
                {t("testRuns.closeConfirm", "Close this test run?")}
              </span>
              <button
                type="button"
                data-testid="testrun-confirm-close-btn"
                onClick={() => void handleClose()}
                disabled={isClosing}
                style={{
                  padding: "var(--space-2) var(--space-4)",
                  background: "var(--color-primary)",
                  color: "white",
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

// ---------------------------------------------------------------------------
// TestRunsList — main split-view component
// ---------------------------------------------------------------------------

export function TestRunsList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<TestRun | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [testCaseOptions, setTestCaseOptions] = useState<TestCase[]>([]);
  const [testCaseOptionsLoading, setTestCaseOptionsLoading] = useState(false);
  const [testCaseOptionsError, setTestCaseOptionsError] = useState<string | null>(null);
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<string[]>([]);
  // `silent=true` refreshes the list in the background without flipping the
  // full-page isLoading flag — used after closing a run so the detail panel
  // (and its success/error feedback) stays mounted instead of being replaced
  // by the "loading" placeholder mid-interaction (REQ-012).
  const loadList = async (silent = false): Promise<void> => {
    if (!activeWorkspace) return;
    if (!silent) setIsLoading(true);
    setLoadError(null);
    try {
      const resp = await testRunsApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error("Failed to load test runs:", err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t("testRuns.loadFailed", "Test-Runs konnten nicht geladen werden.");
      setLoadError(msg);
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedRun(null);
      return;
    }
    testRunsApi
      .get(selectedId)
      .then((run) => setSelectedRun(run))
      .catch((err) => {
        console.error("Failed to load test run detail:", err);
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          t("testRuns.detailLoadFailed", "Test-Run konnte nicht geladen werden.");
        setLoadError(msg);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const resetCreateForm = (): void => {
    setNewName("");
    setCreateError(null);
    setSelectedTestCaseIds([]);
  };

  // Load the workspace's test cases when the create form opens so they can
  // be assigned to the new run right away (C4) — avoids a second trip via
  // addResult after creation.
  useEffect(() => {
    if (!showCreateForm || !activeWorkspace) return;
    setTestCaseOptionsLoading(true);
    setTestCaseOptionsError(null);
    testcasesApi
      .list(activeWorkspace.id)
      .then((resp) => setTestCaseOptions(resp.results))
      .catch((err) => {
        console.error("Failed to load test cases:", err);
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          t("testRuns.testCaseOptionsLoadFailed", "Testfälle konnten nicht geladen werden.");
        setTestCaseOptionsError(msg);
      })
      .finally(() => setTestCaseOptionsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showCreateForm, activeWorkspace]);

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
      setCreateError("Name is required");
      return;
    }
    setIsCreating(true);
    setCreateError(null);
    try {
      await testRunsApi.create({
        workspace_id: activeWorkspace.id,
        name: newName.trim(),
        ...(selectedTestCaseIds.length > 0
          ? { test_case_ids: selectedTestCaseIds }
          : {}),
      });
      resetCreateForm();
      setShowCreateForm(false);
      await loadList();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setCreateError(msg);
    } finally {
      setIsCreating(false);
    }
  };

  if (!activeWorkspace) {
    return <p>{t("workspace.selectPrompt")}</p>;
  }

  if (isLoading) {
    return <p>{t("loading")}</p>;
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
            {createError && (
              <p
                role="alert"
                style={{
                  color: "var(--color-danger)",
                  fontSize: "var(--font-size-sm)",
                  margin: 0,
                }}
              >
                {createError}
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
              onClick={() => void loadList()}
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
        {items.length === 0 ? (
          <p
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              marginTop: "var(--space-4)",
            }}
          >
            {t("testRuns.empty", "No test runs yet")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => {
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
            onRefresh={() => loadList(true)}
            onUpdated={setSelectedRun}
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
