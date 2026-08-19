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
 * Per-finding actions (GitHub #451)
 * ---------------------------------
 * Every finding gets exactly one action, and which one it is follows the
 * backend's remediation analysis (`traceability/audit/remediation.py`), not the
 * rule id:
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
 */

import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { auditApi } from "../../api/audit";
import type { AuditFinding, AuditScopeKind } from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import { extractErrorMessage } from "../../api/client";
import { UnprocessableEntityError } from "../../api/errors";
import type { Artifact } from "../../types";
import { PageHeader } from "../shared/PageHeader";
import { primaryTarget, useFindingTargets } from "./use-finding-targets";
import type { FindingTarget, FindingTargetMap } from "./use-finding-targets";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SCOPES: AuditScopeKind[] = ["project", "document", "global"];

type ActionStatus = "idle" | "pending" | "error";

interface ActionState {
  status: ActionStatus;
  message?: string;
}

/** Extract a human-readable message from any error a fetch call can throw. */
function resolveErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return extractErrorMessage(err);
}

/** Defensive label for an /artifacts/ row — the payload exposes no title/name
 * field today (same caveat as BaselinesView's document-scope picker), so we
 * read them optimistically and fall back to a truncated id. */
function artifactLabel(a: Artifact): string {
  const named = a as Artifact & { title?: string; name?: string };
  const label = named.title ?? named.name ?? `${a.id.slice(0, 8)}…`;
  return `${a.artifact_type} — ${label}`;
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
  // BUG-15: the backend caps very large result sets (AuditService.
  // MAX_REPORT_FINDINGS) instead of paginating — grouping findings by rule
  // id and computing live blocker/warning counts needs the whole capped set
  // at once, so a page-based UI would fragment rule groups. Surface the cap
  // as a visible banner instead of silently hiding findings.
  const [truncated, setTruncated] = useState<boolean>(false);
  const [totalFindingsAvailable, setTotalFindingsAvailable] = useState<number>(0);
  // Code review M3: the true (pre-cap) blocker/warning totals, so the count
  // badges can show the real numbers instead of only counting the (possibly
  // capped) `findings` array — a workspace with 4,440 real blockers must not
  // show "500" with no indication that count is partial.
  const [totalBlockersAvailable, setTotalBlockersAvailable] = useState<number>(0);
  const [totalWarningsAvailable, setTotalWarningsAvailable] = useState<number>(0);

  const [severityFilter, setSeverityFilter] = useState<"all" | "blocker" | "warning">("all");
  const [actionState, setActionState] = useState<Record<number, ActionState>>({});
  const [toast, setToast] = useState<string | null>(null);

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
  const load = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (scope === "document" && !scopeArtifactId) return;

    setIsLoading(true);
    setLoadError(null);
    try {
      const report = await auditApi.run(activeWorkspace.id, {
        scope,
        scopeArtifactId: scope === "document" ? scopeArtifactId : undefined,
      });
      setTier(report.tier);
      setFindings(report.findings);
      setTruncated(report.truncated);
      setTotalFindingsAvailable(report.total_findings_available);
      setTotalBlockersAvailable(report.total_blockers_available);
      setTotalWarningsAvailable(report.total_warnings_available);
      setActionState({});
    } catch (err) {
      setLoadError(resolveErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, scope, scopeArtifactId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id, scope, scopeArtifactId]);

  // Auto-dismiss the success toast.
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

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
            [finding.index]: { status: "error", message: resolveErrorMessage(err) },
          }));
        }
      }
    },
    [activeWorkspace, scope, scopeArtifactId, t]
  );

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

  // ---- Derived state ----
  const filteredFindings = useMemo(
    () =>
      severityFilter === "all"
        ? findings
        : findings.filter((f) => f.severity === severityFilter),
    [findings, severityFilter]
  );

  // Counts are recomputed from the live findings list (not the initial
  // report.counts) so the badges stay accurate after a finding is resolved —
  // but only when the run was NOT truncated: the client-side `findings`
  // array only ever holds the (possibly capped) returned subset, so counting
  // it directly would silently show "500" as if it were the true total
  // (code review M3). When truncated, show the backend's real pre-cap
  // totals instead; these are a snapshot from the last full run_audit() call
  // and do not shrink live as findings are Adopted, but that is preferable
  // to a badge that understates the real number of open findings.
  const counts = useMemo(
    () =>
      truncated
        ? {
            total: totalFindingsAvailable,
            blockers: totalBlockersAvailable,
            warnings: totalWarningsAvailable,
          }
        : {
            total: findings.length,
            blockers: findings.filter((f) => f.severity === "blocker").length,
            warnings: findings.filter((f) => f.severity === "warning").length,
          },
    [findings, truncated, totalFindingsAvailable, totalBlockersAvailable, totalWarningsAvailable]
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
        <p style={{ color: "var(--color-text-muted)" }}>
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

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          marginBottom: "var(--space-4)",
          gap: "var(--space-3)",
          flexWrap: "wrap",
        }}
      >
        <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
          {t("audit.scope.label", "Scope")}
          <select
            data-testid="audit-scope-select"
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as AuditScopeKind);
              setScopeArtifactId("");
            }}
            style={selectStyle}
          >
            {SCOPES.map((s) => (
              <option key={s} value={s}>
                {t(`audit.scope.${s}`, s)}
              </option>
            ))}
          </select>
        </label>

        {scope === "document" && (
          <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
            {t("audit.scopeArtifact.label", "Document")}
            <select
              data-testid="audit-scope-artifact-select"
              value={scopeArtifactId}
              onChange={(e) => setScopeArtifactId(e.target.value)}
              disabled={artifacts.length === 0}
              style={selectStyle}
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

        <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
          {t("audit.severityFilter.label", "Severity")}
          <select
            data-testid="audit-severity-filter"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as "all" | "blocker" | "warning")}
            style={selectStyle}
          >
            <option value="all">{t("audit.severityFilter.all", "All")}</option>
            <option value="blocker">{t("audit.severityFilter.blocker", "Blockers")}</option>
            <option value="warning">{t("audit.severityFilter.warning", "Warnings")}</option>
          </select>
        </label>

        <button
          type="button"
          data-testid="audit-refresh-btn"
          onClick={() => void load()}
          disabled={isLoading}
          style={refreshButtonStyle(isLoading)}
        >
          {isLoading ? t("audit.refreshing", "Refreshing...") : t("audit.refresh", "Refresh")}
        </button>
      </div>

      {/* Counts + tier */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
        <span data-testid="audit-count-total" style={countBadgeStyle("neutral")}>
          {t("audit.counts.total", "Findings")}: {counts.total}
        </span>
        <span data-testid="audit-count-blockers" style={countBadgeStyle("danger")}>
          {t("audit.counts.blockers", "Blockers")}: {counts.blockers}
        </span>
        <span data-testid="audit-count-warnings" style={countBadgeStyle("warning")}>
          {t("audit.counts.warnings", "Warnings")}: {counts.warnings}
        </span>
        {tier && (
          <span data-testid="audit-tier" style={countBadgeStyle("neutral")}>
            {t("audit.tier", "Rigor tier")}: {tier}
          </span>
        )}
      </div>

      {/* BUG-15: the run produced more findings than the backend returns in
          one response — say so explicitly instead of silently showing a
          partial list that looks complete. */}
      {truncated && (
        <div
          role="status"
          data-testid="audit-truncated-banner"
          style={truncatedBannerStyle}
        >
          {t(
            "audit.truncated",
            "Showing {{shown}} of {{total}} findings — resolve some and refresh to see the rest.",
            { shown: findings.length, total: totalFindingsAvailable },
          )}
        </div>
      )}

      {/* GitHub #451: "Adopt" vs "Modify" is not a per-rule quirk (TRACE-P5
          showing "Adopt" while everything else showed "Modify" read like an
          inconsistency) — it is the two outcomes of the backend's remediation
          analysis. Stated once, here, instead of being folklore. */}
      {findings.length > 0 && (
        <p data-testid="audit-action-legend" style={legendStyle}>
          {t(
            "audit.actionLegend",
            "Adopt applies the correction the auditor derived automatically. Modify opens the affected artifact so you can correct it yourself — findings are recomputed from the trace graph, so they disappear once the artifact is fixed.",
          )}
        </p>
      )}

      {toast && (
        <div role="status" data-testid="audit-toast" style={toastStyle}>
          {toast}
        </div>
      )}

      {loadError && (
        <div role="alert" data-testid="audit-load-error" style={errorBannerStyle}>
          {loadError}
        </div>
      )}

      {isLoading && findings.length === 0 && !loadError ? (
        <p data-testid="audit-loading">{t("audit.loading", "Loading...")}</p>
      ) : !loadError && grouped.length === 0 ? (
        <p data-testid="audit-empty" style={{ color: "var(--color-text-muted)" }}>
          {t("audit.empty", "No findings — the trace graph is consistent for this scope.")}
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {grouped.map(([ruleId, groupFindings]) => (
            <FindingGroup
              key={ruleId}
              ruleId={ruleId}
              findings={groupFindings}
              actionState={actionState}
              targets={targets}
              onAdopt={handleAdopt}
              onModify={handleModify}
            />
          ))}
        </div>
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
}

function FindingGroup({
  ruleId,
  findings,
  actionState,
  targets,
  onAdopt,
  onModify,
}: FindingGroupProps): JSX.Element {
  const { t } = useTranslation();
  const blockers = findings.filter((f) => f.severity === "blocker").length;
  const warnings = findings.filter((f) => f.severity === "warning").length;

  return (
    <section
      data-testid={`audit-group-${ruleId}`}
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-lg)",
        background: "var(--color-surface)",
        overflow: "hidden",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--color-border)",
          background: "var(--color-surface-raised)",
        }}
      >
        <span style={{ fontFamily: "monospace", fontWeight: 700, color: "var(--color-text)" }}>{ruleId}</span>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          {blockers > 0 && (
            <span style={countBadgeStyle("danger")}>
              {t("audit.counts.blockers", "Blockers")}: {blockers}
            </span>
          )}
          {warnings > 0 && (
            <span style={countBadgeStyle("warning")}>
              {t("audit.counts.warnings", "Warnings")}: {warnings}
            </span>
          )}
        </div>
      </header>

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {findings.map((finding) => (
          <FindingRow
            key={finding.index}
            finding={finding}
            action={actionState[finding.index] ?? { status: "idle" }}
            target={primaryTarget(finding, targets)}
            onAdopt={onAdopt}
            onModify={onModify}
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
}

function FindingRow({
  finding,
  action,
  target,
  onAdopt,
  onModify,
}: FindingRowProps): JSX.Element {
  const { t } = useTranslation();
  const isPending = action.status === "pending";

  return (
    <li
      data-testid={`audit-finding-${finding.index}`}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        padding: "var(--space-3) var(--space-4)",
        borderBottom: "1px solid var(--color-border)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <span
          data-testid={`audit-finding-severity-${finding.index}`}
          style={countBadgeStyle(finding.severity === "blocker" ? "danger" : "warning")}
        >
          {t(`audit.severity.${finding.severity}`, finding.severity)}
        </span>
        <span style={{ color: "var(--color-text)", fontSize: "var(--font-size-sm)" }}>{finding.message}</span>
      </div>

      {finding.artifact_ids.length > 0 && (
        <div
          data-testid={`audit-finding-artifacts-${finding.index}`}
          style={{ display: "flex", gap: "var(--space-1)", flexWrap: "wrap" }}
        >
          <span style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
            {t("audit.artifacts", "Affected artifacts")}:
          </span>
          {finding.artifact_ids.map((id) => (
            <span
              key={id}
              data-testid={`audit-finding-artifact-${finding.index}-${id}`}
              title={id}
              style={{
                fontFamily: "monospace",
                fontSize: "var(--font-size-xs)",
                background: "var(--color-badge-neutral-bg)",
                color: "var(--color-badge-neutral-text)",
                padding: "1px 6px",
                borderRadius: "var(--radius-full)",
              }}
            >
              {id.slice(0, 8)}…
            </span>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
        {finding.remediation.automatic ? (
          <button
            type="button"
            data-testid={`audit-adopt-${finding.index}`}
            onClick={() => onAdopt(finding)}
            disabled={isPending}
            title={finding.remediation.reason}
            style={adoptButtonStyle(isPending)}
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
                title={t(
                  "audit.modifyHint",
                  "Open the affected artifact to correct it manually.",
                )}
                style={modifyButtonStyle}
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
              style={modifyReasonStyle}
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
        {action.status === "error" && (
          <span data-testid={`audit-finding-error-${finding.index}`} role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-xs)" }}>
            {action.message}
          </span>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const selectStyle: CSSProperties = {
  padding: "var(--space-1) var(--space-2)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
};

function refreshButtonStyle(isLoading: boolean): CSSProperties {
  return {
    padding: "var(--space-2) var(--space-4)",
    background: "var(--color-primary)",
    color: "white",
    border: "none",
    borderRadius: "var(--radius-md)",
    cursor: isLoading ? "not-allowed" : "pointer",
    fontSize: "var(--font-size-sm)",
    fontWeight: 600,
    fontFamily: "inherit",
    opacity: isLoading ? 0.6 : 1,
  };
}

function countBadgeStyle(kind: "danger" | "warning" | "neutral"): CSSProperties {
  const bg =
    kind === "danger"
      ? "var(--color-badge-danger-bg)"
      : kind === "warning"
      ? "var(--color-badge-warning-bg)"
      : "var(--color-badge-neutral-bg)";
  const fg =
    kind === "danger"
      ? "var(--color-badge-danger-text)"
      : kind === "warning"
      ? "var(--color-badge-warning-text)"
      : "var(--color-badge-neutral-text)";
  return {
    display: "inline-block",
    padding: "2px var(--space-3)",
    borderRadius: "var(--radius-full)",
    background: bg,
    color: fg,
    fontSize: "var(--font-size-xs)",
    fontWeight: 600,
  };
}

const adoptButtonStyle = (isPending: boolean): CSSProperties => ({
  padding: "var(--space-1) var(--space-3)",
  background: "var(--color-success)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  cursor: isPending ? "not-allowed" : "pointer",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  fontFamily: "inherit",
  opacity: isPending ? 0.6 : 1,
});

// #451: a real, enabled action now — secondary/outline styling keeps it visually
// subordinate to the green "Adopt" (automatic) without reading as disabled.
const modifyButtonStyle: CSSProperties = {
  padding: "var(--space-1) var(--space-3)",
  background: "transparent",
  color: "var(--color-primary)",
  border: "1px solid var(--color-primary)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  fontFamily: "inherit",
  whiteSpace: "nowrap",
};

const legendStyle: CSSProperties = {
  margin: "0 0 var(--space-4) 0",
  color: "var(--color-text-muted)",
  fontSize: "var(--font-size-xs)",
  lineHeight: 1.5,
};

const modifyReasonStyle: CSSProperties = {
  color: "var(--color-text-muted)",
  fontSize: "var(--font-size-xs)",
  fontStyle: "italic",
};

const toastStyle: CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  marginBottom: "var(--space-4)",
  background: "var(--color-badge-success-bg)",
  color: "var(--color-badge-success-text)",
  border: "1px solid var(--color-success)",
  borderRadius: "var(--radius-md)",
  fontSize: "var(--font-size-sm)",
};

const truncatedBannerStyle: CSSProperties = {
  padding: "var(--space-3) var(--space-4)",
  marginBottom: "var(--space-4)",
  background: "var(--color-badge-warning-bg)",
  border: "1px solid var(--color-warning)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-badge-warning-text)",
  fontSize: "var(--font-size-sm)",
};

const errorBannerStyle: CSSProperties = {
  padding: "var(--space-3) var(--space-4)",
  marginBottom: "var(--space-4)",
  background: "var(--color-badge-danger-bg)",
  border: "1px solid var(--color-danger)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-badge-danger-text)",
  fontSize: "var(--font-size-sm)",
};
