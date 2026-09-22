/**
 * #424 (spec section 4.5 / 7.4.1) — the `pending_ai_review` read-out for the
 * coverage surface, plus the `include_unreviewed_ai` raw-view opt-in.
 *
 * `pending_ai_review` counts the distinct TestCase artifacts excluded from
 * coverage **only** because they are `ai_generated` and not yet `reviewed`
 * (the false-green pair from #424). It is `0` in the raw view
 * (`include_unreviewed_ai=true`), where unreviewed AI tests count again.
 *
 * Scope guardrail: the spec only defines this opt-in on the coverage-report
 * contract, so the toggle is exposed **only here**, next to the number it
 * changes — never as a global list/settings switch.
 *
 * States handled: loading (renders nothing), error (fail-open, renders
 * nothing — the surrounding client-side coverage summary stays authoritative),
 * empty (no unreviewed AI test case and raw view off → renders nothing),
 * success (count + toggle).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { requirementsApi } from "../../api/requirements";
import type { RequirementCoverageReport } from "../../api/requirements";
import styles from "./PendingAiReviewNote.module.css";

export interface PendingAiReviewNoteProps {
  workspaceId: string;
}

export function PendingAiReviewNote({
  workspaceId,
}: PendingAiReviewNoteProps): JSX.Element | null {
  const { t } = useTranslation();
  const [includeUnreviewedAi, setIncludeUnreviewedAi] = useState(false);
  const [summary, setSummary] = useState<RequirementCoverageReport["summary"] | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Fail-open even if the wrapper is unavailable (a partially mocked API in
    // a host test): this note is advisory and must never break the view.
    let request: Promise<RequirementCoverageReport> | undefined;
    try {
      request = requirementsApi.coverageReport(workspaceId, { includeUnreviewedAi });
    } catch {
      request = undefined;
    }
    if (!request) {
      setSummary(null);
      return () => {
        cancelled = true;
      };
    }
    request
      .then((report) => {
        if (!cancelled) setSummary(report?.summary ?? null);
      })
      .catch(() => {
        // Fail-open: this is an advisory note on top of the client-side
        // coverage summary, never a blocker for the traceability view.
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, includeUnreviewedAi]);

  if (!summary) return null;

  const pending = summary.pending_ai_review ?? 0;
  // "empty" = nothing excluded and raw view off -> no note at all. Once the
  // raw view is on the note must stay visible, or the user could never switch
  // it back off (pending drops to 0 in that view).
  if (pending === 0 && !includeUnreviewedAi) return null;

  return (
    <div className={styles.note} data-testid="coverage-pending-ai-review">
      {pending > 0 ? (
        <span className={styles.count} data-testid="coverage-pending-ai-review-count">
          {t("traceability.pendingAiReview", { count: pending })}
        </span>
      ) : null}
      <label className={styles.toggle}>
        <input
          type="checkbox"
          data-testid="coverage-include-unreviewed-ai"
          checked={includeUnreviewedAi}
          onChange={(event) => setIncludeUnreviewedAi(event.target.checked)}
        />
        {t("traceability.includeUnreviewedAi")}
      </label>
    </div>
  );
}

PendingAiReviewNote.displayName = "PendingAiReviewNote";
