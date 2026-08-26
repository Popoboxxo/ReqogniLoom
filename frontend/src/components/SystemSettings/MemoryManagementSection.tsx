/**
 * Memory Admin UI Phase 1 (spec 2026-08-26) — System-Admin workspace
 * memory overview + delete, mounted as the "memory" tab in SystemSettings.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  memoryAdminApi,
  type WorkspaceMemoryOverviewRow,
} from "../../api/memoryAdmin";
import { Dialog } from "../shared/Dialog";
import styles from "./MemoryManagementSection.module.css";

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

export function MemoryManagementSection(): JSX.Element {
  const { t } = useTranslation();
  const [rows, setRows] = useState<WorkspaceMemoryOverviewRow[]>([]);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<WorkspaceMemoryOverviewRow | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const reload = useCallback((): void => {
    memoryAdminApi
      .listWorkspaceOverview()
      .then((r) => {
        setRows(r.results);
        setLoadError(null);
        setHasLoaded(true);
      })
      .catch((err: unknown) => {
        console.error("MemoryManagementSection: failed to load overview", err);
        setLoadError(t("systemSettings.memory.loadError"));
        setHasLoaded(true);
      });
  }, [t]);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!pendingDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await memoryAdminApi.deleteWorkspaceMemory(pendingDelete.workspace_id);
      setPendingDelete(null);
      reload();
    } catch (err: unknown) {
      setDeleteError(extractErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDelete, reload]);

  return (
    <section className={styles.section} data-testid="memory-management-section">
      <h3>{t("systemSettings.memory.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.memory.hint")}</p>

      {loadError && (
        <p role="alert" data-testid="memory-management-error" className={styles.error}>
          {loadError}
        </p>
      )}

      {!loadError && hasLoaded && rows.length === 0 && (
        <p data-testid="memory-management-empty" className={styles.empty}>
          {t("systemSettings.memory.noWorkspaces")}
        </p>
      )}

      {rows.length > 0 && (
        <table className={styles.table} data-testid="memory-management-table">
          <thead>
            <tr>
              <th>{t("systemSettings.memory.colWorkspace")}</th>
              <th>{t("systemSettings.memory.colEnabled")}</th>
              <th>{t("systemSettings.memory.colWorkspaceEntries")}</th>
              <th>{t("systemSettings.memory.colUserEntries")}</th>
              <th>{t("systemSettings.memory.colLastConsolidated")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.workspace_id} data-testid={`memory-row-${row.workspace_id}`}>
                <td>{row.workspace_name}</td>
                <td>{row.enabled ? "✓" : "—"}</td>
                <td>{row.workspace_entry_count}</td>
                <td>{row.user_entry_count}</td>
                <td>{formatDate(row.last_consolidated_at)}</td>
                <td>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    data-testid={`memory-delete-btn-${row.workspace_id}`}
                    onClick={() => {
                      setDeleteError(null);
                      setPendingDelete(row);
                    }}
                  >
                    {t("systemSettings.memory.deleteButton")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {pendingDelete && (
        <Dialog
          title={t("systemSettings.memory.deleteConfirmTitle")}
          onClose={() => setPendingDelete(null)}
          size="sm"
          testId="memory-delete-confirm-dialog"
          footer={
            <div className={styles.dialogFooter}>
              <button type="button" onClick={() => setPendingDelete(null)}>
                {t("actions.cancel", "Cancel")}
              </button>
              <button
                type="button"
                data-testid="memory-delete-confirm-btn"
                disabled={isDeleting}
                onClick={() => void handleDelete()}
                className={styles.deleteBtn}
              >
                {isDeleting ? "…" : t("systemSettings.memory.deleteConfirmButton")}
              </button>
            </div>
          }
        >
          <p>
            {t("systemSettings.memory.deleteConfirmBody", {
              wsCount: pendingDelete.workspace_entry_count,
              userCount: pendingDelete.user_entry_count,
              workspace: pendingDelete.workspace_name,
            })}
          </p>
          {deleteError && (
            <p role="alert" className={styles.error}>
              {deleteError}
            </p>
          )}
        </Dialog>
      )}
    </section>
  );
}
