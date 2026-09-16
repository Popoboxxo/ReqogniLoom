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
  remediation: RemediationProposal;
}

export interface AuditCounts {
  total: number;
  blockers: number;
  warnings: number;
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
};
