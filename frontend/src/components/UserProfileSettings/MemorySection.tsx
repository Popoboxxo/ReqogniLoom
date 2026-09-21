/**
 * ARCH-L1-001 ReactFrontend — MemorySection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * RFC #1002 PR D: lists the authenticated user's OWN user-scoped facts
 * (`GET /memory/me/?include_entries=true`) with a per-row forget action, on
 * top of the existing "delete everything" self-service control. Never touches
 * workspace/artifact memory, which is team-owned (see `memory/policy.py`).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractApiErrorMessage } from "../../api/client";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { formatMemoryDate } from "../Memory/memory-format";
import styles from "./MemorySection.module.css";

const PAGE_SIZE = 100;

export function MemorySection(): JSX.Element {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [entryCount, setEntryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [pendingForget, setPendingForget] = useState<MemoryEntry | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const overview = await memoryApi.getSelfOverview({
        includeEntries: true,
        pageSize: PAGE_SIZE,
      });
      setEntries(overview.entries ?? []);
      setEntryCount(overview.entry_count);
      setLastUpdated(overview.last_updated_at);
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.error", "Memory konnte nicht geladen werden.")
      );
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDelete = useCallback(async (): Promise<void> => {
    setIsDeleting(true);
    setError(null);
    try {
      await memoryApi.deleteSelfMemory();
      setEntries([]);
      setEntryCount(0);
      setLastUpdated(null);
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.error", "Memory konnte nicht gelöscht werden.")
      );
    } finally {
      setIsDeleting(false);
    }
  }, [t]);

  const handleForget = useCallback(async (): Promise<void> => {
    if (!pendingForget) return;
    const entryId = pendingForget.entry_id;
    setPendingForget(null);
    setBusyId(entryId);
    setError(null);
    try {
      await memoryApi.forgetEntry(entryId);
      await load();
    } catch (err: unknown) {
      setError(
        extractApiErrorMessage(err) ??
          t("memorySelfService.forgetError", "Eintrag konnte nicht gelöscht werden.")
      );
    } finally {
      setBusyId(null);
    }
  }, [pendingForget, load, t]);

  return (
    <section className={styles.section} data-testid="memory-self-service-section">
      <h2 className={styles.heading}>{t("memorySelfService.title", "Mein Memory")}</h2>
      <p className={styles.hint}>
        {t(
          "memorySelfService.hint",
          "Das KI-Langzeitgedächtnis speichert Kontext über dich, um Antworten zu personalisieren. Du kannst deine eigenen Einträge jederzeit vollständig löschen."
        )}
      </p>

      {error && (
        <p role="alert" data-testid="memory-self-service-error" className={styles.error}>
          {error}
        </p>
      )}

      {isLoading ? (
        <div className={styles.card}>
          <p role="status" data-testid="memory-self-service-loading" className={styles.loadingText}>
            {t("loading", "Loading...")}
          </p>
        </div>
      ) : (
        <div className={styles.card}>
          <div className={styles.headerRow}>
            <div>
              <p className={styles.metaLine}>
                {t("memorySelfService.countLabel", "Gespeicherte Einträge")}:{" "}
                <span data-testid="memory-self-service-count" className={styles.countValue}>
                  {entryCount}
                </span>
              </p>
              <p className={styles.metaLine}>
                {t("memorySelfService.lastUpdatedLabel", "Zuletzt aktualisiert")}:{" "}
                <span data-testid="memory-self-service-last-updated">
                  {formatMemoryDate(lastUpdated)}
                </span>
              </p>
              {entries.length === 0 && (
                <p data-testid="memory-self-service-empty" className={styles.empty}>
                  {t("memorySelfService.empty", "Noch keine Memory-Einträge vorhanden.")}
                </p>
              )}
            </div>
            <button
              type="button"
              data-testid="memory-self-service-delete-btn"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={entryCount === 0 || isDeleting}
              className={styles.deleteBtn}
            >
              {isDeleting ? "…" : t("memorySelfService.deleteButton", "Mein Memory löschen")}
            </button>
          </div>

          {entries.length > 0 && (
            <ul className={styles.list} data-testid="memory-self-service-list">
              {entries.map((entry) => (
                <li
                  key={entry.entry_id}
                  className={styles.listRow}
                  data-testid={`memory-self-service-row-${entry.entry_id}`}
                >
                  <div className={styles.listRowMain}>
                    <p className={styles.listContent}>{entry.content}</p>
                    <span className={styles.metaLine}>
                      {formatMemoryDate(entry.created_at)}
                    </span>
                  </div>
                  <button
                    type="button"
                    data-testid={`memory-self-service-forget-${entry.entry_id}`}
                    onClick={() => setPendingForget(entry)}
                    disabled={busyId === entry.entry_id}
                    className={styles.forgetBtn}
                  >
                    {t("memorySelfService.forgetButton", "Vergessen")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {showDeleteConfirm && (
        <ConfirmDialog
          title={t("memorySelfService.deleteButton", "Mein Memory löschen")}
          message={t(
            "memorySelfService.deleteConfirm",
            "Delete ALL of your own memory entries? This removes everything the AI has remembered about you and cannot be undone."
          )}
          confirmLabel={t("memorySelfService.deleteButton", "Mein Memory löschen")}
          onConfirm={() => {
            setShowDeleteConfirm(false);
            void handleDelete();
          }}
          onCancel={() => setShowDeleteConfirm(false)}
          testId="memory-self-service-delete-confirm"
        />
      )}

      {pendingForget && (
        <ConfirmDialog
          title={t("memorySelfService.forgetButton", "Vergessen")}
          message={t(
            "memorySelfService.forgetConfirm",
            "Diesen Eintrag endgültig löschen? Das kann nicht rückgängig gemacht werden."
          )}
          confirmLabel={t("memorySelfService.forgetButton", "Vergessen")}
          onConfirm={() => void handleForget()}
          onCancel={() => setPendingForget(null)}
          testId="memory-self-service-forget-confirm"
        />
      )}
    </section>
  );
}
