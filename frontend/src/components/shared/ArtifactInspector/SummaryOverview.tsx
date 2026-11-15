/**
 * SummaryOverview — the stored **type stand** of the inspected artifact type
 * (issue #1793, surfaced in S8).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089, REQ-L1-093
 *
 * The Summary tab answers "what does the AI say about *this item*" on demand.
 * This block above it answers the cheaper, read-only question "what does the
 * AI say about *this workspace's whole type roster*" — a state the periodic
 * sweep keeps fresh without any click.
 *
 * Three rules:
 *
 *  1. **No workspace, no request.** The read is free but pointless without a
 *     scope, and an unscoped call would be a cross-workspace leak risk; the
 *     effect returns early instead of asking.
 *  2. **Degradation stays visible with its reason.** `stale` and the four E11
 *     reasons are shown as text, never as a bare badge without cause.
 *  3. **Refresh is a write.** The button only renders when the caller holds a
 *     write role (`canRefresh`); the backend enforces the same rule. Read-only
 *     callers see the stand and nothing else.
 *
 * Types outside the sweep vocabulary (`DEFAULT_SUMMARY_SCOPES`) render
 * nothing: there is no stored stand to show, and a request would only answer
 * the empty payload.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  fetchTypeSummary,
  refreshTypeSummary,
  type StoredSummary,
  type SummaryDegradedReason,
} from "../../../api/artifact-summary";
import { useInspectorAnnouncer } from "./InspectorLiveRegions";
import {
  REASON_FALLBACKS,
  REASON_LABEL_KEYS,
  formatGeneratedAt,
} from "./summaryReasonLabels";
import type { ArtifactKind } from "./types";
import styles from "./SummaryOverview.module.css";

/**
 * Inspector kind -> backend `artifact_type` spelling, limited to the types the
 * periodic sweep summarises (``DEFAULT_SUMMARY_SCOPES``). `diagram`, `glossary`
 * and `mainGoal` on purpose have no entry: there is no type-roster stand.
 */
export const SUMMARY_TYPE_BY_KIND: Partial<Record<ArtifactKind, string>> = {
  requirement: "Requirement",
  stakeholderNeed: "StakeholderNeed",
  architecture: "ArchitectureElement",
  testCase: "TestCase",
  adr: "Adr",
  risk: "Risk",
  issue: "Issue",
  goal: "Goal",
  icd: "Icd",
};

export interface SummaryOverviewProps {
  /** Active workspace; `null`/empty means "no request, render nothing". */
  workspaceId: string | null | undefined;
  /** Backend `artifact_type` (e.g. `Requirement`), not the inspector kind. */
  artifactType: string | null | undefined;
  /** Whether the caller may spend a refresh (write role on the workspace). */
  canRefresh?: boolean;
}

export function SummaryOverview({
  workspaceId,
  artifactType,
  canRefresh = false,
}: SummaryOverviewProps): JSX.Element | null {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;
  const announcer = useInspectorAnnouncer();

  const mountedRef = useRef(true);
  const requestRef = useRef(0);

  const [summary, setSummary] = useState<StoredSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const scopeReady = Boolean(workspaceId) && Boolean(artifactType);

  useEffect(() => {
    requestRef.current += 1;
    const token = requestRef.current;
    setSummary(null);
    setError(null);
    // Rule 1: an unscoped read is not a request worth making.
    if (!scopeReady) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void fetchTypeSummary(workspaceId as string, artifactType as string)
      .then((next) => {
        if (!mountedRef.current || token !== requestRef.current) return;
        setSummary(next);
      })
      .catch(() => {
        if (!mountedRef.current || token !== requestRef.current) return;
        setError(tRef.current("summary.overview.loadFailed", "The type summary could not be loaded."));
      })
      .finally(() => {
        if (mountedRef.current && token === requestRef.current) setLoading(false);
      });
  }, [workspaceId, artifactType, scopeReady]);

  const refresh = useCallback(async (): Promise<void> => {
    if (!workspaceId || !artifactType || !canRefresh) return;
    const token = (requestRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const next = await refreshTypeSummary(workspaceId, artifactType);
      if (!mountedRef.current || token !== requestRef.current) return;
      setSummary(next);
      announcer?.polite(
        tRef.current("summary.overview.refreshed", "Type summary refreshed."),
      );
    } catch {
      if (!mountedRef.current || token !== requestRef.current) return;
      const message = tRef.current(
        "summary.overview.refreshFailed",
        "The type summary could not be refreshed.",
      );
      setError(message);
      announcer?.alert(message);
    } finally {
      if (mountedRef.current && token === requestRef.current) setLoading(false);
    }
  }, [workspaceId, artifactType, canRefresh, announcer]);

  if (!scopeReady) return null;

  const reasonLabel = (reason: SummaryDegradedReason): string =>
    t(REASON_LABEL_KEYS[reason], REASON_FALLBACKS[reason]);

  const hasText = Boolean(summary?.text);
  const showEmpty = !loading && !error && summary !== null && !hasText && !summary.reason;

  return (
    <section
      className={styles.overview}
      aria-label={t("summary.overview.ariaLabel", "Type overview")}
      aria-busy={loading}
      data-testid="summary-overview"
      data-artifact-type={artifactType ?? ""}
    >
      <div className={styles.header}>
        <h4 className={styles.heading}>
          {t("summary.overview.title", "Overview")}
        </h4>
        {canRefresh && (
          <button
            type="button"
            className={`btn-secondary ${styles.action}`}
            disabled={loading}
            onClick={(): void => void refresh()}
            data-testid="summary-overview-refresh"
          >
            {loading
              ? t("summary.overview.working", "Refreshing …")
              : t("summary.overview.refresh", "Refresh type summary")}
          </button>
        )}
      </div>

      {loading && !summary && (
        <p className={styles.loading} role="status" data-testid="summary-overview-loading">
          {t("summary.overview.loading", "Loading type summary …")}
        </p>
      )}

      {error && (
        <p className={styles.error} data-testid="summary-overview-error">
          {error}
        </p>
      )}

      {hasText && (
        <p className={styles.text} data-testid="summary-overview-text">
          {summary?.text}
        </p>
      )}

      {showEmpty && (
        <p className={styles.empty} data-testid="summary-overview-empty">
          {t("summary.overview.empty", "No type summary stored yet.")}
        </p>
      )}

      {summary && (hasText || summary.reason) && (
        <p className={styles.meta} data-testid="summary-overview-meta">
          {summary.itemCount > 0 && (
            <>
              {t("summary.overview.itemCount", {
                n: summary.itemCount,
                defaultValue: "{{n}} artifacts",
              })}
              {" · "}
            </>
          )}
          {summary.generatedAt && (
            <>
              {t("summary.overview.generatedAt", {
                date: formatGeneratedAt(summary.generatedAt),
                defaultValue: "As of {{date}}",
              })}
              {" · "}
            </>
          )}
          {summary.stale && (
            <span className={styles.stale} data-testid="summary-overview-stale">
              {t("summary.overview.staleBadge", "Out of date")}
            </span>
          )}
        </p>
      )}

      {summary?.reason && (
        <p
          className={styles.reason}
          data-testid="summary-overview-reason"
          data-reason={summary.reason}
        >
          {reasonLabel(summary.reason)}
        </p>
      )}
    </section>
  );
}
