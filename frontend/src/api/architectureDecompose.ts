/**
 * ARCH-L1-001 ReactFrontend — SysEng 2.0 N1 (architecture.decompose) API.
 *
 * UMSETZUNGSPLAN_SYSENG_2.0.md §3.1 + §4 Phase 4a ("KI-Copilot").
 *
 * Wraps the two workspace-scoped Draft-Staging endpoints:
 *   POST /api/v1/workspaces/<workspace_id>/architecture/decompose/         (generate)
 *   POST /api/v1/workspaces/<workspace_id>/architecture/decompose/commit/  (commit)
 *
 * The draft returned by generate() is held in frontend state and echoed back
 * verbatim to commit() — there is no server-side draft persistence.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types — mirror ArchitectureDecomposeService DTOs (backend).
// ---------------------------------------------------------------------------

export interface DraftRequirement {
  title: string;
  description: string;
  rationale: string;
}

export interface DraftNode {
  temp_id: string;
  parent_temp_id: string | null;
  title: string;
  description: string;
  element_type: string;
  requirement: DraftRequirement;
}

export interface DecompositionDraft {
  workspace_id: string;
  root_element_id: string;
  parent_requirement_id: string;
  provider: string;
  /** True when the draft came from the mock fallback (no real LLM). */
  degraded: boolean;
  nodes: DraftNode[];
}

/**
 * UI-40: one SE-Auditor/invariant (I1-I5) finding, as carried by
 * `DecompositionAuditError.findings` on a 422 commit rollback — mirrors
 * `traceability.audit.types.Finding.to_dict()`.
 */
export interface DecomposeFinding {
  rule_id: string;
  severity: string;
  message: string;
  artifact_ids: string[];
  scope: string | null;
  scope_artifact_id: string | null;
}

export interface CommitResult {
  committed: boolean;
  root_element_id: string;
  created_element_ids: string[];
  created_requirement_ids: string[];
  created_link_ids: string[];
  verified_rules: string[];
  counts: { elements: number; requirements: number; links: number };
}

/**
 * Optional *upper bounds* for one decompose call (spec §4). Omitting a value
 * leaves the workspace's configured `max_breadth`/`max_depth` in force — the
 * AI decides the actual structure from the element's content.
 */
export interface GenerateDraftOptions {
  maxBreadth?: number;
  maxDepth?: number;
}

export const architectureDecomposeApi = {
  /** Generate a non-persistent decomposition draft for an ArchitectureElement. */
  generate(
    workspaceId: UUID,
    elementId: UUID,
    options: GenerateDraftOptions = {}
  ): Promise<DecompositionDraft> {
    return apiClient.post<DecompositionDraft>(
      `/workspaces/${workspaceId}/architecture/decompose/`,
      {
        element_id: elementId,
        ...(options.maxBreadth != null ? { max_breadth: options.maxBreadth } : {}),
        ...(options.maxDepth != null ? { max_depth: options.maxDepth } : {}),
      }
    );
  },

  /** Commit a reviewed draft in one transaction (rolled back on any failure). */
  commit(workspaceId: UUID, draft: DecompositionDraft): Promise<CommitResult> {
    return apiClient.post<CommitResult>(
      `/workspaces/${workspaceId}/architecture/decompose/commit/`,
      { draft }
    );
  },
};
