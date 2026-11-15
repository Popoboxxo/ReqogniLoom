/**
 * SummaryPanel — on-demand AI summary of the inspected artifact (Issue #1792, S2).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089, REQ-L1-093
 *
 * Mounted as the "Summary" tab of the shared shell. Two rules shape it:
 *
 *  1. **No request on mount.** A summary costs one provider call, so the
 *     first request happens on the user's click only (spec §5.1). Switching
 *     the inspected artifact resets the panel to the idle state instead of
 *     firing a request for the new one.
 *  2. **Degradation stays visible with its reason.** The endpoint answers
 *     200 with `degraded` + `degraded_reason`; a silent "nothing here" would
 *     be indistinguishable from "no neighbours" (spec §9/E11). All four
 *     enum values get a translated sentence.
 *
 * Focus never leaves the one action button: its label changes between
 * "Summarize" / "Refresh" / "Try again", but the DOM node stays, so a keyboard
 * user does not get dropped back into the tablist after the answer arrives.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  fetchArtifactSummary,
  type ArtifactSummary,
  type SummaryDegradedReason,
} from "../../../api/artifact-summary";
import { useInspectorAnnouncer } from "./InspectorLiveRegions";
import styles from "./SummaryPanel.module.css";

export interface SummaryPanelProps {
  /** Backing generic Artifact UUID — never the domain-entity id. */
  artifactId: string;
  /** Artifact kind of the inspected item (e.g. `requirement`), for diagnostics. */
  artifactType: string;
}

const REASON_LABEL_KEYS: Record<SummaryDegradedReason, string> = {
  budget_exhausted: "summary.reason.budget_exhausted",
  provider_unavailable: "summary.reason.provider_unavailable",
  stale: "summary.reason.stale",
  disabled: "summary.reason.disabled",
};

const REASON_FALLBACKS: Record<SummaryDegradedReason, string> = {
  budget_exhausted: "The AI budget for this period is exhausted.",
  provider_unavailable: "The AI provider is currently unavailable.",
  stale: "The stored summary is out of date.",
  disabled: "AI summaries are disabled for this workspace.",
};

function formatGeneratedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function SummaryPanel({
  artifactId,
  artifactType,
}: SummaryPanelProps): JSX.Element {
  const { t } = useTranslation();
  // Async callbacks must not re-key on `t`'s identity (some hosts return a
  // fresh function per render); the ref carries the latest translator.
  const tRef = useRef(t);
  tRef.current = t;
  const announcer = useInspectorAnnouncer();

  const mountedRef = useRef(true);
  // Monotonic token: an answer that belongs to a previously inspected
  // artifact must not overwrite the current panel.
  const requestRef = useRef(0);

  const [summary, setSummary] = useState<ArtifactSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Different artifact → different summary. Reset, invalidate in-flight
  // answers, and do not fetch: the click stays the only trigger.
  useEffect(() => {
    requestRef.current += 1;
    setSummary(null);
    setError(null);
    setLoading(false);
  }, [artifactId]);

  const load = useCallback(
    async (refresh: boolean): Promise<void> => {
      // No Artifact UUID → no request at all (defensive twin of the tab
      // matrix, which already hides this tab for such kinds).
      if (!artifactId) return;
      const token = (requestRef.current += 1);
      setLoading(true);
      setError(null);
      try {
        const next = await fetchArtifactSummary(artifactId, { refresh });
        if (!mountedRef.current || token !== requestRef.current) return;
        setSummary(next);
        announcer?.polite(tRef.current("summary.loaded", "Summary loaded."));
      } catch {
        if (!mountedRef.current || token !== requestRef.current) return;
        const message = tRef.current(
          "summary.error",
          "The summary could not be loaded.",
        );
        setError(message);
        announcer?.alert(message);
      } finally {
        if (mountedRef.current && token === requestRef.current) setLoading(false);
      }
    },
    [artifactId, announcer],
  );

  const hasSummary = summary !== null;
  const actionLabel = loading
    ? t("summary.working", "Generating …")
    : error
      ? t("summary.retry", "Try again")
      : hasSummary
        ? t("summary.refresh", "Refresh")
        : t("summary.trigger", "Summarize");

  const reasonLabel = (reason: SummaryDegradedReason | null): string =>
    reason
      ? t(REASON_LABEL_KEYS[reason], REASON_FALLBACKS[reason])
      : t("summary.reason.unknown", "No reason given.");

  return (
    <section
      className={styles.panel}
      aria-label={t("summary.ariaLabel", "AI summary")}
      aria-busy={loading}
      data-testid="summary-panel"
      data-artifact-type={artifactType}
    >
      <div className={styles.header}>
        <h3 className={styles.heading}>{t("summary.title", "Summary")}</h3>
        <button
          type="button"
          className={`btn-secondary ${styles.action}`}
          disabled={loading || !artifactId}
          onClick={(): void => void load(hasSummary)}
          data-testid="summary-trigger"
        >
          {actionLabel}
        </button>
      </div>

      {loading && (
        <p className={styles.loading} role="status" data-testid="summary-loading">
          {t("summary.loading", "Generating summary …")}
        </p>
      )}

      {error && (
        <p className={styles.error} data-testid="summary-error">
          {error}
        </p>
      )}

      {summary && summary.summary && (
        <p className={styles.text} data-testid="summary-text">
          {summary.summary}
        </p>
      )}

      {summary?.degraded && (
        <div className={styles.degraded} data-testid="summary-degraded">
          <p className={styles.degradedTitle}>
            {t("summary.degraded", "No AI summary available.")}
          </p>
          <p className={styles.degradedReason} data-testid="summary-degraded-reason">
            {reasonLabel(summary.degradedReason)}
          </p>
        </div>
      )}

      {summary && (
        <p className={styles.meta} data-testid="summary-meta">
          {t("summary.meta", {
            n: summary.neighbourCount,
            depth: summary.traceDepth,
            defaultValue: "Neighbours: {{n}} · depth {{depth}}",
          })}
          {summary.omittedNeighbours > 0 && (
            <>
              {" · "}
              {t("summary.omitted", {
                n: summary.omittedNeighbours,
                defaultValue: "{{n}} more omitted",
              })}
            </>
          )}
          {" · "}
          {t("summary.generatedAt", {
            date: formatGeneratedAt(summary.generatedAt),
            defaultValue: "Generated: {{date}}",
          })}
          {summary.cacheHit && (
            <>
              {" · "}
              {t("summary.cacheHit", "from cache")}
            </>
          )}
        </p>
      )}

      {!loading && !error && !summary && (
        <p className={styles.empty} data-testid="summary-empty">
          {t("summary.idle", "Not summarized yet.")}
        </p>
      )}
    </section>
  );
}
