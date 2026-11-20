/**
 * Memory Admin UI Phase 1 (spec 2026-08-26) — System-Admin workspace
 * memory overview + delete, mounted as the "memory" tab in SystemSettings.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import {
  memoryApi,
  type WorkspaceMemoryOverviewRow,
} from "../../api/memory";
import { Dialog } from "../shared/Dialog";
import styles from "./MemoryManagementSection.module.css";
import { toUserErrorMessage } from "../../utils/userErrorMessage";

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
  const [deleteNotice, setDeleteNotice] = useState<string | null>(null);

  const reload = useCallback((): void => {
    memoryApi
      .listSystemWorkspaceOverview()
      .then((r) => {
        setRows(r.results);
        setLoadError(null);
        setHasLoaded(true);
      })
      .catch((err: unknown) => {
        console.error("MemoryManagementSection: failed to load overview", err);
        setLoadError(
          toUserErrorMessage(err, t, t("systemSettings.memory.loadError"))
        );
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
      const deleted = pendingDelete.workspace_name;
      await memoryApi.deleteSystemWorkspaceMemory(pendingDelete.workspace_id);
      setPendingDelete(null);
      setDeleteNotice(t("systemSettings.memory.deleteSuccess", { workspace: deleted }));
      reload();
    } catch (err: unknown) {
      console.error("MemoryManagementSection: failed to delete workspace memory", err);
      setDeleteError(
        toUserErrorMessage(err, t, t("systemSettings.memory.deleteError"))
      );
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDelete, reload, t]);

  const isAnyDegraded = rows.some((row) => row.degraded);

  return (
    <section className={styles.section} data-testid="memory-management-section">
      <h3>{t("systemSettings.memory.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.memory.hint")}</p>

      {isAnyDegraded && (
        <p
          role="status"
          data-testid="memory-management-degraded"
          className={styles.degraded}
        >
          {t("systemSettings.memory.degraded", "Gedächtnis aktuell nicht erreichbar.")}
        </p>
      )}

      {loadError && (
        <p role="alert" data-testid="memory-management-error" className={styles.error}>
          {loadError}
        </p>
      )}
      {deleteNotice && !loadError && (
        <p role="status" data-testid="memory-management-deleted" className={styles.hint}>
          {deleteNotice}
        </p>
      )}

      {!loadError && hasLoaded && rows.length === 0 && (
        <p data-testid="memory-management-empty" className={styles.empty}>
          {t("systemSettings.memory.noWorkspaces")}
        </p>
      )}

      {rows.length > 0 && (
        <table className={styles.table} data-testid="memory-management-table">
          <caption className="visually-hidden">
            {t("systemSettings.memory.caption")}
          </caption>
          <thead>
            <tr>
              <th scope="col">{t("systemSettings.memory.colWorkspace")}</th>
              <th scope="col">{t("systemSettings.memory.colEnabled")}</th>
              <th scope="col">{t("systemSettings.memory.colWorkspaceEntries")}</th>
              <th scope="col">{t("systemSettings.memory.colUserEntries")}</th>
              <th scope="col">{t("systemSettings.memory.colArtifactEntries")}</th>
              <th scope="col">{t("systemSettings.memory.colContributors")}</th>
              <th scope="col">{t("systemSettings.memory.colStatus")}</th>
              <th scope="col">{t("systemSettings.memory.colLastConsolidated")}</th>
              <th scope="col">
                <span className="visually-hidden">
                  {t("systemSettings.memory.colActions")}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.workspace_id} data-testid={`memory-row-${row.workspace_id}`}>
                <td>{row.workspace_name}</td>
                <td>
                  {row.enabled ? <Check aria-hidden="true" size={14} /> : "—"}
                  <span className="visually-hidden">
                    {row.enabled ? t("common.yes", "Yes") : t("common.no", "No")}
                  </span>
                </td>
                <td>{row.workspace_entry_count}</td>
                <td>{row.user_entry_count}</td>
                <td data-testid={`memory-artifact-count-${row.workspace_id}`}>
                  {row.by_scope?.artifact ?? 0}
                </td>
                <td data-testid={`memory-contributor-count-${row.workspace_id}`}>
                  {row.contributor_count}
                </td>
                <td data-testid={`memory-status-${row.workspace_id}`}>
                  {row.degraded
                    ? t("systemSettings.memory.statusDegraded", "Beeinträchtigt")
                    : t("systemSettings.memory.statusOk", "OK")}
                </td>
                <td>{formatDate(row.last_consolidated_at)}</td>
                <td>
                  <button
                    type="button"
                    className="btn-danger"
                    data-testid={`memory-delete-btn-${row.workspace_id}`}
                    aria-label={`${t("systemSettings.memory.deleteButton")} – ${row.workspace_name}`}
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
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setPendingDelete(null)}
              >
                {t("actions.cancel", "Cancel")}
              </button>
              <button
                type="button"
                data-testid="memory-delete-confirm-btn"
                disabled={isDeleting}
                onClick={() => void handleDelete()}
                className="btn-danger"
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
