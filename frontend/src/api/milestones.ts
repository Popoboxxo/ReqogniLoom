/**
 * ARCH-L1-001 ReactFrontend — Milestone API (Plan B B6-T2, #879).
 *
 * Wraps the `/api/v1/milestones/` surface introduced with the REST/MCP half of
 * Plan B B6. A milestone plans a formal review (SRR/PDR/CDR/TRR/ORR) and is a
 * plain tenant-scoped row — no Artifact, no workflow state.
 *
 * Optimistic locking follows the ETag contract (KA-B-06): the backend answers
 * GET/POST/PATCH with `ETag: "<version>"`, and `update` forwards the last-seen
 * version as the strong `If-Match` precondition. A stale header answers 412;
 * the two domain actions carry the same guard in the request body
 * (`expected_version`), where a stale value answers 409.
 */

import { apiClient, getList } from "./client";
import type { ISODateTime, PaginatedResponse, UUID } from "../types";

/** Formal review a milestone plans (`Milestone.ReviewType`). */
export const MILESTONE_REVIEW_TYPES = [
  "SRR",
  "PDR",
  "CDR",
  "TRR",
  "ORR",
  "OTHER",
] as const;
export type MilestoneReviewType = (typeof MILESTONE_REVIEW_TYPES)[number];

/** Planning/execution state (`Milestone.Status`). */
export const MILESTONE_STATUSES = [
  "planned",
  "in_review",
  "passed",
  "failed",
  "cancelled",
] as const;
export type MilestoneStatus = (typeof MILESTONE_STATUSES)[number];

/**
 * Frozen SE-Auditor counts written by `POST /milestones/{id}/record-audit/`.
 * A record, never a gate — blockers are stored, not enforced.
 */
export interface MilestoneAuditSnapshot {
  tier: string;
  counts: {
    total: number;
    blockers: number;
    warnings: number;
  };
  run_at: ISODateTime;
}

export interface Milestone {
  id: UUID;
  workspace_id: UUID;
  name: string;
  review_type: MilestoneReviewType;
  /** ISO-8601 date (`YYYY-MM-DD`); the primary list sort key. */
  target_date: string;
  status: MilestoneStatus;
  baseline_id: UUID | null;
  audit_snapshot: MilestoneAuditSnapshot | null;
  /** Optimistic-lock counter — the value the `ETag` carries. */
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime | null;
}

export interface MilestoneCreatePayload {
  workspace_id: UUID;
  name: string;
  review_type: MilestoneReviewType;
  target_date: string;
  status?: MilestoneStatus;
  /** Create only; rebinding goes through {@link milestonesApi.bindBaseline}. */
  baseline_id?: UUID | null;
}

export interface MilestoneUpdatePayload {
  name?: string;
  review_type?: MilestoneReviewType;
  target_date?: string;
  status?: MilestoneStatus;
  change_reason?: string;
}

export const milestonesApi = {
  /** List a workspace's milestones (ordered by `target_date`, then `id`). */
  list(params: { workspace_id: UUID }): Promise<PaginatedResponse<Milestone>> {
    return getList<Milestone>("/milestones/", {
      workspace_id: params.workspace_id,
    });
  },

  get(id: UUID): Promise<Milestone> {
    return apiClient.get<Milestone>(`/milestones/${id}/`);
  },

  create(payload: MilestoneCreatePayload): Promise<Milestone> {
    return apiClient.post<Milestone>("/milestones/", payload);
  },

  /**
   * PATCH a milestone. `expectedVersion` becomes the strong `If-Match`
   * precondition (`"<version>"`, exactly the backend's ETag); a stale value
   * answers 412 instead of overwriting a concurrent edit.
   */
  update(
    id: UUID,
    payload: MilestoneUpdatePayload,
    expectedVersion?: number
  ): Promise<Milestone> {
    return apiClient.patch<Milestone>(
      `/milestones/${id}/`,
      payload,
      undefined,
      expectedVersion !== undefined
        ? { "If-Match": `"${expectedVersion}"` }
        : undefined
    );
  },

  /**
   * Bind a baseline of the milestone's own workspace. A baseline from another
   * workspace is refused with 400 `VALIDATION_ERROR` by the service.
   */
  bindBaseline(
    id: UUID,
    baselineId: UUID,
    expectedVersion?: number,
    changeReason?: string
  ): Promise<Milestone> {
    return apiClient.post<Milestone>(
      `/milestones/${id}/bind-baseline/`,
      {
        baseline_id: baselineId,
        ...(expectedVersion !== undefined
          ? { expected_version: expectedVersion }
          : {}),
        ...(changeReason ? { change_reason: changeReason } : {}),
      }
    );
  },

  /**
   * Freeze the workspace's current SE-Auditor counts onto the milestone.
   * Open blockers do not refuse the record (unlike the baseline gate).
   */
  recordAudit(
    id: UUID,
    expectedVersion?: number,
    changeReason?: string
  ): Promise<Milestone> {
    return apiClient.post<Milestone>(
      `/milestones/${id}/record-audit/`,
      {
        ...(expectedVersion !== undefined
          ? { expected_version: expectedVersion }
          : {}),
        ...(changeReason ? { change_reason: changeReason } : {}),
      }
    );
  },
};
