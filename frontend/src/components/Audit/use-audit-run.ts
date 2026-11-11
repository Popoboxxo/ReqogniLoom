/**
 * ARCH-L1-001 ReactFrontend — SE-Auditor run state (#598 S2).
 *
 * Extracted verbatim from `audit-dashboard.tsx` so the page keeps only
 * composition and presentation. This hook owns one audit run:
 *
 *   - the bounded first window and the "Load more" cursor (#596/#1383),
 *   - the two count sets: full-run ground truth vs. the returned window
 *     (#1382/#1383),
 *   - the local corrections accumulated after the run snapshot
 *     (`adoptedSinceRun` / `waivedSinceRun`),
 *   - the per-finding action state, keyed by `findingIdentity` (NFA-2).
 *
 * Adopt/Waive workflows stay in the component: they are user decisions, not
 * run state. They mutate this state through the setters returned here, exactly
 * as they did before the extraction.
 *
 * Stale-response guard: every `load()` bumps a generation counter and only the
 * newest generation may write its response. Without it a slow first response
 * could overwrite the findings of a newer scope/filter (#598 review focus,
 * "Race: Antwort einer überholten Anfrage überschreibt neuere").
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { TFunction } from "i18next";

import { auditApi } from "../../api/audit";
import type {
  AuditCounts,
  AuditFinding,
  AuditReport,
  AuditScopeKind,
} from "../../api/audit";
import { extractErrorMessage } from "../../api/client";

/** #596: findings per request (see the dashboard header for the measurement). */
export const FINDINGS_PAGE_SIZE = 100;

export type ActionStatus = "idle" | "pending" | "error";

export interface ActionState {
  status: ActionStatus;
  message?: string;
}

/** Per-finding action state, keyed by `findingIdentity` — never by `index`. */
export type ActionStateMap = Record<string, ActionState>;

/**
 * Extract a human-readable message from any error a fetch call can throw.
 *
 * GitHub #952: the result must NEVER be an empty/whitespace-only string. A
 * failed audit run that carries no message used to leave `loadError` falsy, so
 * the page fell straight through to the green "No findings" empty state.
 */
export function resolveErrorMessage(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : extractErrorMessage(err);
  return message.trim() ? message : fallback;
}

/**
 * Run-independent identity of a finding (#569/#1383).
 *
 * `finding_key` (rule id + artifact ids) plus the scope is stable across runs;
 * `index` is not — it is the finding's position within the run that produced
 * the response, and every "Load more" is a fresh run.
 */
export function findingIdentity(finding: AuditFinding): string {
  return `${finding.finding_key}\u001f${finding.scope ?? ""}`;
}

/** #1383: the counts of the window a report just returned. */
export function windowCounts(report: AuditReport): AuditCounts {
  return report.page_counts ?? report.counts;
}

/** #1383: the ground truth over the full run. */
export function groundTruthCounts(report: AuditReport): AuditCounts {
  if (
    report.page_counts &&
    report.counts.total === report.total_findings_available
  ) {
    return report.counts;
  }
  return {
    total: report.total_findings_available,
    blockers: report.total_blockers_available,
    warnings: report.total_warnings_available,
    suppressed: report.total_suppressed_available,
    suppressed_blockers: report.total_suppressed_blockers_available,
  };
}

/** #1383: the server cursor for the next window, or `null` for "none". */
function nextWindowOffset(report: AuditReport): number | null {
  if (!report.page_counts) return report.offset + report.findings.length;
  return report.next_offset ?? null;
}

export interface WindowCursor {
  hasMore: boolean;
  nextOffset: number | null;
  /** The backend claimed `truncated` but supplied no advancing cursor. */
  stalled: boolean;
}

/** Resolve one window's paging state against the offset that produced it. */
export function resolveWindowCursor(
  report: AuditReport,
  currentOffset: number
): WindowCursor {
  const cursor = nextWindowOffset(report);
  if (!report.truncated) return { hasMore: false, nextOffset: null, stalled: false };
  if (cursor === null || cursor <= currentOffset) {
    return { hasMore: false, nextOffset: null, stalled: true };
  }
  return { hasMore: true, nextOffset: cursor, stalled: false };
}

export interface UseAuditRunOptions {
  workspaceId: string | undefined;
  scope: AuditScopeKind;
  scopeArtifactId: string;
  artifactTypeFilter: string;
  t: TFunction;
}

export interface UseAuditRunResult {
  tier: string | null;
  setTier: Dispatch<SetStateAction<string | null>>;
  findings: AuditFinding[];
  setFindings: Dispatch<SetStateAction<AuditFinding[]>>;
  isLoading: boolean;
  loadError: string | null;
  setLoadError: Dispatch<SetStateAction<string | null>>;
  hasMore: boolean;
  setHasMore: Dispatch<SetStateAction<boolean>>;
  nextOffset: number | null;
  setNextOffset: Dispatch<SetStateAction<number | null>>;
  isLoadingMore: boolean;
  reportCounts: AuditCounts | null;
  setReportCounts: Dispatch<SetStateAction<AuditCounts | null>>;
  pageCounts: AuditCounts | null;
  setPageCounts: Dispatch<SetStateAction<AuditCounts | null>>;
  loadedWindows: number;
  setLoadedWindows: Dispatch<SetStateAction<number>>;
  adoptedSinceRun: AuditFinding[];
  setAdoptedSinceRun: Dispatch<SetStateAction<AuditFinding[]>>;
  waivedSinceRun: AuditFinding[];
  setWaivedSinceRun: Dispatch<SetStateAction<AuditFinding[]>>;
  actionState: ActionStateMap;
  setActionState: Dispatch<SetStateAction<ActionStateMap>>;
  load: () => Promise<void>;
  loadMore: () => Promise<void>;
}

