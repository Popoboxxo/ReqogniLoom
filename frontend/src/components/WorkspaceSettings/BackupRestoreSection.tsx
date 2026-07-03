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

const inputStyle: React.CSSProperties = {
  background: "var(--color-bg)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-base)",
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
    <section style={sectionStyle} data-testid="backup-restore-section">
      <h3 style={headingStyle}>
        {t("adminOps.title", "Backup & Restore (Disaster Recovery)")}
      </h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginTop: 0,
          marginBottom: "var(--space-3)",
        }}
      >
        {t(
          "adminOps.hint",
          "Instance-level backups. A restore overwrites current data — the confirmation text is required."
        )}
      </p>

      {/* Create backup */}
      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
          flexWrap: "wrap",
        }}
      >
        <input
          data-testid="backup-reason-input"
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t("adminOps.reasonPlaceholder", "Reason (optional)")}
          disabled={isCreating}
          style={{ ...inputStyle, flex: 1, minWidth: "200px" }}
        />
        <select
          data-testid="backup-type-select"
          value={backupType}
          onChange={(e) => setBackupType(e.target.value as BackupTypeValue)}
          disabled={isCreating}
          style={inputStyle}
        >
          <option value="full">{t("adminOps.typeFull", "full")}</option>
          <option value="partial">{t("adminOps.typePartial", "partial")}</option>
        </select>
        <button
          type="button"
          data-testid="backup-create-btn"
          onClick={() => void handleCreateBackup()}
          disabled={isCreating}
          style={{
            ...primaryButtonStyle,
            opacity: isCreating ? 0.5 : 1,
            cursor: isCreating ? "wait" : "pointer",
          }}
        >
          {isCreating ? "…" : `+ ${t("adminOps.createBackup", "Create Backup")}`}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          data-testid="backup-restore-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </p>
      )}

      {/* Restore result summary */}
      {restoreResult && (
        <div
          data-testid="restore-result"
          role="status"
          style={{
            background: "rgba(22,163,74,0.08)",
            border: "1px solid var(--color-success, #16a34a)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            marginBottom: "var(--space-4)",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text)",
          }}
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
        <p role="status" style={{ color: "var(--color-text-muted)" }}>
          {t("loading", "Loading...")}
        </p>
      ) : backups.length === 0 ? (
        <p
          data-testid="backups-empty"
          style={{
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {t("adminOps.empty", "No backups yet.")}
        </p>
      ) : (
        <table
          data-testid="backups-table"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              <th style={thStyle}>{t("adminOps.id", "ID")}</th>
              <th style={thStyle}>{t("adminOps.type", "Type")}</th>
              <th style={thStyle}>{t("adminOps.status", "Status")}</th>
              <th style={thStyle}>{t("adminOps.size", "Size")}</th>
              <th style={thStyle}>{t("adminOps.created", "Created")}</th>
              <th style={thStyle} />
            </tr>
          </thead>
          <tbody>
            {backups.map((backup) => (
              <React.Fragment key={backup.id}>
                <tr data-testid={`backup-row-${backup.id}`}>
                  <td style={{ ...tdStyle, fontFamily: "monospace" }}>
                    {backup.id.slice(0, 8)}…
                  </td>
                  <td style={tdStyle}>{backup.backup_type}</td>
                  <td style={tdStyle}>{backup.status}</td>
                  <td style={tdStyle}>{formatBytes(backup.file_size_bytes)}</td>
                  <td style={tdStyle}>{formatDate(backup.created_at)}</td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>
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
                        style={{
                          background: "transparent",
                          color: "var(--color-danger)",
                          border: "1px solid var(--color-danger)",
                          borderRadius: "var(--radius-md)",
                          padding: "var(--space-1) var(--space-3)",
                          fontSize: "var(--font-size-sm)",
                          cursor: "pointer",
                        }}
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
                    <td colSpan={6} style={{ ...tdStyle, background: "var(--color-surface-raised)" }}>
                      <div
                        data-testid="restore-confirm-box"
                        style={{
                          display: "flex",
                          gap: "var(--space-3)",
                          alignItems: "center",
                          flexWrap: "wrap",
                        }}
                      >
                        <span style={{ fontSize: "var(--font-size-sm)" }}>
                          {t("adminOps.restoreCaptchaPrompt", {
                            defaultValue:
                              'Type "{{captcha}}" to confirm — current data will be overwritten.',
                            captcha: RESTORE_CONFIRMATION_TEXT,
                          })}
                        </span>
                        <input
                          data-testid="restore-confirmation-input"
                          type="text"
                          value={confirmationText}
                          onChange={(e) => setConfirmationText(e.target.value)}
                          placeholder={RESTORE_CONFIRMATION_TEXT}
                          disabled={isRestoring}
                          style={{ ...inputStyle, width: "160px" }}
                        />
                        <button
                          type="button"
                          data-testid="restore-confirm-btn"
                          onClick={() => void handleRestore()}
                          disabled={
                            isRestoring ||
                            confirmationText !== RESTORE_CONFIRMATION_TEXT
                          }
                          style={{
                            background: "var(--color-danger)",
                            color: "white",
                            border: "none",
                            borderRadius: "var(--radius-md)",
                            padding: "var(--space-2) var(--space-4)",
                            fontSize: "var(--font-size-sm)",
                            fontWeight: 600,
                            cursor:
                              isRestoring ||
                              confirmationText !== RESTORE_CONFIRMATION_TEXT
                                ? "not-allowed"
                                : "pointer",
                            opacity:
                              isRestoring ||
                              confirmationText !== RESTORE_CONFIRMATION_TEXT
                                ? 0.5
                                : 1,
                          }}
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

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--color-border)",
};

const tdStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  borderBottom: "1px solid var(--color-border)",
  verticalAlign: "middle",
};
