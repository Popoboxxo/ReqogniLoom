/**
 * ARCH-L1-001 ReactFrontend — ReviewHistoryPanel (COMP-RF-REV-003).
 *
 * leaf_id: COMP-RF-REV-003
 * req_id:  REQ-144 (Review/Approval UI — workflow history tab)
 *
 * Renders the append-only workflow transition log for a requirement:
 * from -> to state, actor, timestamp, and a sealed/unsigned indicator. Pure
 * presentational component — data-fetching lives in useReviewsData.
 *
 * Interfaces consumed (via the parent's data hook):
 *   IF-RF-EXT-OUT-001 → GET /api/v1/requirements/{id}/workflow-history/
 */

import { useTranslation } from "react-i18next";
import type { WorkflowHistoryEntry } from "../../api/requirements";
import styles from "./ReviewHistoryPanel.module.css";

export interface ReviewHistoryPanelProps {
  entries: WorkflowHistoryEntry[];
  isLoading: boolean;
  error: string | null;
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function ReviewHistoryPanel({
  entries,
  isLoading,
  error,
}: ReviewHistoryPanelProps): JSX.Element {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <p role="status" data-testid="review-history-loading" className={styles.mutedText}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <p role="alert" data-testid="review-history-error" className={styles.errorText}>
        {t("reviews.historyLoadError", "Failed to load workflow history.")} ({error})
      </p>
    );
  }

  if (entries.length === 0) {
    return (
      <p data-testid="review-history-empty" className={styles.mutedText}>
        {t("reviews.historyEmpty", "No transitions recorded yet.")}
      </p>
    );
  }

  return (
    <ul data-testid="review-history-list" className={styles.list}>
      {entries.map((entry) => (
        <li
          key={entry.id}
          data-testid={`review-history-entry-${entry.id}`}
          className={styles.entry}
        >
          <div>
            <div className={styles.entryTransition}>
              {entry.from_state ?? "—"} → {entry.to_state}
            </div>
            <div className={styles.entryMeta}>
              {entry.actor} · {formatTimestamp(entry.transitioned_at)}
            </div>
            {entry.change_reason && (
              <div className={styles.entryReason}>{entry.change_reason}</div>
            )}
          </div>
          <span
            data-testid={`review-history-sealed-${entry.id}`}
            title={
              entry.sealed
                ? t("reviews.historySealed", "Signed")
                : t("reviews.historyUnsealed", "Unsigned")
            }
            aria-label={
              entry.sealed
                ? t("reviews.historySealed", "Signed")
                : t("reviews.historyUnsealed", "Unsigned")
            }
            className={styles.sealIcon}
          >
            {entry.sealed ? "🔒" : "—"}
          </span>
        </li>
      ))}
    </ul>
  );
}

ReviewHistoryPanel.displayName = "ReviewHistoryPanel";
