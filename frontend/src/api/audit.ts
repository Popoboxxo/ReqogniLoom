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

export interface AuditCounts {
  total: number;
  blockers: number;
  warnings: number;
  /**
   * #569 (additive, M5): how many of the returned findings are suppressed.
   * `blockers`/`warnings` stay descriptive and are NOT re-interpreted — a
   * suppressed blocker still counts there.
   */
  suppressed: number;
  /** #569 (additive): of `suppressed`, the BLOCKER-severity ones. */
  suppressed_blockers: number;
}

export interface AuditReport {
  tier: string;
  scope: AuditScopeKind | null;
  scope_artifact_id: string | null;
  counts: AuditCounts;
  /**
   * Without `limit`: true when the backend capped the result set
   * (AuditService.MAX_REPORT_FINDINGS). With `limit` (#622/#596): true when
   * more findings exist *past* this window — i.e. the client should request
   * the next one.
   */
  truncated: boolean;
  /** Total findings the run actually produced, before any truncation/windowing. */
  total_findings_available: number;
  /** True blocker count before truncation (code review M3 — counts.blockers only covers the returned/capped subset). */
  total_blockers_available: number;
  /** True warning count before truncation (see total_blockers_available). */
  total_warnings_available: number;
  /**
   * #569 (additive): suppressed findings in the full, uncapped run. When the
   * client filters (`include_suppressed=false`) or the run is capped, the
   * `counts.*` describe the returned window while these describe the whole
   * run — `counts.total != total_findings_available` is expected then.
   */
  total_suppressed_available: number;
  /** #569 (additive): of `total_suppressed_available`, the BLOCKER ones. */
  total_suppressed_blockers_available: number;
  /**
   * #569 (additive, m7): how many findings the `include_suppressed=false`
   * filter removed from `findings` (0 when the filter is off). Explains the
   * `counts.total` vs `total_findings_available` difference.
   */
  suppressed_filtered: number;
  /**
   * #622: position of `findings[0]` within the full (pre-cap) run — always 0
   * for a request without `limit`. Next window start: `offset + findings.length`.
   */
  offset: number;
  findings: AuditFinding[];
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
    const qs = params.toString();
    return apiClient.get<AuditReport>(
      `/workspaces/${workspaceId}/audit/${qs ? `?${qs}` : ""}`
    );
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
