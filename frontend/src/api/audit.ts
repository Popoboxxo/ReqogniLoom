/**
 * ARCH-L1-001 ReactFrontend — SE-Auditor Audit API.
 *
 * UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3 ("Auditor UI").
 *
 * Wraps the two workspace-scoped SE-Auditor endpoints (backend fixed,
 * commit 062587a3):
 *   GET  /api/v1/workspaces/<workspace_id>/audit/
 *   POST /api/v1/workspaces/<workspace_id>/audit/remediate/
 *
 * The rigor tier (minimal/standard/extended) is resolved server-side from
 * the workspace's active preset — there is no tier query param.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types — mirror AuditReport.to_dict() / RemediationResult.to_dict()
// (backend/application/audit_service.py).
// ---------------------------------------------------------------------------

export type AuditScopeKind = "document" | "project" | "global";
export type AuditSeverity = "blocker" | "warning";

/** The concrete mutation an automatic proposal maps to (RemediationActionKind). */
export type RemediationActionKind = "create_trace_link";

export interface RemediationProposal {
  rule_id: string;
  /** True if the fix can be applied without user input (drives Adopt vs. Modify). */
  automatic: boolean;
  /** What will be done (automatic) or why it cannot be done automatically (manual). */
  reason: string;
  finding_artifact_ids: string[];
  action_kind: RemediationActionKind | null;
  params: Record<string, string>;
}

export interface AuditFinding {
  rule_id: string;
  severity: AuditSeverity;
  message: string;
  artifact_ids: string[];
  scope: AuditScopeKind | null;
  scope_artifact_id: string | null;
  /** Stable position within this audit run — correlates an Adopt click back to the finding. */
  index: number;
  /**
   * #569: canonical, run-independent identity of the finding, rendered with
   * its scope (`finding_key(rule_id, artifact_ids, scope)`). The backend has
   * always sent it (`AuditFindingView.finding_key`); the type only lagged.
   */
  finding_key: string;
  /**
   * #569: an active suppression (waiver) covers this finding. A suppressed
   * finding is **never hidden** by the default report — it stays in
   * `findings` and is marked, so the suppression is visible rather than
   * silent. `include_suppressed=false` filters it out server-side.
   */
  suppressed: boolean;
  /** #569: expiry of the matching suppression (`null` = unbounded). */
  suppressed_until: string | null;
  /** #569: justification of the matching suppression. */
  suppression_reason: string | null;
  /** #569: id of the matching `BaselineGateWaiver` row. */
  suppression_id: string | null;
  remediation: RemediationProposal;
}

/**
 * One consistent set of audit counts.
 *
 * #1382/#1383: the *same* five keys appear twice in a report and the two
 * objects mean different things:
 *   - `AuditReport.counts`     — the ground truth over the FULL run, independent
 *     of `limit`/`offset` (`counts.total === total_findings_available`).
 *   - `AuditReport.page_counts` — the returned window only (additive).
 *
 * Before #1383 `counts` described only the returned window, which is exactly
 * the bug behind #1382: the UI had to fall back to the `total_*_available`
 * fields to avoid presenting a partial window as the run total.
 */
export interface AuditCounts {
  total: number;
  /**
   * Blocker count — two different semantics, one per block:
   *   - `AuditReport.counts.blockers` is the *effective*, waiver-aware count
   *     over the full run (#1150): a blocker matched by an active waiver is
   *     already excluded here and is reported in `suppressed_blockers`
   *     instead. This is the badge/baseline number.
   *   - `AuditReport.page_counts.blockers` is a *raw* window counter: it
   *     counts every BLOCKER row in the returned window, INCLUDING suppressed
   *     ones, so `blockers + warnings === total` holds on that block. It is
   *     descriptive only, never a gate verdict — use `counts` for the
   *     waiver-aware number.
   * The dashboard corrects a local waive/adopt on top of the last snapshot
   * instead of deriving a badge from either block's window values.
   */
  blockers: number;
  warnings: number;
  /** #569 (additive): suppressed findings, counted additively to `total`. */
  suppressed: number;
  /** #569 (additive): of `suppressed`, the BLOCKER-severity ones. */
  suppressed_blockers: number;
}