export function useAuditRun({
  workspaceId,
  scope,
  scopeArtifactId,
  artifactTypeFilter,
  t,
}: UseAuditRunOptions): UseAuditRunResult {
  const [tier, setTier] = useState<string | null>(null);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [reportCounts, setReportCounts] = useState<AuditCounts | null>(null);
  const [pageCounts, setPageCounts] = useState<AuditCounts | null>(null);
  const [loadedWindows, setLoadedWindows] = useState<number>(1);
  const [adoptedSinceRun, setAdoptedSinceRun] = useState<AuditFinding[]>([]);
  const [waivedSinceRun, setWaivedSinceRun] = useState<AuditFinding[]>([]);
  const [actionState, setActionState] = useState<ActionStateMap>({});

  const generation = useRef(0);

  const load = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    if (scope === "document" && !scopeArtifactId) return;

    // Only the newest run may write. A scope/filter switch starts a new
    // generation and the previous response is discarded when it lands.
    const mine = ++generation.current;

    setIsLoading(true);
    setLoadError(null);
    try {
      const report = await auditApi.run(workspaceId, {
        scope,
        scopeArtifactId: scope === "document" ? scopeArtifactId : undefined,
        artifactType: artifactTypeFilter !== "all" ? artifactTypeFilter : undefined,
        limit: FINDINGS_PAGE_SIZE,
        offset: 0,
      });
      if (mine !== generation.current) return;
      setTier(report.tier);
      setFindings(report.findings);
      const cursor = resolveWindowCursor(report, 0);
      setHasMore(cursor.hasMore);
      setNextOffset(cursor.nextOffset);
      setReportCounts(groundTruthCounts(report));
      setPageCounts(windowCounts(report));
      setLoadedWindows(1);
      // A new run re-snapshots the server counts, so local corrections from
      // the previous snapshot no longer apply.
      setAdoptedSinceRun([]);
      setWaivedSinceRun([]);
      setActionState({});
      if (cursor.stalled) setLoadError(t("audit.pagingStalled"));
    } catch (err) {
      if (mine !== generation.current) return;
      setLoadError(
        resolveErrorMessage(err, t("audit.loadError", "Could not load audit findings."))
      );
    } finally {
      if (mine === generation.current) setIsLoading(false);
    }
  }, [workspaceId, scope, scopeArtifactId, artifactTypeFilter, t]);

  /**
   * #596: append the next window of findings.
   *
   * The append dedupe uses `findingIdentity`, not the backend's `index`: a
   * window boundary is a fresh run server-side, so indices shift as soon as
   * one finding was resolved in between.
   */
  const loadMore = useCallback(async (): Promise<void> => {
    if (!workspaceId || isLoadingMore || !hasMore || nextOffset === null) return;
    setIsLoadingMore(true);
    setLoadError(null);
    try {
      const report = await auditApi.run(workspaceId, {
        scope,
        scopeArtifactId: scope === "document" ? scopeArtifactId : undefined,
        artifactType: artifactTypeFilter !== "all" ? artifactTypeFilter : undefined,
        limit: FINDINGS_PAGE_SIZE,
        offset: nextOffset,
      });
      setFindings((prev) => {
        const seen = new Set(prev.map(findingIdentity));
        const appended = [...prev];
        for (const finding of report.findings) {
          const identity = findingIdentity(finding);
          if (seen.has(identity)) continue;
          seen.add(identity);
          appended.push(finding);
        }
        return appended;
      });
      const cursor = resolveWindowCursor(report, nextOffset);
      setHasMore(cursor.hasMore);
      setNextOffset(cursor.nextOffset);
      // Every window reports the same full-run `counts`, but a later window is
      // the freshest snapshot — and `page_counts` becomes the size of *this*
      // window, which is what the "{{shown}} of {{total}}" display names.
      setReportCounts(groundTruthCounts(report));
      setPageCounts(windowCounts(report));
      setLoadedWindows((prev) => prev + 1);
      // #1382: local deltas mean "resolved/waived since the snapshot". This
      // response *is* a new snapshot and already excludes them.
      setAdoptedSinceRun([]);
      setWaivedSinceRun([]);
      if (cursor.stalled) setLoadError(t("audit.pagingStalled"));
    } catch (err) {
      // The already-loaded findings stay readable — a failed "Load more" must
      // not discard the page the user is working through.
      setLoadError(
        resolveErrorMessage(err, t("audit.loadError", "Could not load audit findings."))
      );
    } finally {
      setIsLoadingMore(false);
    }
  }, [
    workspaceId,
    scope,
    scopeArtifactId,
    artifactTypeFilter,
    isLoadingMore,
    hasMore,
    nextOffset,
    t,
  ]);

  // Run on mount and whenever the audit context changes. The effect keeps its
  // old shape (exhaustive-deps disabled) because `load`/`loadMore` are
  // recreated on every context change anyway.
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, scope, scopeArtifactId, artifactTypeFilter]);

  return {
    tier,
    setTier,
    findings,
    setFindings,
    isLoading,
    loadError,
    setLoadError,
    hasMore,
    setHasMore,
    nextOffset,
    setNextOffset,
    isLoadingMore,
    reportCounts,
    setReportCounts,
    pageCounts,
    setPageCounts,
    loadedWindows,
    setLoadedWindows,
    adoptedSinceRun,
    setAdoptedSinceRun,
    waivedSinceRun,
    setWaivedSinceRun,
    actionState,
    setActionState,
    load,
    loadMore,
  };
}
