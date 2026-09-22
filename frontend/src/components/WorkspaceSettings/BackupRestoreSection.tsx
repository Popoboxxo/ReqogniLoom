/**
 * ARCH-L1-001 ReactFrontend — BackupRestoreSection (WorkspaceSettings).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L1-046 (Disaster Recovery: Backup / Restore)
 *
 * Admin-only section (parent gates rendering on the admin role):
 *   - list backups (newest first)
 *   - create backup (optional reason, full/partial)
 *   - restore from a restorable backup — requires typing the captcha
 *     confirmation text "RESTORE" (enforced by the backend as well)
 */

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  adminOpsApi,
  RESTORE_CONFIRMATION_TEXT,
  type BackupMetadata,
  type BackupTypeValue,
  type RestoreResult,
} from "../../api/admin-ops";
import { Spinner } from "../shared/Spinner/Spinner";
import styles from "./BackupRestoreSection.module.css";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function BackupRestoreSection(): JSX.Element {
  const { t } = useTranslation();
  const [backups, setBackups] = useState<BackupMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create-backup state
  const [reason, setReason] = useState("");
  const [backupType, setBackupType] = useState<BackupTypeValue>("full");
  const [isCreating, setIsCreating] = useState(false);

  // Restore state
  const [restoreTargetId, setRestoreTargetId] = useState<string | null>(null);
  const [confirmationText, setConfirmationText] = useState("");
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreResult, setRestoreResult] = useState<RestoreResult | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const rows = await adminOpsApi.listBackups();
      setBackups(rows);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreateBackup = useCallback(async (): Promise<void> => {
    setIsCreating(true);
    setError(null);
    try {
      await adminOpsApi.createBackup({
        reason: reason.trim() || undefined,
        backup_type: backupType,
      });
      setReason("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsCreating(false);
    }
  }, [reason, backupType, load]);

  const handleRestore = useCallback(async (): Promise<void> => {
    if (!restoreTargetId) return;
    setIsRestoring(true);
    setError(null);
    setRestoreResult(null);
    try {
      const result = await adminOpsApi.restore({
        backup_id: restoreTargetId,
        confirmation_text: confirmationText,
      });
      setRestoreResult(result);
      setRestoreTargetId(null);
      setConfirmationText("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsRestoring(false);
    }
  }, [restoreTargetId, confirmationText, load]);

  return (
    <section className={styles.section} data-testid="backup-restore-section">
      <h3 className={styles.heading}>
        {t("adminOps.title", "Backup & Restore (Disaster Recovery)")}
      </h3>
      <p className={styles.hint}>
        {t(
          "adminOps.hint",
          "Instance-level backups. A restore overwrites current data — the confirmation text is required."
        )}
      </p>

      {/* Create backup */}
      <div className={styles.createRow}>
        <input
          data-testid="backup-reason-input"
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t("adminOps.reasonPlaceholder", "Reason (optional)")}
          disabled={isCreating}
          className={`${styles.input} ${styles.inputFlex}`}
        />
        <label htmlFor="backup-type-select" className={styles.visuallyHidden}>
          {t("adminOps.backupTypeLabel", "Backup type")}
        </label>
        <select
          id="backup-type-select"
          data-testid="backup-type-select"
          value={backupType}
          onChange={(e) => setBackupType(e.target.value as BackupTypeValue)}
          disabled={isCreating}
          className={styles.input}
        >
          <option value="full">{t("adminOps.typeFull", "full")}</option>
          <option value="partial">{t("adminOps.typePartial", "partial")}</option>
        </select>
        <button
          type="button"
          data-testid="backup-create-btn"
          onClick={() => void handleCreateBackup()}
          disabled={isCreating}
          className={`btn-primary ${styles.createButton}`}
        >
          {isCreating ? (
            <Spinner label={t("adminOps.creatingBackup", "Creating backup...")} />
          ) : (
            `+ ${t("adminOps.createBackup", "Create Backup")}`
          )}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          data-testid="backup-restore-error"
          className={styles.errorText}
        >
          {error}
        </p>
      )}

      {/* Restore result summary */}
      {restoreResult && (
        <div
          data-testid="restore-result"
          role="status"
          className={styles.restoreResult}
        >
          <strong>
            {t("adminOps.restoreDone", "Restore completed")}
          </strong>{" "}
          — {restoreResult.restored_tables.length}{" "}
          {t("adminOps.tablesRestored", "tables restored")}
          {restoreResult.completed_at
            ? ` (${formatDate(restoreResult.completed_at)})`
            : ""}
        </div>
      )}

      {/* Backup list */}
      {isLoading ? (
        <p role="status" className={styles.mutedText}>
          {t("loading", "Loading...")}
        </p>
      ) : backups.length === 0 ? (
        <p
          data-testid="backups-empty"
          className={styles.emptyText}
        >
          {t("adminOps.empty", "No backups yet.")}
        </p>
      ) : (
        <table data-testid="backups-table" className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>{t("adminOps.id", "ID")}</th>
              <th className={styles.th}>{t("adminOps.type", "Type")}</th>
              <th className={styles.th}>{t("adminOps.status", "Status")}</th>
              <th className={styles.th}>{t("adminOps.size", "Size")}</th>
              <th className={styles.th}>{t("adminOps.created", "Created")}</th>
              <th className={styles.th} />
            </tr>
          </thead>
          <tbody>
            {backups.map((backup) => (
              <React.Fragment key={backup.id}>
                <tr data-testid={`backup-row-${backup.id}`}>
                  <td className={`${styles.td} ${styles.tdMono}`}>
                    {backup.id.slice(0, 8)}…
                  </td>
                  <td className={styles.td}>{backup.backup_type}</td>
                  <td className={styles.td}>{backup.status}</td>
                  <td className={styles.td}>{formatBytes(backup.file_size_bytes)}</td>
                  <td className={styles.td}>{formatDate(backup.created_at)}</td>
                  <td className={`${styles.td} ${styles.tdRight}`}>
                    {backup.is_restorable && (
                      <button
                        type="button"
                        data-testid={`backup-restore-${backup.id}`}
                        onClick={() => {
                          setRestoreTargetId(
                            restoreTargetId === backup.id ? null : backup.id
                          );
                          setConfirmationText("");
                          setRestoreResult(null);
                        }}
                        className={styles.restoreLinkButton}
                      >
                        {restoreTargetId === backup.id
                          ? t("actions.cancel", "Cancel")
                          : t("adminOps.restore", "Restore")}
                      </button>
                    )}
                  </td>
                </tr>
                {restoreTargetId === backup.id && (
                  <tr>
                    <td colSpan={6} className={`${styles.td} ${styles.tdRaised}`}>
                      <div
                        data-testid="restore-confirm-box"
                        className={styles.restoreConfirmRow}
                      >
                        <label
                          htmlFor="restore-confirmation-input"
                          className={styles.captchaLabel}
                        >
                          {t("adminOps.restoreCaptchaPrompt", {
                            defaultValue:
                              'Type "{{captcha}}" to confirm — current data will be overwritten.',
                            captcha: RESTORE_CONFIRMATION_TEXT,
                          })}
                        </label>
                        <input
                          id="restore-confirmation-input"
                          data-testid="restore-confirmation-input"
                          type="text"
                          value={confirmationText}
                          onChange={(e) => setConfirmationText(e.target.value)}
                          placeholder={RESTORE_CONFIRMATION_TEXT}
                          disabled={isRestoring}
                          aria-required="true"
                          className={`${styles.input} ${styles.inputNarrow}`}
                        />
                        <button
                          type="button"
                          data-testid="restore-confirm-btn"
                          onClick={() => void handleRestore()}
                          disabled={
                            isRestoring ||
                            confirmationText !== RESTORE_CONFIRMATION_TEXT
                          }
                          className="btn-danger"
                        >
                          {isRestoring
                            ? "…"
                            : t("adminOps.restoreConfirm", "Restore now")}
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
