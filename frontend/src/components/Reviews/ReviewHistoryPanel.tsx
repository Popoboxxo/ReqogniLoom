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
      <p role="status" data-testid="review-history-loading" style={{ color: "var(--color-text-muted)" }}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <p role="alert" data-testid="review-history-error" style={{ color: "var(--color-danger)" }}>
        {t("reviews.historyLoadError", "Failed to load workflow history.")} ({error})
      </p>
    );
  }

  if (entries.length === 0) {
    return (
      <p data-testid="review-history-empty" style={{ color: "var(--color-text-muted)" }}>
        {t("reviews.historyEmpty", "No transitions recorded yet.")}
      </p>
    );
  }

  return (
    <ul data-testid="review-history-list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {entries.map((entry) => (
        <li
          key={entry.id}
          data-testid={`review-history-entry-${entry.id}`}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "var(--space-3)",
            padding: "var(--space-2) 0",
            borderBottom: "1px solid var(--color-border)",
          }}
        >
          <div>
            <div style={{ fontWeight: 600 }}>
              {entry.from_state ?? "—"} → {entry.to_state}
            </div>
            <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
              {entry.actor} · {formatTimestamp(entry.transitioned_at)}
            </div>
            {entry.change_reason && (
              <div style={{ fontSize: "var(--font-size-sm)" }}>{entry.change_reason}</div>
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
            style={{ fontSize: "1.1rem" }}
          >
            {entry.sealed ? "🔒" : "—"}
          </span>
        </li>
      ))}
    </ul>
  );
}

ReviewHistoryPanel.displayName = "ReviewHistoryPanel";
