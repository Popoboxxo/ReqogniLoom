/**
 * ARCH-L1-001 ReactFrontend — Audit Dashboard (SE-Auditor UI).
 *
 * UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3 ("Auditor UI").
 *
 * Runs the workspace-scoped SE-Auditor (GET .../audit/) and renders its
 * findings grouped by rule id, with per-group blocker/warning badges and a
 * scope selector (project/document/global — document scope additionally
 * needs a root-artifact pick).
 *
 * Per-finding actions (GitHub #451, extended by #569)
 * --------------------------------------------------
 * Each finding gets the Adopt/Modify action that follows the backend's
 * remediation analysis (`traceability/audit/remediation.py`), not the rule id:
 *
 *   - `remediation.automatic === true`  -> **Adopt**: POST .../audit/remediate/
 *     applies the proposal the backend already derived (today only TRACE-P1/P2/
 *     P5 register one, which is why "Adopt" looks rule-specific in the UI — it
 *     is not; the legend below states the distinction).
 *   - `remediation.automatic === false` -> **Modify**: there is no "edit a
 *     finding" endpoint and there cannot be one — findings are derived live from
 *     the trace graph, never persisted, so the only way to clear one is to
 *     correct the underlying artifact. The button therefore navigates to that
 *     artifact's editor (`/traceability/resolve/` maps the finding's Artifact id
 *     to the entity id the SPA routes take, see `use-finding-targets.ts`).
 *
 * #569 adds a **third, independent** action, "Waive": record a justified
 * suppression for a reported BLOCKER finding (POST .../audit/waivers/). It
 * removes nothing — the finding stays in the list, marked as suppressed with
 * its justification and expiry, so the decision stays visible
 * ("Nachvollziehbarkeit statt Verstecken"). Its failures are handled by their
 * stable `error.code` and are deliberately NEVER routed into the Adopt/Modify
 * flip: HTTP 422 is reserved for `remediate` in this module and the waive
 * endpoints never emit it, so a rejected justification must surface as a
 * reason-specific message, not as a silent "Modify" state change.
 *
 * Before #451 the Modify button was permanently `disabled`, which left findings
 * without an automatic proposal — the overwhelming majority — with no path
 * forward at all. Combined with the fail-closed baseline gate (#490) that is a
 * workflow deadlock: blockers must be resolved before a baseline can be created,
 * but nothing in the UI could resolve them.
 *
 * When the subject artifact cannot be resolved to an editor route (dangling
 * artifact, or a type without a backing domain row — `resolved: false`), no
 * button is rendered at all: a control that cannot do anything is worse than no
 * control. The reason text stays visible in both cases, as text and not just as
 * a hover `title`, which is not discoverable via keyboard/touch/screen reader.
 *
 * Adopt success removes the finding from the list; a 422 response (not
 * automatically fixable) flips the finding into the "Modify" state in-place
 * instead of leaving a dead button.
 *
 * The scope selector and severity filter stay interactive during a refresh
 * (mirrors ListToolbar's list pages, GitHub #450) — only the Refresh button
 * itself disables while its own request is in flight.
 *
 * The rigor tier (minimal/standard/extended) is resolved server-side from
 * the workspace's active preset — this dashboard only displays it.
 *
 * Bounded DOM / paging (#596)
 * ---------------------------
 * Mounting every returned finding at once measured ~480 KB of DOM text at
 * 500 findings (GitHub #596). The dashboard therefore walks the backend's
 * #622 `?limit=&offset=` window — one bounded page of findings is mounted,
 * the rest is pulled in on demand through "Load more". `report.truncated`
 * keeps its meaning per window ("more findings exist past this one"), the
 * grouping-by-rule and the Adopt/Modify actions are unchanged, and the count
 * badges keep showing the backend's true pre-window totals until every page
 * has been loaded.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { auditApi } from "../../api/audit";
import type {
  AuditFinding,
  AuditScopeKind,
  SuppressionView,
  WaiveRequest,
} from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import { extractErrorMessage } from "../../api/client";
import { ForbiddenError, UnprocessableEntityError } from "../../api/errors";
import type { ApiError, Artifact } from "../../types";
import { Badge } from "../shared/Badge";
import { PageHeader } from "../shared/PageHeader";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { Dialog } from "../shared/Dialog";
import { primaryTarget, useFindingTargets } from "./use-finding-targets";
import type { FindingTarget, FindingTargetMap } from "./use-finding-targets";
import styles from "./audit-dashboard.module.css";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SCOPES: AuditScopeKind[] = ["project", "document", "global"];

/**
 * #596: findings per request. The DOM measurement in the issue (~480 KB of
 * text at 500 findings) put the per-finding cost near 1 KB, so a page of 100
 * keeps the mounted subtree around 100 KB regardless of how many findings the
 * run produced. The backend caps the value at AuditService.MAX_REPORT_FINDINGS.
 */
const FINDINGS_PAGE_SIZE = 100;

type ActionStatus = "idle" | "pending" | "error";

interface ActionState {
  status: ActionStatus;
  message?: string;
}

/**
 * Extract a human-readable message from any error a fetch call can throw.
 *
 * GitHub #952: the result must NEVER be an empty/whitespace-only string. A
 * failed audit run that carries no message (e.g. a network failure surfaced
 * with `new Error("")`) used to leave `loadError` falsy, so the page fell
 * straight through to the green "No findings — the trace graph is consistent"
 * empty state — the UI reported a *successful* run for a run that failed. The
 * `fallback` is the user-facing message used whenever the thrown error itself
 * carries nothing.
 */
function resolveErrorMessage(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : extractErrorMessage(err);
  return message.trim() ? message : fallback;
}

