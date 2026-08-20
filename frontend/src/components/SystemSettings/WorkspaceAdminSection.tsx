/**
 * REQ-184 — WorkspaceAdminSection (relocated Administration tab, SCR-204).
 *
 * The content of the former ``/settings`` "Administration" tab, moved verbatim
 * into System Settings: the System Health dialog trigger, the feature-flagged
 * Backup/Restore section, and the Workspace Administration lifecycle controls
 * (close/reactivate/delete/clone). Behaviour is unchanged — it still operates on
 * the globally-active workspace via ``useWorkspace()`` (the workspace switcher
 * lives in the sidebar and is not route-scoped), per the IA-split spec.
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { workspacesApi } from "../../api/workspaces";
import { BackupRestoreSection } from "../WorkspaceSettings/BackupRestoreSection";
import { SystemHealthDialog } from "../AdminDialog/SystemHealthDialog";
import { TriLabelOverviewDialog } from "../AdminDialog/TriLabelOverviewDialog";
import { Dialog } from "../shared/Dialog";

const cardStyle: React.CSSProperties = {
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

export function WorkspaceAdminSection(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, reloadWorkspaces, isFeatureVisible } = useWorkspace();
  const navigate = useNavigate();

  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);
  const [showSystemHealth, setShowSystemHealth] = useState(false);
  const [showTriLabelOverview, setShowTriLabelOverview] = useState(false);

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [isCloning, setIsCloning] = useState(false);

  const handleCloseWorkspace = useCallback(async (): Promise<void> => {
    if (!activeWorkspace || !window.confirm(t("settings.closeConfirm"))) return;
    setSaveError(null);
    setIsClosing(true);
    try {
      await workspacesApi.closeWorkspace(activeWorkspace.id);
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    } finally {
      setIsClosing(false);
    }
  }, [activeWorkspace, reloadWorkspaces, t]);

  const handleReactivateWorkspace = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setSaveError(null);
    try {
      await workspacesApi.reactivateWorkspace(activeWorkspace.id);
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    }
  }, [activeWorkspace, reloadWorkspaces]);

  const handleDeleteWorkspace = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (deleteConfirmation !== activeWorkspace.name) {
      setDeleteError(t("settings.deleteConfirmationMismatch"));
      return;
    }
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await workspacesApi.deleteWorkspace(activeWorkspace.id, deleteConfirmation);
      setShowDeleteModal(false);
      setDeleteConfirmation("");
      navigate("/");
    } catch (err: unknown) {
      setDeleteError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    } finally {
      setIsDeleting(false);
    }
  }, [activeWorkspace, deleteConfirmation, navigate, t]);

  const handleCloneWorkspace = useCallback(async (): Promise<void> => {
    if (!activeWorkspace || !cloneName.trim()) return;
    setSaveError(null);
    setIsCloning(true);
    try {
      const cloned = await workspacesApi.clone(activeWorkspace.id, cloneName.trim());
      await reloadWorkspaces(cloned.id);
      setCloneName("");
      setSavedOk(true);
      navigate("/");
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    } finally {
      setIsCloning(false);
    }
  }, [activeWorkspace, cloneName, navigate, reloadWorkspaces]);

  if (!activeWorkspace) {
    return <p style={{ padding: "var(--space-4)" }}>{t("errors.generic")}</p>;
  }

  return (
    <>
      {/* System Health dashboard — infra status + recent audit log */}
      <section style={cardStyle} data-testid="system-health-section">
        <h3 style={headingStyle}>{t("systemHealth.title", "System Health")}</h3>
        <p
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            marginTop: 0,
            marginBottom: "var(--space-3)",
          }}
        >
          {t(
            "systemHealth.sectionHint",
            "Live status of database, redis, celery worker/beat, MCP server and LLM provider, plus recent audit-log entries."
          )}
        </p>
        <button
          type="button"
          data-testid="system-health-open-btn"
          onClick={() => setShowSystemHealth(true)}
          style={primaryButtonStyle}
        >
          {t("systemHealth.openButton", "View System Health")}
        </button>
      </section>

      <SystemHealthDialog
        isOpen={showSystemHealth}
        onClose={() => setShowSystemHealth(false)}
      />

      {/* Tri-Label Overview — read-only DE/EN TraceLink-type reference (UMSETZUNGSPLAN_SYSENG_2.0.md §1.3) */}
      <section style={cardStyle} data-testid="tri-label-overview-section">
        <h3 style={headingStyle}>{t("triLabelOverview.title", "Tri-Label Overview")}</h3>
        <p
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            marginTop: 0,
            marginBottom: "var(--space-3)",
          }}
        >
          {t(
            "triLabelOverview.sectionHint",
            "Read-only reference of all 14 TraceLink types with their German/English downstream, upstream and neutral labels."
          )}
        </p>
        <button
          type="button"
          data-testid="tri-label-overview-open-btn"
          onClick={() => setShowTriLabelOverview(true)}
          style={primaryButtonStyle}
        >
          {t("triLabelOverview.openButton", "View Tri-Label Overview")}
        </button>
      </section>

      <TriLabelOverviewDialog
        isOpen={showTriLabelOverview}
        onClose={() => setShowTriLabelOverview(false)}
      />

      {/* Feature-flagged: Baselines & Backup/Restore (REQ-L1-046) */}
      {isFeatureVisible("baselines") && <BackupRestoreSection />}

      {/* Workspace Administration (REQ-L1-042) */}
      <section style={cardStyle} data-testid="lifecycle-section">
        <h3 style={headingStyle}>{t("settings.lifecycleSection", "Workspace Administration")}</h3>

        {activeWorkspace.is_active !== false && (
          <button
            type="button"
            data-testid="close-workspace-btn"
            onClick={() => void handleCloseWorkspace()}
            disabled={isClosing}
            style={{
              background: "var(--color-warning)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
              marginRight: "var(--space-2)",
              opacity: isClosing ? 0.5 : 1,
            }}
          >
            {isClosing ? "…" : t("settings.closeWorkspace", "Close Workspace")}
          </button>
        )}

        {activeWorkspace.is_active !== false && (
          <div style={{ marginTop: "var(--space-4)", marginBottom: "var(--space-4)", display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
            <input
              type="text"
              placeholder="Sandbox Name"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              style={{
                padding: "var(--space-2)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                background: "var(--color-surface-raised)",
                color: "var(--color-text)",
              }}
            />
            <button
              type="button"
              data-testid="clone-workspace-btn"
              onClick={() => void handleCloneWorkspace()}
              disabled={isCloning || !cloneName.trim()}
              style={{
                ...primaryButtonStyle,
                cursor: isCloning || !cloneName.trim() ? "not-allowed" : "pointer",
                opacity: isCloning || !cloneName.trim() ? 0.5 : 1,
              }}
            >
              {isCloning ? "Cloning…" : "Create Sandbox"}
            </button>
          </div>
        )}

        {activeWorkspace.is_active === false && (
          <button
            type="button"
            data-testid="reactivate-workspace-btn"
            onClick={() => void handleReactivateWorkspace()}
            style={{
              background: "var(--color-success)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
              marginRight: "var(--space-2)",
            }}
          >
            {t("settings.reactivateWorkspace", "Reactivate Workspace")}
          </button>
        )}

        <button
          type="button"
          data-testid="delete-workspace-btn"
          onClick={() => { setShowDeleteModal(true); setDeleteError(null); setDeleteConfirmation(""); }}
          style={{
            background: "var(--color-danger)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {t("settings.deleteWorkspace", "Delete Workspace")}
        </button>

        {showDeleteModal && (
          <Dialog
            title={t("settings.deleteConfirmTitle", "Delete Workspace")}
            onClose={() => { setShowDeleteModal(false); setDeleteConfirmation(""); setDeleteError(null); }}
            size="sm"
            testId="delete-modal"
            footer={
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button
                  type="button"
                  data-testid="delete-cancel-btn"
                  onClick={() => { setShowDeleteModal(false); setDeleteConfirmation(""); setDeleteError(null); }}
                  style={{
                    background: "transparent",
                    color: "var(--color-text-muted)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-2) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    cursor: "pointer",
                  }}
                >
                  {t("actions.cancel", "Cancel")}
                </button>
                <button
                  type="button"
                  data-testid="delete-confirm-btn"
                  onClick={() => void handleDeleteWorkspace()}
                  disabled={isDeleting || deleteConfirmation !== activeWorkspace.name}
                  style={{
                    background: "var(--color-danger)",
                    color: "white",
                    border: "none",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-2) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    fontWeight: 600,
                    cursor: "pointer",
                    opacity: (isDeleting || deleteConfirmation !== activeWorkspace.name) ? 0.5 : 1,
                  }}
                >
                  {isDeleting ? "…" : t("settings.deleteConfirmButton", "Permanently Delete")}
                </button>
              </div>
            }
          >
            <p style={{ fontSize: "var(--font-size-sm)", marginBottom: "var(--space-3)", marginTop: 0 }}>
              {t("settings.deleteCaptchaPrompt", { name: activeWorkspace.name })}
            </p>
            <input
              data-testid="delete-confirmation-input"
              type="text"
              value={deleteConfirmation}
              onChange={(e) => { setDeleteConfirmation(e.target.value); setDeleteError(null); }}
              placeholder={activeWorkspace.name}
              style={{
                width: "100%",
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-3)",
                color: "var(--color-text)",
                fontSize: "var(--font-size-base)",
                marginBottom: "var(--space-2)",
                boxSizing: "border-box",
              }}
            />
            {deleteError && (
              <div role="alert" data-testid="delete-error" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-2)" }}>
                {deleteError}
              </div>
            )}
          </Dialog>
        )}
      </section>

      {saveError && (
        <div role="alert" style={{ color: "var(--color-danger)", padding: "var(--space-3)", background: "var(--color-surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-danger)" }}>
          {saveError}
        </div>
      )}
      {savedOk && (
        <div data-testid="settings-saved-ok" style={{ color: "var(--color-success)", padding: "var(--space-3)" }}>
          {t("settings.saved")}
        </div>
      )}
    </>
  );
}
