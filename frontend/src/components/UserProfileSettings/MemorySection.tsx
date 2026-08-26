/**
 * ARCH-L1-001 ReactFrontend — MemorySection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Memory Admin UI Phase 4 (spec 2026-08-26): GDPR-style self-service erasure
 * control for the authenticated user's OWN UserTenantMemory rows — never
 * WorkspaceMemory, which is team-owned and stays exclusively under the
 * System-Admin "Memory" tab (MemoryAdminService, Phase 1). No admin gate:
 * any authenticated user, no role required (mirrors ApiKeysSection).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  memorySelfServiceApi,
  type MemorySelfServiceOverview,
} from "../../api/memory-self-service";
import styles from "./MemorySection.module.css";

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

const EMPTY_OVERVIEW: MemorySelfServiceOverview = {
  entry_count: 0,
  last_updated_at: null,
};

export function MemorySection(): JSX.Element {
  const { t } = useTranslation();
  const [overview, setOverview] = useState<MemorySelfServiceOverview>(EMPTY_OVERVIEW);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await memorySelfServiceApi.get();
      setOverview(result);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (
      !window.confirm(
        t(
          "memorySelfService.deleteConfirm",
          "Delete ALL of your own memory entries? This removes everything the AI has remembered about you and cannot be undone."
        )
      )
    ) {
      return;
    }
    setIsDeleting(true);
    setError(null);
    try {
      await memorySelfServiceApi.deleteAll();
      setOverview(EMPTY_OVERVIEW);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  }, [t]);

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
                  {overview.entry_count}
                </span>
              </p>
              <p className={styles.metaLine}>
                {t("memorySelfService.lastUpdatedLabel", "Zuletzt aktualisiert")}:{" "}
                <span data-testid="memory-self-service-last-updated">
                  {formatDate(overview.last_updated_at)}
                </span>
              </p>
              {overview.entry_count === 0 && (
                <p data-testid="memory-self-service-empty" className={styles.empty}>
                  {t("memorySelfService.empty", "Noch keine Memory-Einträge vorhanden.")}
                </p>
              )}
            </div>
            <button
              type="button"
              data-testid="memory-self-service-delete-btn"
              onClick={() => void handleDelete()}
              disabled={overview.entry_count === 0 || isDeleting}
              className={styles.deleteBtn}
            >
              {isDeleting ? "…" : t("memorySelfService.deleteButton", "Mein Memory löschen")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
