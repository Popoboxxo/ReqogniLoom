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
 * grouping-by-rule and the Adopt/Modify actions are unchanged.
 *
 * Counts are ground truth (#1382/#1383)
 * -------------------------------------
 * `report.counts` describes the FULL run; `report.page_counts` describes only
 * the window just returned. The badges are therefore fed from the server, not
 * from `findings.length` — deriving them from the mounted rows made a partial
 * window look like the run total (#1382). The window size is shown as
 * "{{shown}} of {{total}}" (page_counts.total of counts.total), and
 * "Load more" advances with the server's `report.next_offset` cursor.
 */

import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  AuditCounts,
  AuditFinding,
  AuditRuleInfo,
  AuditScopeKind,
} from "../../api/audit";
import { Badge } from "../shared/Badge";
import { PageHeader } from "../shared/PageHeader";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { Dialog } from "../shared/Dialog";
import { primaryTarget } from "./use-finding-targets";
import { findingIdentity, useAuditRun } from "./use-audit-run";
import type { ActionState, ActionStateMap } from "./use-audit-run";
import { useAuditFilters } from "./use-audit-filters";
import {
  useAuditRules,
  useAuditWaivers,
  useScopeArtifacts,
} from "./use-audit-context";
import type { FindingTarget, FindingTargetMap } from "./use-finding-targets";
import {
  ARTIFACT_TYPE_OPTIONS,
  SCOPES,
  artifactLabel,
  buildRuleOptions,
  computeCounts,
  filterFindings,
  formatExpiry,
  groupFindingsByRule,
} from "./audit-dashboard.logic";
import { useAuditActions } from "./use-audit-actions";
import { useAuditScope } from "./use-audit-scope";
import styles from "./audit-dashboard.module.css";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AuditDashboard(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();

  // ---- Data context (#598 S2) ----
  // Artifacts back the document-scope picker; the rule catalogue backs the
  // rule-id popover (#1262); the suppression list is its own request (#569).
  const artifacts = useScopeArtifacts(activeWorkspace?.id);
  const ruleInfo = useAuditRules();
  const { waivers, waiversLoading, waiversError, loadWaivers } = useAuditWaivers(
    activeWorkspace?.id,
    t
  );

  // Scope selection + document-scope auto-pick (own module, S3.2 WP-5).
  const { scope, setScope, scopeArtifactId, setScopeArtifactId } = useAuditScope({
    artifacts,
  });

  // #1262/#569: severity, rule, artifact-type and suppressed filters
  // (own module, #598 S2).
  const {
    severityFilter,
    setSeverityFilter,
    ruleFilter,
    setRuleFilter,
    artifactTypeFilter,
    setArtifactTypeFilter,
    showSuppressed,
    setShowSuppressed,
  } = useAuditFilters();

  // ---- Run state (#598 S2) ----
  // The hook owns one run: the bounded first window and "Load more" cursor
  // (#596/#1383), the two count sets (#1382/#1383) and the local corrections
  // after the snapshot. Adopt/Waive below mutate it through the setters.
  const {
    tier,
    findings,
    setFindings,
    isLoading,
    loadError,
    hasMore,
    setNextOffset,
    isLoadingMore,
    reportCounts,
    pageCounts,
    loadedWindows,
    adoptedSinceRun,
    setAdoptedSinceRun,
    waivedSinceRun,
    setWaivedSinceRun,
    actionState,
    setActionState,
    load,
    loadMore,
  } = useAuditRun({
    workspaceId: activeWorkspace?.id,
    scope,
    scopeArtifactId,
    artifactTypeFilter,
    t,
  });

  // ---- Finding actions (#569/UI-57/#451, S3.2 WP-5) ----
  // The action module owns the Adopt/Modify/Waive decisions, their dialogs,
  // the success toast and the post-waive focus hand-off. It mutates the run
  // through the setters above; everything it renders stays here.
  const {
    toast,
    targets,
    pendingAdopt,
    requestAdopt,
    cancelAdopt,
    confirmAdopt,
    handleModify,
    pendingWaive,
    waiveReason,
    setWaiveReason,
    waiveExpiresAt,
    setWaiveExpiresAt,
    waiveError,
    isWaiving,
    requestWaive,
    cancelWaive,
    confirmWaive,
    validation,
  } = useAuditActions({
    workspaceId: activeWorkspace?.id,
    scope,
    scopeArtifactId,
    findings,
    loadWaivers,
    setFindings,
    setActionState,
    setAdoptedSinceRun,
    setWaivedSinceRun,
    setNextOffset,
  });
  // Keep the dialog markup (and its testids/ARIA) byte-identical to before the
  // extraction: only the source of these helpers moved, not the JSX.
  const {
    errors: requiredErrors,
    clearError,
    fieldProps,
    errorId,
  } = validation;

  // ---- Derived state ----
  // GitHub #952: whether the last run FAILED is a flag, not "is the message
  // non-empty". `resolveErrorMessage` guarantees a non-empty string, but the
  // banner/empty-state decision must not depend on that guarantee alone: a
  // failed run must never be able to render as the green "No findings" state.
  const loadFailed = loadError !== null;

  const filteredFindings = useMemo(
    () => filterFindings(findings, severityFilter, ruleFilter, showSuppressed),
    [findings, severityFilter, ruleFilter, showSuppressed]
  );

  /** #1262: per-rule counters for the rule filter, ordered by rule id. */
  const ruleOptions = useMemo(() => buildRuleOptions(findings), [findings]);

  // ---- Counts (#1382/#1383) ----
  // The badges read the report's `counts`, which is the ground truth over the
  // FULL run. They are never derived from `findings.length`: that list holds
  // only the mounted windows, so counting it made a 100-finding window look
  // like the run total (#1382). Client-side filters (severity/rule/suppressed)
  // do not change these numbers either — they describe the run, not the view.
  //
  // Shrink-on-resolve trade-off: the server counts are a snapshot taken during
  // the last run, so an Adopt or a Waive performed afterwards cannot change
  // them. Rather than dropping the live feedback entirely, the findings acted
  // on since that snapshot are applied on top of it (`adoptedSinceRun` /
  // `waivedSinceRun`) — a bounded, explicit correction, not a recount of the
  // DOM. Both lists are cleared as soon as a fresh snapshot is adopted (`load`
  // and `loadMore`), because that snapshot already reflects the actions; the
  // deltas therefore always mean "since the last snapshot", never "since page
  // load". The mounted rows and the window/"rows loaded" display follow
  // `findings` on their own.
  //
  // #1150/#1382: `counts.blockers` is effective (waiver-aware), so a local
  // waive must decrement it exactly like an Adopt does. Suppression stays
  // counted additively in `suppressed`/`suppressed_blockers` — the waived
  // finding is not hidden, it is visible there.
  const counts = useMemo<AuditCounts>(
    () => computeCounts(reportCounts, adoptedSinceRun, waivedSinceRun),
    [reportCounts, adoptedSinceRun, waivedSinceRun]
  );

  const grouped = useMemo(
    () => groupFindingsByRule(filteredFindings),
    [filteredFindings]
  );

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

        {/* #1262: rule filter with per-rule counters (client-side). The
            counters count the mounted rows only, not the full run, so the
            control says so (#1382 follow-up) instead of implying a run total. */}
        <label className={styles.toolbarLabel}>
          {t("audit.ruleFilter.label")}
          <select
            data-testid="audit-rule-filter"
            title={t("audit.loadedOnlyCountsHint")}
            value={ruleFilter}
            onChange={(e) => setRuleFilter(e.target.value)}
            className={styles.select}
          >
            <option value="all">{t("audit.ruleFilter.all")}</option>
            {ruleOptions.map(([id, count]) => (
              <option key={id} value={id}>
                {id} ({count})
              </option>
            ))}
          </select>
        </label>

        {/* #1262: artifact-type filter — server-side (a finding's artifact
            types cannot be derived client-side from its ids alone). */}
        <label className={styles.toolbarLabel}>
          {t("audit.artifactTypeFilter.label")}
          <select
            data-testid="audit-artifact-type-filter"
            value={artifactTypeFilter}
            onChange={(e) => setArtifactTypeFilter(e.target.value)}
            className={styles.select}
          >
            <option value="all">{t("audit.artifactTypeFilter.all")}</option>
            {ARTIFACT_TYPE_OPTIONS.map((type) => (
              <option key={type} value={type}>
                {t(`audit.artifactTypeFilter.${type}`)}
              </option>
            ))}
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
          className="btn-primary"
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
        {/* #1150/#569: `counts.blockers` above is the *effective* count (a
            waiver already excludes the blocker there), and suppression is
            counted additively here so the waived finding stays visible rather
            than silently disappearing from the numbers. */}
        <Badge variant="neutral" testId="audit-count-suppressed">
          {t("audit.counts.suppressed", "Suppressed")}: {counts.suppressed}
        </Badge>
        {counts.suppressed_blockers > 0 && (
          <Badge variant="neutral" testId="audit-count-suppressed-blockers">
            {t("audit.counts.suppressedBlockers", "Suppressed blockers")}:{" "}
            {counts.suppressed_blockers}
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
          explicitly instead of showing a partial list that looks complete, and
          offer the next window below the list.
          #1382/#1383: the total (Y) is the full-run ground truth
          (`counts.total`), the window size (X) is `page_counts.total` for the
          window just returned — NOT the mounted row count, which is only
          named separately once several windows are on screen so "window" and
          "rows loaded" cannot be confused.
          #1382 residual: `shown` is the last snapshot's window size, so after
          a local Adopt/Waive it is not decremented the way `counts.total` is —
          the two can temporarily differ by the local deltas instead of summing
          to a partition. Kept deliberately: the adopted row may have come from
          an earlier window, so subtracting it here would misstate the last
          window just as often as it corrects it. Refresh re-snapshots both. */}
      {hasMore && (
        <div
          role="status"
          data-testid="audit-truncated-banner"
          className={styles.truncatedBanner}
        >
          {loadedWindows > 1
            ? t("audit.truncatedWithMounted", {
                shown: pageCounts?.total ?? 0,
                mounted: findings.length,
                total: counts.total,
              })
            : t(
                "audit.truncated",
                "Showing {{shown}} of {{total}} findings — use “Load more” to mount the rest.",
                { shown: pageCounts?.total ?? 0, total: counts.total },
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

      {/* #1382/NF-B: "consistent" is a statement about the RUN, so it may only
          be shown when the run itself is empty (`counts.total === 0`) AND no
          server-side artifact-type filter is narrowing it. `counts.total` is
          post-filter ground truth: with a filter selected a zero result says
          "nothing of that type", not "the trace graph is consistent". Deriving
          the empty state from the mounted, filtered rows made a filter that
          hides every loaded row read as a clean trace graph while the ground-
          truth badges reported thousands of findings. A filter that hides all
          rows gets a neutral message instead. */}
      {isLoading && findings.length === 0 && !loadFailed ? (
        <p data-testid="audit-loading">{t("audit.loading", "Loading...")}</p>
      ) : !loadFailed && grouped.length === 0 ? (
        artifactTypeFilter === "all" && counts.total === 0 ? (
          <p data-testid="audit-empty" className={styles.mutedText}>
            {t("audit.empty", "No findings — the trace graph is consistent for this scope.")}
          </p>
        ) : (
          <p data-testid="audit-no-filter-match" className={styles.mutedText}>
            {t("audit.noFilterMatch")}
          </p>
        )
      ) : (
        <div className={styles.groupsColumn}>
          {grouped.map(([ruleId, groupFindings]) => (
            <FindingGroup
              key={ruleId}
              ruleId={ruleId}
              findings={groupFindings}
              actionState={actionState}
              targets={targets}
              ruleInfo={ruleInfo[ruleId]}
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
          onCancel={cancelAdopt}
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
                disabled={isWaiving}
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
              onChange={(e) => {
                setWaiveReason(e.target.value);
                clearError("waiveReason");
              }}
              placeholder={t(
                "audit.waiveReasonPlaceholder",
                "Why is this blocker finding an accepted deviation?",
              )}
              rows={4}
              className={styles.waiveTextarea}
              disabled={isWaiving}
              {...fieldProps("waiveReason")}
            />
            {requiredErrors.waiveReason ? (
              <p
                id={errorId("waiveReason")}
                role="alert"
                data-testid="audit-waive-reason-error"
                className={styles.waiveError}
              >
                {requiredErrors.waiveReason}
              </p>
            ) : null}
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
// Rule info popover (#1262)
// ---------------------------------------------------------------------------

interface RuleInfoPopoverProps {
  ruleId: string;
  info?: AuditRuleInfo;
}

/**
 * #1262: the rule id is a button that toggles a popover with the rule's
 * catalogue metadata (title, description, severity, standard reference and the
 * "how to fix" hint). Falls back to the bare rule id while the catalogue is
 * still loading or unavailable.
 */
function RuleInfoPopover({ ruleId, info }: RuleInfoPopoverProps): JSX.Element {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const popoverId = useId();

  return (
    <span className={styles.ruleInfoWrap}>
      <button
        type="button"
        data-testid={`audit-rule-info-${ruleId}`}
        className={styles.groupRuleId}
        aria-expanded={open}
        // M-2 (SC 4.1.2): the popover is non-modal, read-only metadata — it
        // contains no interactive content, so `role="tooltip"` with a
        // `aria-describedby` relationship is the correct semantics (not a
        // dialog). Only reference it while it is actually mounted.
        aria-describedby={open ? popoverId : undefined}
        title={info?.title ?? ruleId}
        onKeyDown={(event) => {
          // Escape dismisses the popover while its trigger has focus.
          if (event.key === "Escape" && open) {
            event.stopPropagation();
            setOpen(false);
          }
        }}
        onClick={() => setOpen((v) => !v)}
      >
        {ruleId}
      </button>
      {open && (
        <div
          id={popoverId}
          role="tooltip"
          data-testid={`audit-rule-popover-${ruleId}`}
          className={styles.rulePopover}
        >
          <p className={styles.rulePopoverTitle}>{info?.title ?? ruleId}</p>
          {info ? (
            <>
              <p>{info.description}</p>
              <p>
                {t("audit.rulePopover.severity")}: {info.severity}
              </p>
              {info.standard_ref && (
                <p>
                  {t("audit.rulePopover.standard")}:{" "}
                  {info.standard_ref}
                </p>
              )}
              {info.remediation_hint && (
                <p>
                  {t("audit.rulePopover.remediation")}:{" "}
                  {info.remediation_hint}
                </p>
              )}
            </>
          ) : (
            <p>{t("audit.rulePopover.loading")}</p>
          )}
        </div>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Finding group (one rule id)
// ---------------------------------------------------------------------------

interface FindingGroupProps {
  ruleId: string;
  findings: AuditFinding[];
  actionState: ActionStateMap;
  targets: FindingTargetMap;
  /** #1262: catalogue metadata for the rule-id popover (may be undefined). */
  ruleInfo?: AuditRuleInfo;
  onAdopt: (finding: AuditFinding) => void;
  onModify: (target: FindingTarget) => void;
  onWaive: (finding: AuditFinding) => void;
}

function FindingGroup({
  ruleId,
  findings,
  actionState,
  targets,
  ruleInfo,
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
        <RuleInfoPopover ruleId={ruleId} info={ruleInfo} />
        <div className={styles.groupBadges} title={t("audit.loadedOnlyCountsHint")}>
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
            key={findingIdentity(finding)}
            finding={finding}
            action={actionState[findingIdentity(finding)] ?? { status: "idle" }}
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
            className="btn-primary"
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
                className={`btn-secondary ${styles.modifyButton}`}
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
            className="btn-secondary"
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
