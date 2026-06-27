/**
 * ARCH-L1-001 ReactFrontend — Test Runs view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-AS-030 (Test-Run-Protokollierung)
 *
 * Lists all TestRuns for the active workspace with detail view on select.
 */

import { useState, useEffect } from "react";
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
// TestRuns component
// ---------------------------------------------------------------------------

export default function TestRuns(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TestRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<TestRun | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newRunName, setNewRunName] = useState("");

  // ---- Load list ----
  useEffect(() => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    testRunsApi
      .list(activeWorkspace.id)
      .then((resp) => setItems(resp.results))
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [activeWorkspace]);

  // ---- Load detail ----
  useEffect(() => {
    if (!selectedId) {
      setSelectedRun(null);
      return;
    }
    testRunsApi
      .get(selectedId)
      .then((run) => setSelectedRun(run))
      .catch(console.error);
  }, [selectedId]);

  // ---- Create test run ----
  const handleCreate = async (): Promise<void> => {
    if (!activeWorkspace || !newRunName.trim()) return;
    try {
      await testRunsApi.create({
        workspace_id: activeWorkspace.id,
        name: newRunName.trim(),
      });
      setNewRunName("");
      setShowCreateForm(false);
      const resp = await testRunsApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error("Failed to create test run", err);
    }
  };

  // ---- Close test run ----
  const handleClose = async (): Promise<void> => {
    if (!selectedId) return;
    try {
      await testRunsApi.close(selectedId);
      const run = await testRunsApi.get(selectedId);
      setSelectedRun(run);
      if (activeWorkspace) {
        const resp = await testRunsApi.list(activeWorkspace.id);
        setItems(resp.results);
      }
    } catch (err) {
      console.error("Failed to close test run", err);
    }
  };

  if (!activeWorkspace) {
    return <p>{t("workspace.selectPrompt")}</p>;
  }

  if (isLoading) return <p>{t("loading")}</p>;

  // ---- Detail view ----
  if (selectedId) {
    return (
      <div>
        <button
          type="button"
          onClick={() => setSelectedId(null)}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-primary)",
            cursor: "pointer",
            fontSize: "var(--font-size-sm)",
            padding: 0,
            marginBottom: "var(--space-4)",
            fontFamily: "inherit",
          }}
        >
          &larr; {t("actions.back", "Back")}
        </button>

        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            marginTop: 0,
            marginBottom: "var(--space-2)",
          }}
        >
          {selectedRun?.name || "..."}
        </h2>

        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            alignItems: "center",
            marginBottom: "var(--space-6)",
          }}
        >
          <StatusBadge status={selectedRun?.status || "in_progress"} />
          {selectedRun?.ci_job_id && (
            <span
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-text-muted)",
              }}
            >
              CI: {selectedRun.ci_job_id}
            </span>
          )}
        </div>

        {/* Summary */}
        {selectedRun?.result_summary && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "var(--space-3)",
              marginBottom: "var(--space-6)",
            }}
          >
            {[
              { label: "Total", value: selectedRun.result_summary.total, color: "var(--color-text)" },
              { label: "Passed", value: selectedRun.result_summary.passed, color: "#22c55e" },
              { label: "Failed", value: selectedRun.result_summary.failed, color: "#ef4444" },
              { label: "Not Run", value: selectedRun.result_summary.not_run, color: "#64748b" },
            ].map((s) => (
              <div
                key={s.label}
                style={{
                  padding: "var(--space-3)",
                  background: "var(--color-surface)",
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

        {/* Actions */}
        {selectedRun?.status === "in_progress" && (
          <button
            type="button"
            onClick={handleClose}
            style={{
              padding: "var(--space-2) var(--space-4)",
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              fontFamily: "inherit",
              marginBottom: "var(--space-6)",
            }}
          >
            {t("testRuns.closeRun", "Close Test Run")}
          </button>
        )}
      </div>
    );
  }

  // ---- List view ----
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "var(--space-6)",
        }}
      >
        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            margin: 0,
          }}
        >
          {t("nav.testRuns", "Test Runs")}
        </h2>
        <button
          type="button"
          onClick={() => setShowCreateForm(true)}
          style={{
            padding: "var(--space-2) var(--space-4)",
            background: "var(--color-primary)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            fontFamily: "inherit",
          }}
        >
          + {t("testRuns.create", "Create Run")}
        </button>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <div
          style={{
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--color-border)",
            display: "flex",
            gap: "var(--space-3)",
            alignItems: "center",
          }}
        >
          <input
            type="text"
            value={newRunName}
            onChange={(e) => setNewRunName(e.target.value)}
            placeholder={t("testRuns.namePlaceholder", "Run name...")}
            autoFocus
            style={{
              flex: 1,
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              fontSize: "var(--font-size-sm)",
              fontFamily: "inherit",
            }}
          />
          <button
            type="button"
            onClick={handleCreate}
            disabled={!newRunName.trim()}
            style={{
              padding: "var(--space-2) var(--space-4)",
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: newRunName.trim() ? "pointer" : "not-allowed",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              fontFamily: "inherit",
              opacity: newRunName.trim() ? 1 : 0.6,
            }}
          >
            {t("actions.create", "Create")}
          </button>
          <button
            type="button"
            onClick={() => setShowCreateForm(false)}
            style={{
              padding: "var(--space-2) var(--space-4)",
              background: "transparent",
              color: "var(--color-text-muted)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "var(--font-size-sm)",
              fontFamily: "inherit",
            }}
          >
            {t("actions.cancel", "Cancel")}
          </button>
        </div>
      )}

      {/* Empty state */}
      {items.length === 0 ? (
        <p
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("testRuns.empty", "No test runs yet. Create one to get started.")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              style={{
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                transition: "var(--transition-fast)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor =
                  "var(--color-primary)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor =
                  "var(--color-border)";
              }}
            >
              <div>
                <strong>{item.name}</strong>
                {item.ci_job_id && (
                  <span
                    style={{
                      marginLeft: "var(--space-2)",
                      fontSize: "0.75rem",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    CI: {item.ci_job_id}
                  </span>
                )}
              </div>
              <StatusBadge status={item.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