export interface AuditReport {
  tier: string;
  scope: AuditScopeKind | null;
  scope_artifact_id: string | null;
  /**
   * #1382/#1383: ground truth for the FULL run — NOT the returned window.
   * `counts.total === total_findings_available`; use this for every
   * "how many findings are there" badge/banner total, never `findings.length`.
   */
  counts: AuditCounts;
  /**
   * #1383 (additive): the same five keys, but describing only the findings in
   * this response's window. Use it wherever the window size itself is shown
   * (e.g. "{{shown}} of {{total}}" with `counts.total` as the total).
   *
   * Optional because a backend that predates #1383 does not send it at all —
   * its absence is the discriminator the dashboard uses for the legacy shape
   * (there, `counts` is window-scoped and `total_*_available` carries the run
   * total). `null` is accepted for the same reason.
   */
  page_counts?: AuditCounts | null;
  /**
   * Without `limit`: true when the backend capped the result set
   * (AuditService.MAX_REPORT_FINDINGS). With `limit` (#622/#596): true when
   * more findings exist *past* this window — i.e. the client should request
   * the next one.
   */
  truncated: boolean;
  /** Total findings the run actually produced, before any truncation/windowing. */
  total_findings_available: number;
  /** True blocker count before truncation. Effective: waived blockers are excluded (#1150). */
  total_blockers_available: number;
  /** #1150: explicit alias of `total_blockers_available` (same effective, waiver-aware value). */
  total_effective_blockers: number;
  /** True warning count before truncation (see total_blockers_available). */
  total_warnings_available: number;
  /**
   * #569 (additive): suppressed findings in the full, uncapped run.
   * #1383: identical to `counts.suppressed` now that `counts` describes the
   * full run; kept because the field is part of the existing response
   * contract. `counts.*` is the canonical source for the UI.
   */
  total_suppressed_available: number;
  /** #569 (additive): of `total_suppressed_available`, the BLOCKER ones. */
  total_suppressed_blockers_available: number;
  /**
   * #569 (additive, m7): how many findings the `include_suppressed=false`
   * filter removed from `findings` (0 when the filter is off). With #1383 the
   * full-run counts stay in `counts`, so this only explains the difference
   * between `page_counts` (window) and the mounted rows.
   */
  suppressed_filtered: number;
  /**
   * #622: position of `findings[0]` within the full (pre-cap) run — always 0
   * for a request without `limit`.
   */
  offset: number;
  /**
   * #1383: server cursor for the next window — the value to send as `offset`
   * while `truncated` is true. `null` once the run has been fully paged.
   * Do NOT recompute this client-side (`offset + findings.length` is only the
   * old approximation and breaks as soon as the server skips findings).
   *
   * Optional because a backend that predates #1383 does not send it at all
   * (same legacy discriminator as `page_counts`).
   */
  next_offset?: number | null;
  findings: AuditFinding[];
}

// ---------------------------------------------------------------------------
// #1262 — SE-Auditor rule catalogue (GET /api/v1/audit/rules/)
// ---------------------------------------------------------------------------

/**
 * Catalogue metadata for one registered audit rule. Mirrors
 * ``traceability.audit.registry.get_rule_catalogue()`` (backend). ``severity``
 * is the rule's gate-effective severity at the strictest tier; ``active_tiers``
 * lists the rigor tiers the rule runs in.
 */
export interface AuditRuleInfo {
  rule_id: string;
  title: string;
  description: string;
  severity: AuditSeverity;
  standard_ref: string;
  remediation_hint: string;
  active_tiers: string[];
  is_scope_aware: boolean;
  deferred: boolean;
}

export interface AuditRuleCatalogResponse {
  rules: AuditRuleInfo[];
}

export interface RemediateRequest {
  rule_id: string;
  artifact_ids: string[];
  scope?: AuditScopeKind;
  scope_artifact_id?: string;
}

export interface RemediateResult {
  applied: boolean;
  finding_resolved: boolean | null;
  created_link_id: string | null;
  proposal: RemediationProposal;
}

// ---------------------------------------------------------------------------
// #569 — SE-Auditor finding suppression (waivers). Mirrors
// SuppressionView.to_dict() / the POST …/audit/waivers/ request body.
// ---------------------------------------------------------------------------

/** Lifecycle filter accepted by `GET …/audit/waivers/?state=`. */
export type WaiverState = "active" | "expired" | "all";

/** Derived lifecycle of one suppression row (`expires_at` vs. now). */
export type WaiverLifecycle = "active" | "expired";

/**
 * One persisted suppression (`BaselineGateWaiver`). `finding_key` is the
 * scope-less, persisted identity (GH-821); `identity_key` includes the scope
 * and exists only for display/correlation.
 */
export interface SuppressionView {
  waiver_id: string;
  finding_key: string;
  identity_key: string;
  rule_id: string;
  artifact_ids: string[];
  scope: string;
  scope_artifact_id: string;
  reason: string;
  granted_by: string;
  created_at: string;
  expires_at: string | null;
  state: WaiverLifecycle;
}

export interface WaiverListResponse {
  waivers: SuppressionView[];
  counts: { active: number; expired: number };
}

