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
import { ConfirmDialog } from "../shared/ConfirmDialog";
import styles from "./WorkspaceAdminSection.module.css";

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
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  const handleCloseWorkspace = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
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
  }, [activeWorkspace, reloadWorkspaces]);

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
    return <p className={styles.emptyMessage}>{t("errors.generic")}</p>;
  }

  return (
    <>
      {/* System Health dashboard — infra status + recent audit log */}
      <section className={styles.card} data-testid="system-health-section">
        <h3 className={styles.heading}>{t("systemHealth.title", "System Health")}</h3>
        <p
          className={styles.sectionHint}
        >
          {t(
            "systemHealth.sectionHint",
            "Live status of database, redis, celery worker/beat, MCP server and LLM provider, plus recent audit-log entries."
          )}
        </p>
        <button
          type="button"
          className="btn-primary"
          data-testid="system-health-open-btn"
          onClick={() => setShowSystemHealth(true)}
        >
          {t("systemHealth.openButton", "View System Health")}
        </button>
      </section>

      <SystemHealthDialog
        isOpen={showSystemHealth}
        onClose={() => setShowSystemHealth(false)}
      />

      {/* Tri-Label Overview — read-only DE/EN TraceLink-type reference (UMSETZUNGSPLAN_SYSENG_2.0.md §1.3) */}
      <section className={styles.card} data-testid="tri-label-overview-section">
        <h3 className={styles.heading}>{t("triLabelOverview.title", "Tri-Label Overview")}</h3>
        <p
          className={styles.sectionHint}
        >
          {t(
            "triLabelOverview.sectionHint",
            "Read-only reference of all 14 TraceLink types with their German/English downstream, upstream and neutral labels."
          )}
        </p>
        <button
          type="button"
          className="btn-primary"
          data-testid="tri-label-overview-open-btn"
          onClick={() => setShowTriLabelOverview(true)}
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
      <section className={styles.card} data-testid="lifecycle-section">
        <h3 className={styles.heading}>{t("settings.lifecycleSection", "Workspace Administration")}</h3>

        {activeWorkspace.is_active !== false && (
          <button
            type="button"
            data-testid="close-workspace-btn"
            onClick={() => setShowCloseConfirm(true)}
            disabled={isClosing}
            className={styles.solidAction + " " + styles.closeWorkspaceButton}
          >
            {isClosing ? "…" : t("settings.closeWorkspace", "Close Workspace")}
          </button>
        )}

        {activeWorkspace.is_active !== false && (
          <div className={styles.cloneRow}>
            <input
              type="text"
              placeholder="Sandbox Name"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              className={styles.cloneInput}
            />
            <button
              type="button"
              className="btn-primary"
              data-testid="clone-workspace-btn"
              onClick={() => void handleCloneWorkspace()}
              disabled={isCloning || !cloneName.trim()}
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
            className={styles.solidAction + " " + styles.reactivateWorkspaceButton}
          >
            {t("settings.reactivateWorkspace", "Reactivate Workspace")}
          </button>
        )}

        <button
          type="button"
          data-testid="delete-workspace-btn"
          onClick={() => { setShowDeleteModal(true); setDeleteError(null); setDeleteConfirmation(""); }}
          className={styles.solidAction + " " + styles.deleteWorkspaceButton}
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
              <>
                <button
                  type="button"
                  className="btn-secondary"
                  data-testid="delete-cancel-btn"
                  onClick={() => { setShowDeleteModal(false); setDeleteConfirmation(""); setDeleteError(null); }}
                >
                  {t("actions.cancel", "Cancel")}
                </button>
                <button
                  type="button"
                  data-testid="delete-confirm-btn"
                  onClick={() => void handleDeleteWorkspace()}
                  disabled={isDeleting || deleteConfirmation !== activeWorkspace.name}
                  className={styles.solidAction + " " + styles.deleteWorkspaceButton}
                >
                  {isDeleting ? "…" : t("settings.deleteConfirmButton", "Permanently Delete")}
                </button>
              </>
            }
          >
            <p className={styles.deletePrompt}>
              {t("settings.deleteCaptchaPrompt", { name: activeWorkspace.name })}
            </p>
            <input
              data-testid="delete-confirmation-input"
              type="text"
              value={deleteConfirmation}
              onChange={(e) => { setDeleteConfirmation(e.target.value); setDeleteError(null); }}
              placeholder={activeWorkspace.name}
              className={styles.deleteInput}
            />
            {deleteError && (
              <div role="alert" data-testid="delete-error" className={styles.deleteError}>
                {deleteError}
              </div>
            )}
          </Dialog>
        )}
      </section>

      {saveError && (
        <div role="alert" className={styles.saveError}>
          {saveError}
        </div>
      )}
      {savedOk && (
        <div data-testid="settings-saved-ok" className={styles.savedOk}>
          {t("settings.saved")}
        </div>
      )}

      {showCloseConfirm && (
        <ConfirmDialog
          title={t("settings.closeWorkspace", "Close Workspace")}
          message={t("settings.closeConfirm")}
          confirmLabel={t("settings.closeWorkspace", "Close Workspace")}
          onConfirm={() => {
            setShowCloseConfirm(false);
            void handleCloseWorkspace();
          }}
          onCancel={() => setShowCloseConfirm(false)}
          testId="close-workspace-confirm"
        />
      )}
    </>
  );
}