/** Defensive label for an /artifacts/ row — the payload exposes no title/name
 * field today (same caveat as BaselinesView's document-scope picker), so we
 * read them optimistically and fall back to a truncated id. */
function artifactLabel(a: Artifact): string {
  const named = a as Artifact & { title?: string; name?: string };
  const label = named.title ?? named.name ?? `${a.id.slice(0, 8)}…`;
  return `${a.artifact_type} — ${label}`;
}

/**
 * #569: the stable `error.code` of a thrown API error, if any.
 *
 * Two different shapes reach a caller: the non-2xx path of `apiFetch` throws
 * the parsed `{error: {code, message, details}}` body (so the code lives on
 * the object rather than on an `Error` subclass), but `apiFetch` intercepts
 * **403 before** that generic path and throws `ForbiddenError` — a plain
 * `Error` subclass that carries **no** `.error` property (client.ts:287-301).
 * Reading only `apiErr.error.code` therefore made the `PERMISSION_DENIED`
 * branch dead on REST: a real 403 (no Admin/Approver role, or an AUTHOR-tier
 * API key) resolved to `null` and the dedicated forbidden message was
 * unreachable. `ForbiddenError` is mapped back onto its stable code here so
 * both transports land on the same branch.
 *
 * Callers must branch on this code — not on the HTTP status, and never on 422
 * (which the waive paths deliberately never emit; see spec E18).
 */
function waiverErrorCode(err: unknown): string | null {
  if (err instanceof ForbiddenError) return "PERMISSION_DENIED";
  const apiErr = err as Partial<ApiError> | null;
  return apiErr?.error?.code ?? null;
}