/**
 * Request body for `POST …/audit/waivers/`. `scope`/`scope_artifact_id` only
 * select the engine scope for the existence check and must be copied from the
 * clicked finding (C1) — the persisted scope always comes from the matched
 * finding server-side. `granted_by` is deliberately absent: the server derives
 * the author from the auth context and rejects a body field with 400.
 */
export interface WaiveRequest {
  rule_id: string;
  artifact_ids: string[];
  scope?: AuditScopeKind;
  scope_artifact_id?: string;
  reason: string;
  /** ISO-8601 with timezone; a naive or already-past value is rejected 400. */
  expires_at?: string;
}

export interface RunAuditOptions {
  scope?: AuditScopeKind;
  scopeArtifactId?: string;
  /**
   * #622/#596: return a plain sequential window of the full result set
   * (`findings[offset:offset+limit]`) instead of the default BLOCKER-first
   * capped view — lets the dashboard page through thousands of findings
   * without mounting them all. Capped server-side at MAX_REPORT_FINDINGS.
   */
  limit?: number;
  /** Start position of the requested window; only meaningful with `limit`. */
  offset?: number;
  /**
   * #569 (O3): whether suppressed findings stay in `findings` (marked
   * `suppressed=true`). Default `true` — nothing is hidden by default. Only
   * the literals `true`/`false` are accepted server-side; anything else is
   * rejected with 400.
   */
  includeSuppressed?: boolean;
  /**
   * #1262: server-side finding filters (``rule_id`` / ``severity`` /
   * ``artifact_type``). When set, the backend narrows the run before taking the
   * window, so `limit`/`offset` page over the filtered result.
   */
  ruleId?: string;
  severity?: AuditSeverity;
  artifactType?: string;
}

export const auditApi = {
  /** Run the SE-Auditor for the workspace and return findings + remediation proposals. */
  run(workspaceId: UUID, options: RunAuditOptions = {}): Promise<AuditReport> {
    const params = new URLSearchParams();
    if (options.scope) params.set("scope", options.scope);
    if (options.scopeArtifactId) {
      params.set("scope_artifact_id", options.scopeArtifactId);
    }
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    if (options.includeSuppressed !== undefined) {
      // #569/m2: the backend accepts only the literals `true`/`false`.
      params.set("include_suppressed", options.includeSuppressed ? "true" : "false");
    }
    // #1262: server-side filters.
    if (options.ruleId) params.set("rule_id", options.ruleId);
    if (options.severity) params.set("severity", options.severity);
    if (options.artifactType) params.set("artifact_type", options.artifactType);
    const qs = params.toString();
    return apiClient.get<AuditReport>(
      `/workspaces/${workspaceId}/audit/${qs ? `?${qs}` : ""}`
    );
  },

  /**
   * #1262: fetch the SE-Auditor rule catalogue — human-readable metadata
   * (title, description, severity, standard reference, remediation hint) for
   * every registered rule. Not workspace-scoped.
   */
  rules(): Promise<AuditRuleCatalogResponse> {
    return apiClient.get<AuditRuleCatalogResponse>("/audit/rules/");
  },

  /** Apply the automatic remediation for one finding (Adopt-Workflow). */
  remediate(workspaceId: UUID, data: RemediateRequest): Promise<RemediateResult> {
    return apiClient.post<RemediateResult>(
      `/workspaces/${workspaceId}/audit/remediate/`,
      data
    );
  },

  /**
   * #569: grant (or idempotently re-confirm) a suppression for one reported
   * BLOCKER finding. 201 when a new row is persisted, 200 when an identical
   * active waiver already exists. Failures carry a stable `error.code`
   * (`WAIVER_REASON_REJECTED`, `WAIVER_FINDING_NOT_BLOCKING`,
   * `SUPPRESSION_EXPIRED`, `VALIDATION_ERROR`, `PERMISSION_DENIED`,
   * `NOT_FOUND`) — callers must branch on that code, never on 422, which is
   * reserved for `remediate`.
   */
  waive(workspaceId: UUID, data: WaiveRequest): Promise<SuppressionView> {
    return apiClient.post<SuppressionView>(
      `/workspaces/${workspaceId}/audit/waivers/`,
      data
    );
  },

  /**
   * #569: list the workspace's suppressions by lifecycle state
   * (`active` default, `expired`, or `all`). An invalid state is a 400.
   */
  waivers(
    workspaceId: UUID,
    state: WaiverState = "active"
  ): Promise<WaiverListResponse> {
    const params = new URLSearchParams();
    if (state) params.set("state", state);
    const qs = params.toString();
    return apiClient.get<WaiverListResponse>(
      `/workspaces/${workspaceId}/audit/waivers/${qs ? `?${qs}` : ""}`
    );
  },
};
