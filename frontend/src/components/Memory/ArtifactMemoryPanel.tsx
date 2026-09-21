/**
 * ARCH-L1-001 ReactFrontend — ArtifactMemoryPanel (RFC #1002, PR D).
 *
 * The "Gedächtnis" section on the artifact detail page: lists the
 * artifact-scoped facts (`GET /artifacts/{id}/memory/`), shows the fact count
 * as a badge and offers a create action (Editor+), plus per-row forget for
 * Workspace-Admins. Reused by the requirement detail page; the component is
 * artifact-id driven so any future detail page can mount it unchanged.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractApiErrorMessage } from "../../api/client";
import { memoryApi, type MemoryEntry } from "../../api/memory";
import { useHasRole } from "../../hooks/useHasRole";
import type { UUID } from "../../types";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { AddMemoryFactDialog } from "./AddMemoryFactDialog";
import { contributorLabel, formatMemoryDate } from "./memory-format";
import styles from "./ArtifactMemoryPanel.module.css";

export interface ArtifactMemoryPanelProps {
  artifactId: UUID;
}

export function ArtifactMemoryPanel({
  artifactId,
}: ArtifactMemoryPanelProps): JSX.Element {
  const { t } = useTranslation();
  const hasRole = useHasRole();

  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [degraded, setDegraded] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [pendingForget, setPendingForget] = useState<MemoryEntry | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const page = await memoryApi.listArtifactMemory(artifactId, {
        page_size: 25,
      });
      setEntries(page.items ?? []);
      setTotal(page.total ?? 0);
      setDegraded(Boolean(page.degraded));
      setHasLoaded(true);
    } catch (err: unknown) {
      setLoadError(
        extractApiErrorMessage(err) ??
          t("memory.panel.loadError", "Gedächtnis konnte nicht geladen werden.")
      );
      setHasLoaded(true);
    } finally {
      setIsLoading(false);
    }
  }, [artifactId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleForget = useCallback(async (): Promise<void> => {
    if (!pendingForget) return;
    const entryId = pendingForget.entry_id;
    setPendingForget(null);
    setBusyId(entryId);
    setActionError(null);
    try {
      await memoryApi.forgetEntry(entryId);
      await load();
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ??
          t("memory.action.forgetError", "Vergessen fehlgeschlagen.")
      );
    } finally {
      setBusyId(null);
    }
  }, [pendingForget, load, t]);

  const handleCreated = useCallback((): void => {
    setShowAdd(false);
    void load();
  }, [load]);

  return (
    <section className={styles.panel} data-testid="artifact-memory-panel">
      <div className={styles.headerRow}>
        <h3 className={styles.heading}>
          {t("memory.panel.heading", "Gedächtnis")}
          <span className={styles.countBadge} data-testid="artifact-memory-count">
            {total}
          </span>
        </h3>
        {hasRole("editor") && (
          <button
            type="button"
            className="btn-secondary"
            data-testid="artifact-memory-add-btn"
            onClick={() => setShowAdd(true)}
          >
            {t("memory.add.title", "Fakt hinzufügen")}
          </button>
        )}
      </div>
      <p className={styles.hint}>
        {t(
          "memory.panel.hint",
          "Fakten, die die KI sich zu diesem Artefakt gemerkt hat. Sie fließen in künftige Vorschläge ein."
        )}
      </p>

      {degraded && (
        <p role="status" data-testid="artifact-memory-degraded" className={styles.degraded}>
          {t("memory.degraded", "Gedächtnis aktuell nicht erreichbar.")}
        </p>
      )}

      {loadError && (
        <p role="alert" data-testid="artifact-memory-error" className={styles.error}>
          {loadError}
        </p>
      )}
      {actionError && (
        <p role="alert" data-testid="artifact-memory-action-error" className={styles.error}>
          {actionError}
        </p>
      )}

      {isLoading && (
        <p role="status" data-testid="artifact-memory-loading" className={styles.loading}>
          {t("loading", "Loading...")}
        </p>
      )}

      {!isLoading && !loadError && hasLoaded && entries.length === 0 && (
        <p data-testid="artifact-memory-empty" className={styles.empty}>
          {t("memory.panel.empty", "Noch keine Fakten zu diesem Artefakt.")}
        </p>
      )}

      {!isLoading && entries.length > 0 && (
        <ul className={styles.list} data-testid="artifact-memory-list">
          {entries.map((entry) => {
            const isBusy = busyId === entry.entry_id;
            return (
              <li
                key={entry.entry_id}
                className={styles.row}
                data-testid={`artifact-memory-row-${entry.entry_id}`}
              >
                <div className={styles.rowMain}>
                  <p className={styles.content}>{entry.content}</p>
                  <div className={styles.metaRow}>
                    <span className={styles.badge} data-testid={`artifact-memory-contributor-${entry.entry_id}`}>
                      {contributorLabel(entry, t)}
                    </span>
                    <span className={styles.meta}>
                      {formatMemoryDate(entry.created_at)}
                    </span>
                  </div>
                </div>
                {hasRole("admin") && (
                  <button
                    type="button"
                    className={styles.forgetBtn}
                    data-testid={`artifact-memory-forget-${entry.entry_id}`}
                    disabled={isBusy}
                    onClick={() => {
                      setActionError(null);
                      setPendingForget(entry);
                    }}
                  >
                    {t("memory.action.forget", "Vergessen")}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {showAdd && (
        <AddMemoryFactDialog
          artifacts={[]}
          fixedArtifactId={artifactId}
          defaultScope="artifact"
          onClose={() => setShowAdd(false)}
          onCreated={handleCreated}
        />
      )}

      {pendingForget && (
        <ConfirmDialog
          title={t("memory.action.forget", "Vergessen")}
          message={t(
            "memory.action.forgetConfirm",
            "Diesen Fakt endgültig vergessen? Das kann nicht rückgängig gemacht werden."
          )}
          confirmLabel={t("memory.action.forget", "Vergessen")}
          onConfirm={() => void handleForget()}
          onCancel={() => setPendingForget(null)}
          testId="artifact-memory-forget-confirm"
        />
      )}
    </section>
  );
}
