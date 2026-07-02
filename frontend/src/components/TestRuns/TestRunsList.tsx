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

import React, { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { testRunsApi } from "../../api/test-runs";
import type { TestRun } from "../../types";

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  in_progress: { bg: "rgba(59,130,246,0.15)", color: "#3b82f6" },
  passed: { bg: "rgba(34,197,94,0.15)", color: "#22c55e" },
  failed: { bg: "rgba(239,68,68,0.15)", color: "#ef4444" },
  partial: { bg: "rgba(234,179,8,0.15)", color: "#eab308" },
};

function StatusBadge({ status }: { status: string }): JSX.Element {
  const colors = STATUS_COLORS[status] || {
    bg: "rgba(100,116,139,0.15)",
    color: "#64748b",
  };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px var(--space-2)",
        borderRadius: "var(--radius-sm)",
        background: colors.bg,
        color: colors.color,
        fontSize: "0.75rem",
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
}

function TestRunDetailEditor({
  testRun,
  onClose,
  onRefresh,
}: TestRunDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [isClosing, setIsClosing] = useState(false);

  const handleClose = async (): Promise<void> => {
    if (!window.confirm(t("testRuns.closeConfirm", "Close this test run?")))
      return;
    setIsClosing(true);
    try {
      await testRunsApi.close(testRun.id);
      await onRefresh();
      onClose();
    } catch (err) {
      console.error("Failed to close test run:", err);
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

      {/* Actions */}
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        {testRun.status === "in_progress" && (
          <button
            type="button"
            data-testid="testrun-close-btn"
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
              : t("testRuns.closeRun", "Close Run")}
          </button>
        )}
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<TestRun | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // Split-pane resize state
  const [leftPanelWidth, setLeftPanelWidth] = useState(260);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  const loadList = async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await testRunsApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error("Failed to load test runs:", err);
    } finally {
      setIsLoading(false);
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
      .catch((err) => console.error("Failed to load test run detail:", err));
  }, [selectedId]);

  const resetCreateForm = (): void => {
    setNewName("");
    setCreateError(null);
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

  // Split-pane resize handlers
  const handleDividerMouseDown = (e: React.MouseEvent): void => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = leftPanelWidth;
    e.preventDefault();
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent): void => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      const newWidth = Math.max(260, dragStartWidthRef.current + delta);
      setLeftPanelWidth(newWidth);
    };

    const handleMouseUp = (): void => {
      isDraggingRef.current = false;
    };

    if (isDraggingRef.current) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [leftPanelWidth]);

  if (!activeWorkspace) {
    return <p>{t("workspace.selectPrompt")}</p>;
  }

  if (isLoading) {
    return <p>{t("loading")}</p>;
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left panel: Test Runs list */}
      <div
        style={{
          width: `${leftPanelWidth}px`,
          minWidth: "260px",
          maxWidth: "70%",
          overflow: "auto",
          padding: "var(--space-4)",
          borderRight: "1px solid var(--color-border)",
        }}
      >
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
      </div>

      {/* Divider for split-pane resize */}
      <div
        onMouseDown={handleDividerMouseDown}
        data-testid="testrun-list-divider"
        style={{
          width: "4px",
          backgroundColor: "var(--color-border)",
          cursor: "col-resize",
          userSelect: "none",
          transition: isDraggingRef.current
            ? "none"
            : "background-color var(--transition-fast)",
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor =
            "var(--color-border-hover)";
        }}
        onMouseLeave={(e) => {
          if (!isDraggingRef.current) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor =
              "var(--color-border)";
          }
        }}
      />

      {/* Right panel: Detail editor */}
      <div style={{ flex: 1, overflow: "auto", padding: "var(--space-4)" }}>
        {selectedRun ? (
          <TestRunDetailEditor
            key={selectedRun.id}
            testRun={selectedRun}
            onClose={() => setSelectedId(null)}
            onRefresh={loadList}
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
        )}
      </div>
    </div>
  );
}
