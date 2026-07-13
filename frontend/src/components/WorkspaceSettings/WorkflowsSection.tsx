/**
 * ARCH-L1-001 ReactFrontend — WorkflowsSection (WorkspaceSettings).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L2-RA-001 (WorkflowDefinition endpoints)
 *
 * Surfaces the /api/v1/workflows/ endpoints:
 *   - initialize workflow states for an artifact (POST /workflows/)
 *   - transition an entity's workflow state (PATCH /workflows/<id>/)
 *
 * Backend contract note: GET /workflows/ always returns an empty result set
 * (the WorkflowFacade exposes no list operation) and DELETE is rejected —
 * this section therefore only offers the two supported operations.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { workflowsApi } from "../../api/workflows";
import { artifactsApi } from "../../api/artifacts";
import type { Artifact, UUID } from "../../types";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const sectionStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const subHeadingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-base)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-2) 0",
};

const inputStyle: React.CSSProperties = {
  background: "var(--color-bg)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  boxSizing: "border-box",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

export interface WorkflowsSectionProps {
  workspaceId: UUID;
}

export function WorkflowsSection({
  workspaceId,
}: WorkflowsSectionProps): JSX.Element {
  const { t } = useTranslation();
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Initialize form
  const [initArtifactId, setInitArtifactId] = useState("");
  const [initName, setInitName] = useState("");
  const [isInitializing, setIsInitializing] = useState(false);

  // Transition form
  const [transitionEntityId, setTransitionEntityId] = useState("");
  const [targetState, setTargetState] = useState("");
  const [changeReason, setChangeReason] = useState("");
  const [isTransitioning, setIsTransitioning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    artifactsApi
      .list(workspaceId)
      .then((resp) => {
        if (!cancelled) setArtifacts(resp.results);
      })
      .catch((err) => {
        if (!cancelled) setError(extractErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const handleInitialize = useCallback(async (): Promise<void> => {
    if (!initArtifactId || !initName.trim()) return;
    setIsInitializing(true);
    setError(null);
    setStatusMessage(null);
    try {
      const resp = await workflowsApi.initialize({
        workspace_id: workspaceId,
        artifact_id: initArtifactId,
        name: initName.trim(),
      });
      setStatusMessage(
        resp.message ||
          t("workflows.initialized", "Workflow initialized for artifact.")
      );
      setInitName("");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsInitializing(false);
    }
  }, [workspaceId, initArtifactId, initName, t]);

  const handleTransition = useCallback(async (): Promise<void> => {
    if (!transitionEntityId || !targetState.trim()) return;
    setIsTransitioning(true);
    setError(null);
    setStatusMessage(null);
    try {
      const resp = await workflowsApi.transition(
        transitionEntityId,
        targetState.trim(),
        changeReason.trim() || undefined
      );
      setStatusMessage(
        t("workflows.transitioned", {
          defaultValue: "State transitioned to {{state}}.",
          state: resp.target_state,
        })
      );
      setTargetState("");
      setChangeReason("");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsTransitioning(false);
    }
  }, [transitionEntityId, targetState, changeReason, t]);

  return (
    <section style={sectionStyle} data-testid="workflows-section">
      <h3 style={headingStyle}>{t("workflows.title", "Workflows")}</h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginTop: 0,
          marginBottom: "var(--space-4)",
        }}
      >
        {t(
          "workflows.hint",
          "Initialize workflow states for an artifact or transition an artifact's workflow state. Available states depend on the workspace preset."
        )}
      </p>

      {/* Initialize workflow */}
      <div style={{ marginBottom: "var(--space-5)" }}>
        <h4 style={subHeadingStyle}>
          {t("workflows.initializeTitle", "Initialize workflow")}
        </h4>
        <div
          data-testid="workflow-init-form"
          style={{
            display: "flex",
            gap: "var(--space-2)",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <select
            data-testid="workflow-init-artifact-select"
            value={initArtifactId}
            onChange={(e) => setInitArtifactId(e.target.value)}
            disabled={isInitializing}
            style={{ ...inputStyle, minWidth: "220px" }}
          >
            <option value="">
              {t("workflows.selectArtifact", "-- select artifact --")}
            </option>
            {artifacts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.artifact_type} — {a.id.slice(0, 8)}…
              </option>
            ))}
          </select>
          <input
            data-testid="workflow-init-name-input"
            type="text"
            value={initName}
            onChange={(e) => setInitName(e.target.value)}
            placeholder={t("workflows.namePlaceholder", "Workflow name")}
            disabled={isInitializing}
            style={{ ...inputStyle, flex: 1, minWidth: "160px" }}
          />
          <button
            type="button"
            data-testid="workflow-init-btn"
            onClick={() => void handleInitialize()}
            disabled={isInitializing || !initArtifactId || !initName.trim()}
            style={{
              ...primaryButtonStyle,
              opacity:
                isInitializing || !initArtifactId || !initName.trim() ? 0.5 : 1,
              cursor:
                isInitializing || !initArtifactId || !initName.trim()
                  ? "not-allowed"
                  : "pointer",
            }}
          >
            {isInitializing ? "…" : t("workflows.initialize", "Initialize")}
          </button>
        </div>
      </div>

      {/* Transition state */}
      <div>
        <h4 style={subHeadingStyle}>
          {t("workflows.transitionTitle", "Transition state")}
        </h4>
        <div
          data-testid="workflow-transition-form"
          style={{
            display: "flex",
            gap: "var(--space-2)",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <select
            data-testid="workflow-transition-artifact-select"
            value={transitionEntityId}
            onChange={(e) => setTransitionEntityId(e.target.value)}
            disabled={isTransitioning}
            style={{ ...inputStyle, minWidth: "220px" }}
          >
            <option value="">
              {t("workflows.selectArtifact", "-- select artifact --")}
            </option>
            {artifacts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.artifact_type} — {a.id.slice(0, 8)}…
              </option>
            ))}
          </select>
          <input
            data-testid="workflow-target-state-input"
            type="text"
            value={targetState}
            onChange={(e) => setTargetState(e.target.value)}
            placeholder={t(
              "workflows.targetStatePlaceholder",
              "Target state (e.g. Approved)"
            )}
            disabled={isTransitioning}
            style={{ ...inputStyle, minWidth: "160px" }}
          />
          <input
            data-testid="workflow-change-reason-input"
            type="text"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder={t(
              "workflows.changeReasonPlaceholder",
              "Change reason (optional)"
            )}
            disabled={isTransitioning}
            style={{ ...inputStyle, flex: 1, minWidth: "160px" }}
          />
          <button
            type="button"
            data-testid="workflow-transition-btn"
            onClick={() => void handleTransition()}
            disabled={
              isTransitioning || !transitionEntityId || !targetState.trim()
            }
            style={{
              ...primaryButtonStyle,
              opacity:
                isTransitioning || !transitionEntityId || !targetState.trim()
                  ? 0.5
                  : 1,
              cursor:
                isTransitioning || !transitionEntityId || !targetState.trim()
                  ? "not-allowed"
                  : "pointer",
            }}
          >
            {isTransitioning ? "…" : t("workflows.transition", "Transition")}
          </button>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          data-testid="workflows-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            marginBottom: 0,
          }}
        >
          {error}
        </p>
      )}
      {statusMessage && (
        <p
          role="status"
          data-testid="workflows-status"
          style={{
            color: "var(--color-success, #16a34a)",
            fontSize: "var(--font-size-sm)",
            marginBottom: 0,
          }}
        >
          {statusMessage}
        </p>
      )}
    </section>
  );
}