/** Render an ISO-8601 expiry for display; invalid input degrades to the raw string. */
function formatExpiry(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AuditDashboard(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();

  const [scope, setScope] = useState<AuditScopeKind>("project");
  const [scopeArtifactId, setScopeArtifactId] = useState<string>("");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);

  const [tier, setTier] = useState<string | null>(null);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // #596: the findings list is mounted in bounded windows instead of all at
  // once. `hasMore` is the backend's per-window `truncated` flag ("more
  // findings exist past this one"), `nextOffset` the start of the following
  // window (`offset + len(findings)`, per the #622 contract).
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [nextOffset, setNextOffset] = useState<number>(0);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  // BUG-15: the backend also reports how many findings the run produced in
  // total (pre-window), so the count badges can show the real numbers instead
  // of only counting the (possibly partial) loaded `findings` array — a
  // workspace with 4,440 real blockers must not show "100" with no indication
  // that count is partial.
  const [totalFindingsAvailable, setTotalFindingsAvailable] = useState<number>(0);
  const [totalBlockersAvailable, setTotalBlockersAvailable] = useState<number>(0);
  const [totalWarningsAvailable, setTotalWarningsAvailable] = useState<number>(0);
  // #569: absolute (pre-cap, pre-filter) suppression totals from the last run.
  const [totalSuppressedAvailable, setTotalSuppressedAvailable] = useState<number>(0);
  const [totalSuppressedBlockersAvailable, setTotalSuppressedBlockersAvailable] =
    useState<number>(0);

  const [severityFilter, setSeverityFilter] = useState<"all" | "blocker" | "warning">("all");
  // #569: "show suppressed" is on by default — nothing is hidden by default
  // (O3). Unchecking filters `suppressed === true` client-side; the report
  // itself always keeps suppressed findings (include_suppressed default true).
  const [showSuppressed, setShowSuppressed] = useState<boolean>(true);
  // #569: every persisted suppression, both lifecycles — so an *expired*
  // suppression is visible and visually distinct from an active one (the
  // report only marks active ones).
  const [waivers, setWaivers] = useState<SuppressionView[]>([]);
  // UI-569-02: the suppression list is an independent request, so it needs its
  // own lifecycle. Without it a failed/forbidden `GET …/audit/waivers/` looked
  // exactly like "no suppressions on file" (the empty key never rendered).
  const [waiversLoading, setWaiversLoading] = useState<boolean>(false);
  const [waiversError, setWaiversError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<Record<number, ActionState>>({});
  const [toast, setToast] = useState<string | null>(null);
  // UI-57: Adopt applies an automatic correction with no undo — interpose a
  // confirmation instead of firing the remediation call straight from the
  // row button.
  const [pendingAdopt, setPendingAdopt] = useState<AuditFinding | null>(null);
  // #569: the Waive action opens a dialog that requires a justification before
  // it can be confirmed — a suppression without a reason must not be possible.
  const [pendingWaive, setPendingWaive] = useState<AuditFinding | null>(null);
  const [waiveReason, setWaiveReason] = useState<string>("");
  const [waiveExpiresAt, setWaiveExpiresAt] = useState<string>("");
  const [waiveError, setWaiveError] = useState<string | null>(null);
  const [isWaiving, setIsWaiving] = useState<boolean>(false);
  // UI-569-03: a successful waive unmounts the row's Waive trigger, so the
  // dialog's focus trap cannot restore focus to it. This carries the index of
  // the row that should take focus instead.
  const [focusFindingIndex, setFocusFindingIndex] = useState<number | null>(null);

  // ---- Load artifacts once per workspace (needed for the document-scope picker) ----
  useEffect(() => {
    if (!activeWorkspace) {
      setArtifacts([]);
      return;
    }
    let cancelled = false;
    void artifactsApi
      .list(activeWorkspace.id)
      .then((resp) => {
        if (!cancelled) setArtifacts(resp.results);
      })
      .catch(() => {
        // Non-critical for project/global scope — document scope will simply
        // show an empty picker and the user can switch scope back.
      });
    return () => {
      cancelled = true;
    };
    // Re-run only when the workspace identity changes, not on every
    // activeWorkspace object re-render (mirrors MetricsDashboard's pattern).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id]);

  // Auto-pick the first artifact when the user switches to document scope
  // without one selected yet (mirrors BaselinesView's create-form behaviour).
  useEffect(() => {
    if (scope === "document" && !scopeArtifactId && artifacts.length > 0) {
      setScopeArtifactId(artifacts[0].id);
    }
  }, [scope, scopeArtifactId, artifacts]);

  // ---- Run the SE-Auditor ----
  // Always requests the first bounded window (#596) rather than the whole
  // (BLOCKER-first capped) result set — a fresh run, a scope change or a
  // refresh resets the list to page 1.
  const load = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (scope === "document" && !scopeArtifactId) return;

    setIsLoading(true);
    setLoadError(null);
    try {
      const report = await auditApi.run(activeWorkspace.id, {
        scope,
        scopeArtifactId: scope === "document" ? scopeArtifactId : undefined,
        limit: FINDINGS_PAGE_SIZE,
        offset: 0,
      });
      setTier(report.tier);
      setFindings(report.findings);
      setHasMore(report.truncated);
      setNextOffset(report.offset + report.findings.length);
      setTotalFindingsAvailable(report.total_findings_available);
      setTotalBlockersAvailable(report.total_blockers_available);
      setTotalWarningsAvailable(report.total_warnings_available);
      setTotalSuppressedAvailable(report.total_suppressed_available);
      setTotalSuppressedBlockersAvailable(report.total_suppressed_blockers_available);
      setActionState({});
    } catch (err) {
      setLoadError(
        resolveErrorMessage(err, t("audit.loadError", "Could not load audit findings."))
      );
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, scope, scopeArtifactId, t]);

  /**
   * #569: load every suppression (both lifecycles). Non-critical to the audit
   * run — a failure must not blank the findings list. It must not be
   * indistinguishable from "no suppressions on file" either (UI-569-02): the
   * suppression panel gets its own loading/error/empty states driven by these
   * flags instead of silently degrading to an empty panel.
   */
  const loadWaivers = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setWaiversLoading(true);
    setWaiversError(null);
    try {
      const resp = await auditApi.waivers(activeWorkspace.id, "all");
      setWaivers(resp?.waivers ?? []);
    } catch (err) {
      setWaiversError(
        resolveErrorMessage(
          err,
          t("audit.waivers.loadError", "Could not load suppressions.")
        )
      );
    } finally {
      setWaiversLoading(false);
    }
  }, [activeWorkspace, t]);

  useEffect(() => {
    void load();
    void loadWaivers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id, scope, scopeArtifactId]);

  /**
   * #596: append the next window of findings. The backend's `index` is a
   * finding's stable position in the *full* run (#622), so appending keeps
   * React keys, `data-testid`s and the Adopt correlation unique; the seen-set
   * filter is a safety net against a duplicate window (e.g. a double click
   * that slipped past the in-flight guard).
   */
  const loadMore = useCallback(async (): Promise<void> => {
    if (!activeWorkspace || isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    setLoadError(null);
    try {
      const report = await auditApi.run(activeWorkspace.id, {
        scope,
        scopeArtifactId: scope === "document" ? scopeArtifactId : undefined,
        limit: FINDINGS_PAGE_SIZE,
        offset: nextOffset,
      });
      setFindings((prev) => {
        const seen = new Set(prev.map((f) => f.index));
        return [...prev, ...report.findings.filter((f) => !seen.has(f.index))];
      });
      setHasMore(report.truncated);
      setNextOffset(report.offset + report.findings.length);
    } catch (err) {
      // The already-loaded findings stay readable (the error banner renders
      // above them) — a failed "Load more" must not discard the page the
      // user is working through.
      setLoadError(
        resolveErrorMessage(err, t("audit.loadError", "Could not load audit findings."))
      );
    } finally {
      setIsLoadingMore(false);
    }
  }, [
    activeWorkspace,
    scope,
    scopeArtifactId,
    isLoadingMore,
    hasMore,
    nextOffset,
    t,
  ]);

  // Auto-dismiss the success toast.
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  // UI-569-03: after a successful waive the finding flips to `suppressed` and
  // its Waive trigger unmounts — so the dialog's focus trap skips the restore
  // (`previouslyFocused.isConnected` is false) and keyboard focus falls to
  // `<body>`. Move it explicitly onto the still-mounted finding row
  // (`tabIndex={-1}`, so it stays out of the Tab cycle), which keeps the user's
  // place in the list after the decision.
  useEffect(() => {
    if (focusFindingIndex === null) return;
    const row = document.querySelector<HTMLElement>(
      `[data-testid="audit-finding-${focusFindingIndex}"]`
    );
    if (!row) return;
    row.focus();
    setFocusFindingIndex(null);
  }, [focusFindingIndex, findings]);

  // ---- Adopt workflow ----
  const handleAdopt = useCallback(
    async (finding: AuditFinding): Promise<void> => {
      if (!activeWorkspace) return;
      setActionState((prev) => ({ ...prev, [finding.index]: { status: "pending" } }));
      try {
        await auditApi.remediate(activeWorkspace.id, {
          rule_id: finding.rule_id,
          artifact_ids: finding.artifact_ids,
          scope,
          scope_artifact_id: scope === "document" ? scopeArtifactId : undefined,
        });
        setFindings((prev) => prev.filter((f) => f.index !== finding.index));
        setActionState((prev) => {
          const next = { ...prev };
          delete next[finding.index];
          return next;
        });
        setToast(t("audit.adoptSuccess", "Resolved — the correction was applied."));
      } catch (err) {
        if (err instanceof UnprocessableEntityError) {
          // Not automatically fixable (anymore) — flip this finding into the
          // manual "Modify" state in-place instead of leaving a dead button.
          setFindings((prev) =>
            prev.map((f) =>
              f.index === finding.index
                ? { ...f, remediation: { ...f.remediation, automatic: false, reason: err.message } }
                : f
            )
          );
          setActionState((prev) => ({
            ...prev,
            [finding.index]: { status: "error", message: err.message },
          }));
        } else {
          setActionState((prev) => ({
            ...prev,
            [finding.index]: {
              status: "error",
              message: resolveErrorMessage(err, t("audit.actionError")),
            },
          }));
        }
      }
    },
    [activeWorkspace, scope, scopeArtifactId, t]
  );

  // UI-57: Adopt has no undo (it PATCHes/creates trace links straight away) —
  // the row button opens the confirmation, the confirmation fires the actual
  // mutation. Mirrors UserManagement's request/confirm split.
  const requestAdopt = useCallback((finding: AuditFinding): void => {
    setPendingAdopt(finding);
  }, []);

  const confirmAdopt = useCallback((): void => {
    if (!pendingAdopt) return;
    const finding = pendingAdopt;
    setPendingAdopt(null);
    void handleAdopt(finding);
  }, [pendingAdopt, handleAdopt]);

  // ---- Modify workflow (GitHub #451) ----
  // A finding is cleared by correcting the artifact it points at, so "Modify"
  // is a navigation, not a mutation — there is no finding to PATCH.
  const targets = useFindingTargets(findings);

  const handleModify = useCallback(
    (target: FindingTarget): void => {
      navigate(target.route);
    },
    [navigate]
  );

  // ---- Waive workflow (#569) ----
  // The third action: record a justified suppression for a reported BLOCKER
  // finding. Unlike Adopt it removes nothing — the finding stays in the list,
  // marked as suppressed, so the decision stays visible.
  const waiveErrorMessage = useCallback(
    (err: unknown): string => {
      // The stable `error.code` decides the message. A rejected justification
      // must be reason-specific, and a waive failure must NEVER fall through
      // into the Adopt/Modify flip (that flip belongs to a 422 from
      // `remediate` alone — the waive paths never emit 422, spec E18).
      switch (waiverErrorCode(err)) {
        case "WAIVER_REASON_REJECTED":
          return t(
            "audit.waiveReasonRejected",
            "The justification does not satisfy the policy."
          );
        case "WAIVER_FINDING_NOT_BLOCKING":
          return t("audit.waiveNotBlocking", "This finding is not a blocker right now.");
        case "SUPPRESSION_EXPIRED":
          return t(
            "audit.waiveExpired",
            "An expired suppression already exists for this finding."
          );
        case "PERMISSION_DENIED":
          return t("audit.waiveForbidden", "You are not allowed to suppress findings.");
        default:
          // VALIDATION_ERROR (field-level feedback) and anything else: prefer
          // the server's concrete message over a generic one.
          return resolveErrorMessage(err, t("audit.actionError"));
      }
    },
    [t]
  );

  const requestWaive = useCallback((finding: AuditFinding): void => {
    setPendingWaive(finding);
    setWaiveReason("");
    setWaiveExpiresAt("");
    setWaiveError(null);
  }, []);

  const cancelWaive = useCallback((): void => {
    if (isWaiving) return;
    setPendingWaive(null);
    setWaiveError(null);
  }, [isWaiving]);

  const confirmWaive = useCallback(async (): Promise<void> => {
    if (!activeWorkspace || !pendingWaive) return;
    const finding = pendingWaive;
    const reason = waiveReason.trim();
    // "No silent suppression": a justification is mandatory in the UI too.
    if (!reason) {
      setWaiveError(t("audit.waiveReasonRequired", "Please provide a justification."));
      return;
    }
    setIsWaiving(true);
    setWaiveError(null);
    try {
      const body: WaiveRequest = {
        rule_id: finding.rule_id,
        artifact_ids: finding.artifact_ids,
        reason,
      };
      // C1: the engine scope of the clicked row must travel with the request
      // so the existence check runs over the same scope the finding was
      // reported in — a document-scoped finding is otherwise unreachable.
      if (finding.scope) body.scope = finding.scope;
      if (finding.scope === "document" && finding.scope_artifact_id) {
        body.scope_artifact_id = finding.scope_artifact_id;
      }
      if (waiveExpiresAt) {
        // <input type="datetime-local"> yields a *naive* local value; the
        // backend rejects naive timestamps, so normalise to UTC ISO-8601.
        body.expires_at = new Date(waiveExpiresAt).toISOString();
      }
      const view = await auditApi.waive(activeWorkspace.id, body);
      // Mark the finding in-place as suppressed — it is NOT removed, so the
      // suppression stays visible (Nachvollziehbarkeit statt Verstecken).
      setFindings((prev) =>
        prev.map((f) =>
          f.index === finding.index
            ? {
                ...f,
                suppressed: true,
                suppressed_until: view.expires_at,
                suppression_reason: view.reason,
                suppression_id: view.waiver_id,
              }
            : f
        )
      );
      setPendingWaive(null);
      setToast(t("audit.waiveSuccess", "Suppression saved."));
      // UI-569-03: the trigger that opened the dialog is about to unmount.
      setFocusFindingIndex(finding.index);
      void loadWaivers();
    } catch (err) {
      // Deliberately NOT `instanceof UnprocessableEntityError`: the waive
      // paths never emit 422, and routing a failure here into the Modify
      // flip would misreport a rejected reason as an Adopt conflict.
      setWaiveError(waiveErrorMessage(err));
    } finally {
      setIsWaiving(false);
    }
  }, [
    activeWorkspace,
    pendingWaive,
    waiveReason,
    waiveExpiresAt,
    t,
    waiveErrorMessage,
    loadWaivers,
  ]);

  // ---- Derived state ----
  // GitHub #952: whether the last run FAILED is a flag, not "is the message
  // non-empty". `resolveErrorMessage` guarantees a non-empty string, but the
  // banner/empty-state decision must not depend on that guarantee alone: a
  // failed run must never be able to render as the green "No findings" state.
  const loadFailed = loadError !== null;

  const filteredFindings = useMemo(() => {
    let list =
      severityFilter === "all"
        ? findings
        : findings.filter((f) => f.severity === severityFilter);
    // #569: the "show suppressed" filter (default on) hides suppressed rows
    // client-side only — the report keeps them marked, never silently.
    if (!showSuppressed) list = list.filter((f) => !f.suppressed);
    return list;
  }, [findings, severityFilter, showSuppressed]);

  // Counts are recomputed from the live findings list (not the initial
  // report.counts) so the badges stay accurate after a finding is resolved —
  // but only once every window has been loaded: while `hasMore` is true the
  // client-side `findings` array holds just the mounted pages, so counting it
  // directly would silently show "100" as if it were the true total (code
  // review M3, #596). While more findings exist, show the backend's real
  // pre-window totals instead; those are a snapshot from the last full
  // run_audit() call and do not shrink live as findings are Adopted, but that
  // is preferable to a badge that understates the real number of open
  // findings.
  //
  // #569: `blockers`/`warnings` stay descriptive of the returned findings
  // (M5) — a suppressed blocker still counts there. Suppression is counted
  // additively via `suppressed`/`suppressedBlockers`.
  const counts = useMemo(
    () =>
      hasMore
        ? {
            total: totalFindingsAvailable,
            blockers: totalBlockersAvailable,
            warnings: totalWarningsAvailable,
            suppressed: totalSuppressedAvailable,
            suppressedBlockers: totalSuppressedBlockersAvailable,
          }
        : {
            total: findings.length,
            blockers: findings.filter((f) => f.severity === "blocker").length,
            warnings: findings.filter((f) => f.severity === "warning").length,
            suppressed: findings.filter((f) => f.suppressed).length,
            suppressedBlockers: findings.filter(
              (f) => f.suppressed && f.severity === "blocker"
            ).length,
          },
    [
      findings,
      hasMore,
      totalFindingsAvailable,
      totalBlockersAvailable,
      totalWarningsAvailable,
      totalSuppressedAvailable,
      totalSuppressedBlockersAvailable,
    ]
  );

  const grouped = useMemo(() => {
    const groups = new Map<string, AuditFinding[]>();
    for (const f of filteredFindings) {
      const list = groups.get(f.rule_id) ?? [];
      list.push(f);
      groups.set(f.rule_id, list);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredFindings]);

  if (!activeWorkspace) {
    return (
      <div data-testid="audit-dashboard">
        <p className={styles.mutedText}>
          {t("audit.noWorkspace", "Select a workspace to run the SE-Auditor.")}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="audit-dashboard">
      <PageHeader
        title={t("audit.title", "SE-Auditor")}
        summary={t(
          "audit.pageSummary",
          "Automatisierte Regelprüfung für Requirements und Architektur, gruppiert nach Regel mit Blocker-/Warnungs-Einstufung.",
        )}
      />

      <div className={styles.toolbar}>
        <label className={styles.toolbarLabel}>
          {t("audit.scope.label", "Scope")}
          <select
            data-testid="audit-scope-select"
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as AuditScopeKind);
              setScopeArtifactId("");
            }}
            className={styles.select}
          >
            {SCOPES.map((s) => (
              <option key={s} value={s}>
                {t(`audit.scope.${s}`, s)}
              </option>
            ))}
          </select>
        </label>

        {scope === "document" && (
          <label className={styles.toolbarLabel}>
            {t("audit.scopeArtifact.label", "Document")}
            <select
              data-testid="audit-scope-artifact-select"
              value={scopeArtifactId}
              onChange={(e) => setScopeArtifactId(e.target.value)}
              disabled={artifacts.length === 0}
              className={styles.select}
            >
              {artifacts.length === 0 ? (
                <option value="">{t("audit.scopeArtifact.empty", "No artifacts available.")}</option>
              ) : (
                artifacts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {artifactLabel(a)}
                  </option>
                ))
              )}
            </select>
          </label>
        )}

        <label className={styles.toolbarLabel}>
          {t("audit.severityFilter.label", "Severity")}
          <select
            data-testid="audit-severity-filter"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as "all" | "blocker" | "warning")}
            className={styles.select}
          >
            <option value="all">{t("audit.severityFilter.all", "All")}</option>
            <option value="blocker">{t("audit.severityFilter.blocker", "Blockers")}</option>
            <option value="warning">{t("audit.severityFilter.warning", "Warnings")}</option>
          </select>
        </label>

        {/* #569: default ON — nothing is hidden by default (O3). Unchecking
            filters suppressed findings out client-side. */}
        <label className={styles.toolbarLabel}>
          <input
            type="checkbox"
            data-testid="audit-show-suppressed"
            checked={showSuppressed}
            onChange={(e) => setShowSuppressed(e.target.checked)}
          />
          {t("audit.showSuppressed", "Show suppressed")}
        </label>

        <button
          type="button"
          data-testid="audit-refresh-btn"
          onClick={() => void load()}
          disabled={isLoading}
          className={`${styles.refreshButton} ${
            isLoading ? styles.refreshButtonDisabled : styles.refreshButtonEnabled
          }`}
        >
          {isLoading ? t("audit.refreshing", "Refreshing...") : t("audit.refresh", "Refresh")}
        </button>
      </div>

      {/* Counts + tier. Issue #675: rendered through the shared <Badge> with
          its canonical variant semantics (blockers = danger, warnings =
          warning, totals/tier = neutral) instead of a local colour map. */}
      <div className={styles.countsRow}>
        <Badge variant="neutral" testId="audit-count-total">
          {t("audit.counts.total", "Findings")}: {counts.total}
        </Badge>
        <Badge variant="danger" testId="audit-count-blockers">
          {t("audit.counts.blockers", "Blockers")}: {counts.blockers}
        </Badge>
        <Badge variant="warning" testId="audit-count-warnings">
          {t("audit.counts.warnings", "Warnings")}: {counts.warnings}
        </Badge>
        {/* #569: suppression is counted additively — `counts.blockers` above
            stays the descriptive blocker number (M5), so a suppressed blocker
            shows up here instead of being subtracted there. */}
        <Badge variant="neutral" testId="audit-count-suppressed">
          {t("audit.counts.suppressed", "Suppressed")}: {counts.suppressed}
        </Badge>
        {counts.suppressedBlockers > 0 && (
          <Badge variant="neutral" testId="audit-count-suppressed-blockers">
            {t("audit.counts.suppressedBlockers", "Suppressed blockers")}:{" "}
            {counts.suppressedBlockers}
          </Badge>
        )}
        {tier && (
          <Badge variant="neutral" testId="audit-tier">
            {t("audit.tier", "Rigor tier")}: {tier}
          </Badge>
        )}
      </div>

      {/* #569: every suppression, both lifecycles. The report only marks
          *active* ones, so an expired suppression would otherwise be
          invisible; here it is listed with a distinct "expired" badge, which
          is what keeps an expired waiver visually distinguishable from an
          active one.
          UI-569-02: this is an independent request with its own lifecycle —
          loading, error and empty are distinct, testable states, so a failed
          or forbidden read no longer masquerades as "no suppressions". */}
      <section data-testid="audit-waivers" className={styles.waiversPanel}>
        <h2 className={styles.waiversHeading}>
          {t("audit.waivers.title", "Suppressions")}
        </h2>
        {waiversLoading ? (
          <p data-testid="audit-waivers-loading" className={styles.waiversState}>
            {t("audit.waivers.loading", "Loading suppressions...")}
          </p>
        ) : waiversError ? (
          <p role="alert" data-testid="audit-waivers-error" className={styles.waiversError}>
            {waiversError}
          </p>
        ) : waivers.length === 0 ? (
          <p data-testid="audit-waivers-empty" className={styles.waiversState}>
            {t("audit.waivers.empty", "No suppressions on file.")}
          </p>
        ) : (
          <ul className={styles.waiversList}>
            {waivers.map((w) => (
              <li
                key={w.waiver_id}
                data-testid={`audit-waiver-${w.waiver_id}`}
                className={styles.waiverRow}
              >
                <Badge
                  variant={w.state === "active" ? "neutral" : "warning"}
                  testId={`audit-waiver-state-${w.waiver_id}`}
                >
                  {t(`audit.waivers.state.${w.state}`, w.state)}
                </Badge>
                <span className={styles.waiverRule}>{w.rule_id}</span>
                <span
                  data-testid={`audit-waiver-reason-${w.waiver_id}`}
                  className={styles.waiverReason}
                >
                  {w.reason}
                </span>
                {w.expires_at && (
                  <span className={styles.waiverMeta}>
                    {t("audit.waivers.until", "Valid until")}: {formatExpiry(w.expires_at)}
                  </span>
                )}
                {w.granted_by && (
                  <span className={styles.waiverMeta}>
                    {t("audit.waivers.grantedBy", "Granted by")}: {w.granted_by}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* #596: more findings exist than the page currently mounts — say so
          explicitly (with the real totals) instead of showing a partial list
          that looks complete, and offer the next window below the list. */}
      {hasMore && (
        <div
          role="status"
          data-testid="audit-truncated-banner"
          className={styles.truncatedBanner}
        >
          {t(
            "audit.truncated",
            "Showing {{shown}} of {{total}} findings — use “Load more” to mount the rest.",
            { shown: findings.length, total: totalFindingsAvailable },
          )}
        </div>
      )}

      {/* GitHub #451: "Adopt" vs "Modify" is not a per-rule quirk (TRACE-P5
          showing "Adopt" while everything else showed "Modify" read like an
          inconsistency) — it is the two outcomes of the backend's remediation
          analysis. Stated once, here, instead of being folklore. */}
      {findings.length > 0 && (
        <p data-testid="audit-action-legend" className={styles.legend}>
          {t(
            "audit.actionLegend",
            "Adopt applies the correction the auditor derived automatically. Modify opens the affected artifact so you can correct it yourself — findings are recomputed from the trace graph, so they disappear once the artifact is fixed.",
          )}
        </p>
      )}

      {toast && (
        <div role="status" data-testid="audit-toast" className={styles.toast}>
          {toast}
        </div>
      )}

      {loadFailed && (
        <div role="alert" data-testid="audit-load-error" className={styles.errorBanner}>
          {loadError}
        </div>
      )}

      {isLoading && findings.length === 0 && !loadFailed ? (
        <p data-testid="audit-loading">{t("audit.loading", "Loading...")}</p>
      ) : !loadFailed && grouped.length === 0 ? (
        <p data-testid="audit-empty" className={styles.mutedText}>
          {t("audit.empty", "No findings — the trace graph is consistent for this scope.")}
        </p>
      ) : (
        <div className={styles.groupsColumn}>
          {grouped.map(([ruleId, groupFindings]) => (
            <FindingGroup
              key={ruleId}
              ruleId={ruleId}
              findings={groupFindings}
              actionState={actionState}
              targets={targets}
              onAdopt={requestAdopt}
              onModify={handleModify}
              onWaive={requestWaive}
            />
          ))}
        </div>
      )}

      {/* #596: next window of findings. Only rendered while more exist; each
          click mounts one further bounded page instead of the whole run.
          Deliberately not gated on `loadFailed`: a failed window must stay
          retryable (Refresh would reset to page 1 and discard the loaded
          pages). */}
      {hasMore && (
        <div className={styles.loadMoreRow}>
          <button
            type="button"
            data-testid="audit-load-more-btn"
            className="btn-secondary"
            onClick={() => void loadMore()}
            disabled={isLoadingMore}
          >
            {isLoadingMore
              ? t("audit.loadingMore", "Loading more...")
              : t("audit.loadMore", "Load more findings")}
          </button>
        </div>
      )}

      {pendingAdopt && (
        <ConfirmDialog
          title={t("audit.adoptConfirmTitle", "Apply correction?")}
          message={t(
            "audit.adoptConfirmMessage",
            "This applies the automatic correction for {{ruleId}} right away. There is no undo.",
            { ruleId: pendingAdopt.rule_id },
          )}
          confirmLabel={t("audit.adopt", "Adopt")}
          onConfirm={confirmAdopt}
          onCancel={() => setPendingAdopt(null)}
          testId="audit-adopt-confirm"
        />
      )}

      {/* #569: the Waive dialog. A justification is mandatory (the confirm
          button stays disabled until one is typed) — a suppression without a
          reason must not be reachable through the UI. */}
      {pendingWaive && (
        <Dialog
          title={t("audit.waiveTitle", "Waive finding")}
          onClose={cancelWaive}
          closeOnBackdropClick={!isWaiving}
          testId="audit-waive-dialog"
          footer={
            <>
              <button
                type="button"
                className="btn-secondary"
                data-testid="audit-waive-cancel"
                onClick={cancelWaive}
                disabled={isWaiving}
              >
                {t("audit.waiveCancel", "Cancel")}
              </button>
              <button
                type="button"
                className="btn-primary"
                data-testid="audit-waive-confirm"
                onClick={() => void confirmWaive()}
                disabled={isWaiving || waiveReason.trim() === ""}
              >
                {isWaiving
                  ? t("audit.waiving", "Waiving...")
                  : t("audit.waiveConfirm", "Waive")}
              </button>
            </>
          }
        >
          <div className={styles.waiveField}>
            <label className={styles.waiveLabel} htmlFor="audit-waive-reason-input">
              {t("audit.waiveReasonLabel", "Justification (required)")}
            </label>
            <textarea
              id="audit-waive-reason-input"
              data-testid="audit-waive-reason"
              value={waiveReason}
              onChange={(e) => setWaiveReason(e.target.value)}
              placeholder={t(
                "audit.waiveReasonPlaceholder",
                "Why is this blocker finding an accepted deviation?",
              )}
              rows={4}
              className={styles.waiveTextarea}
              disabled={isWaiving}
            />
          </div>
          <div className={styles.waiveField}>
            <label className={styles.waiveLabel} htmlFor="audit-waive-expires-input">
              {t("audit.waiveExpiresLabel", "Expiry date (optional)")}
            </label>
            <input
              id="audit-waive-expires-input"
              type="datetime-local"
              data-testid="audit-waive-expires"
              value={waiveExpiresAt}
              onChange={(e) => setWaiveExpiresAt(e.target.value)}
              className={styles.waiveInput}
              disabled={isWaiving}
            />
            <span className={styles.waiveHint}>
              {t(
                "audit.waiveExpiresHint",
                "Leave empty for unbounded. An already-past timestamp is rejected.",
              )}
            </span>
          </div>
          {waiveError && (
            <p role="alert" data-testid="audit-waive-error" className={styles.waiveError}>
              {waiveError}
            </p>
          )}
        </Dialog>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding group (one rule id)
// ---------------------------------------------------------------------------

interface FindingGroupProps {
  ruleId: string;
  findings: AuditFinding[];
  actionState: Record<number, ActionState>;
  targets: FindingTargetMap;
  onAdopt: (finding: AuditFinding) => void;
  onModify: (target: FindingTarget) => void;
  onWaive: (finding: AuditFinding) => void;
}

function FindingGroup({
  ruleId,
  findings,
  actionState,
  targets,
  onAdopt,
  onModify,
  onWaive,
}: FindingGroupProps): JSX.Element {
  const { t } = useTranslation();
  const blockers = findings.filter((f) => f.severity === "blocker").length;
  const warnings = findings.filter((f) => f.severity === "warning").length;

  return (
    <section
      data-testid={`audit-group-${ruleId}`}
      className={styles.groupSection}
    >
      <header className={styles.groupHeader}>
        <span className={styles.groupRuleId}>{ruleId}</span>
        <div className={styles.groupBadges}>
          {blockers > 0 && (
            <Badge variant="danger">
              {t("audit.counts.blockers", "Blockers")}: {blockers}
            </Badge>
          )}
          {warnings > 0 && (
            <Badge variant="warning">
              {t("audit.counts.warnings", "Warnings")}: {warnings}
            </Badge>
          )}
        </div>
      </header>

      <ul className={styles.findingsList}>
        {findings.map((finding) => (
          <FindingRow
            key={finding.index}
            finding={finding}
            action={actionState[finding.index] ?? { status: "idle" }}
            target={primaryTarget(finding, targets)}
            onAdopt={onAdopt}
            onModify={onModify}
            onWaive={onWaive}
          />
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Finding row
// ---------------------------------------------------------------------------

interface FindingRowProps {
  finding: AuditFinding;
  action: ActionState;
  /** Editor target for the manual correction; `null` while unresolved/unresolvable. */
  target: FindingTarget | null;
  onAdopt: (finding: AuditFinding) => void;
  onModify: (target: FindingTarget) => void;
  onWaive: (finding: AuditFinding) => void;
}

function FindingRow({
  finding,
  action,
  target,
  onAdopt,
  onModify,
  onWaive,
}: FindingRowProps): JSX.Element {
  const { t } = useTranslation();
  const isPending = action.status === "pending";
  const isSuppressed = finding.suppressed;

  return (
    <li
      data-testid={`audit-finding-${finding.index}`}
      // UI-569-03: programmatic focus target after a successful waive (the
      // trigger unmounts, so the dialog's focus trap cannot restore it).
      // `-1` keeps the row out of the Tab cycle (getFocusableElements skips it).
      tabIndex={-1}
      className={styles.findingRow}
    >
      <div className={styles.findingHeader}>
        <Badge
          variant={finding.severity === "blocker" ? "danger" : "warning"}
          testId={`audit-finding-severity-${finding.index}`}
        >
          {t(`audit.severity.${finding.severity}`, finding.severity)}
        </Badge>
        <span className={styles.findingMessage}>{finding.message}</span>
      </div>

      {finding.artifact_ids.length > 0 && (
        <div
          data-testid={`audit-finding-artifacts-${finding.index}`}
          className={styles.findingArtifacts}
        >
          <span className={styles.findingArtifactsLabel}>
            {t("audit.artifacts", "Affected artifacts")}:
          </span>
          {finding.artifact_ids.map((id) => (
            <Badge
              key={id}
              variant="neutral"
              testId={`audit-finding-artifact-${finding.index}-${id}`}
              title={id}
              className={styles.artifactBadge}
            >
              {id.slice(0, 8)}…
            </Badge>
          ))}
        </div>
      )}

      {/* #569: a suppressed finding is marked, never hidden — the badge shows
          who decided what, with the mandatory justification and (when set)
          the expiry, so the suppression stays auditable in the UI. */}
      {isSuppressed && (
        <div
          data-testid={`audit-suppressed-badge-${finding.index}`}
          className={styles.suppressedBadge}
        >
          <Badge variant="neutral">{t("audit.suppressedBadge", "Suppressed")}</Badge>
          {finding.suppression_reason && (
            <span
              data-testid={`audit-suppression-reason-${finding.index}`}
              className={styles.suppressionText}
            >
              {t("audit.suppressionReasonPrefix", "Reason")}: {finding.suppression_reason}
            </span>
          )}
          {finding.suppressed_until && (
            <span className={styles.suppressionText}>
              {t("audit.suppressedUntilPrefix", "Valid until")}:{" "}
              {formatExpiry(finding.suppressed_until)}
            </span>
          )}
        </div>
      )}

      <div className={styles.findingHeader}>
        {finding.remediation.automatic ? (
          <button
            type="button"
            data-testid={`audit-adopt-${finding.index}`}
            onClick={() => onAdopt(finding)}
            disabled={isPending || isSuppressed}
            title={finding.remediation.reason}
            className={`${styles.adoptButton} ${
              isPending || isSuppressed
                ? styles.adoptButtonDisabled
                : styles.adoptButtonEnabled
            }`}
          >
            {isPending ? t("audit.adopting", "Adopting...") : t("audit.adopt", "Adopt")}
          </button>
        ) : (
          <>
            {/* GitHub #451: an enabled Modify action that navigates to the
                artifact the finding is about — the only place the correction
                can actually be made, since findings are derived, not stored.
                Rendered only when that artifact resolves to an editor route;
                otherwise no control at all, because a button that cannot go
                anywhere is exactly the dead affordance this issue is about. */}
            {target && (
              <button
                type="button"
                data-testid={`audit-modify-${finding.index}`}
                onClick={() => onModify(target)}
                disabled={isSuppressed}
                title={t(
                  "audit.modifyHint",
                  "Open the affected artifact to correct it manually.",
                )}
                className={styles.modifyButton}
              >
                {t("audit.modify", "Modify")}
              </button>
            )}
            {/* The reason is shown as visible text, not only as a hover
                `title` — a hover-only tooltip is not discoverable via
                keyboard/touch/screen reader, and every finding without a
                registered automatic remediation lands here, so it is the
                common case, not an edge case (GitHub #451). */}
            <span
              data-testid={`audit-modify-reason-${finding.index}`}
              className={styles.modifyReason}
            >
              {t("audit.modifyReasonPrefix", "Not auto-fixable")}: {finding.remediation.reason}
              {!target &&
                ` ${t(
                  "audit.modifyNoTarget",
                  "This finding references no artifact that can be opened — correct it via the affected artifacts listed above.",
                )}`}
            </span>
          </>
        )}
        {/* #569: the third action. Visible for every non-suppressed finding;
            it opens the justification dialog. A suppressed finding gets no
            Waive button (it already carries a suppression). */}
        {!isSuppressed && (
          <button
            type="button"
            data-testid={`audit-waive-${finding.index}`}
            onClick={() => onWaive(finding)}
            title={t("audit.waiveTitle", "Waive finding")}
            className={styles.waiveButton}
          >
            {t("audit.waive", "Waive")}
          </button>
        )}
        {action.status === "error" && (
          <span data-testid={`audit-finding-error-${finding.index}`} role="alert" className={styles.findingActionError}>
            {action.message}
          </span>
        )}
      </div>
    </li>
  );
}
