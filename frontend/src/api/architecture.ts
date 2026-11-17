/**
 * ARCH-L1-001 ReactFrontend — ArchitectureElements API.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-004 (Architecture-Editor)
 *
 * Wraps /api/v1/architecture/ endpoints.
 * NOTE: Backend route is /api/v1/architecture/ (not /architecture-elements/).
 */

import { apiClient, getAllPages, getList } from "./client";
import type { ArchitectureElement, PaginatedResponse, UUID, ArtifactDiffResult, ArtifactVersion } from "../types";

export const architectureApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<ArchitectureElement>> {
    return getList<ArchitectureElement>("/architecture/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * Bug fix B-ICD-004: the ICD source/target dropdowns showed only the
   * first paginated page of architecture elements. This helper follows
   * the paginator's `next` URL until exhaustion and returns the full
   * de-duplicated list of elements for the workspace.
   */
  listAll(workspaceId: UUID, includeDeleted = false): Promise<ArchitectureElement[]> {
    // R2A-005: use the central walker so this helper gets the same de-duplication
    // and 100-page truncation warning as every other full-pagination caller.
    // `getAllPages` supplies `page_size=100` when the caller does not set it.
    return getAllPages<ArchitectureElement>("/architecture/", {
      workspace_id: workspaceId,
      ...(includeDeleted ? { include_deleted: "true" } : {}),
    });
  },

  get(id: UUID): Promise<ArchitectureElement> {
    return apiClient.get<ArchitectureElement>(`/architecture/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    element_type?: string;
    parent_id?: UUID | null;
  }): Promise<ArchitectureElement> {
    return apiClient.post<ArchitectureElement>("/architecture/", data);
  },

  /**
   * Task 24 (ArchitectureElement rollout wave): widened from the former
   * closed `Pick<...>` type to `Record<string, unknown>` — same class of
   * change as `risksApi.update`/`issuesApi.update` — so
   * `ArchitectureArtifactForm`'s definition-driven patch body (built from
   * whatever the live attribute definition introspects, not a fixed field
   * list) type-checks. Optimistic-concurrency guard (`expected_version`,
   * Systemaudit 2026-08-27 UI-08) and `change_reason` still travel through
   * this same untyped bag; the backend remains the source of truth for
   * which keys are accepted.
   */
  update(id: UUID, data: Record<string, unknown>): Promise<ArchitectureElement> {
    return apiClient.patch<ArchitectureElement>(`/architecture/${id}/`, data);
  },

  /**
   * Reparenting helper — moves an element under a new parent.
   *
   * Used by the Architecture tree's drag & drop (see
   * `ArchitectureEditors.handleReparent`). The edit form's parent dropdown
   * does NOT go through here: it submits `parent_id` together with the rest
   * of the form in a single `update()` call. `parentId = null` detaches the
   * element and makes it a root (L0).
   *
   * The backend validates the hierarchy invariants on this PATCH, but only
   * those enabled for the workspace's rigor tier — a cycle (I1) is rejected at
   * Standard/Extended and accepted at Minimal. Both UI entry points therefore
   * screen for cycles before calling this (see `collectSelfAndDescendantIds`);
   * a direct API caller is not protected.
   */
  reparent(id: UUID, parentId: UUID | null): Promise<ArchitectureElement> {
    return architectureApi.update(id, { parent_id: parentId });
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/architecture/${id}/`);
  },

  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/architecture/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/architecture/${id}/versions/`);
  },

  // -----------------------------------------------------------------------
  // AI risk derivation (#1358 REST parity / #1360 UI entry)
  // -----------------------------------------------------------------------

  /**
   * POST /api/v1/architecture/{id}/derive-risks/ (`mode="preview"`, the
   * default): risk drafts for the element. `ephemeral: true` — nothing is
   * persisted.
   */
  deriveRisksPreview(id: UUID): Promise<ArchitectureDeriveRisksPreview> {
    return apiClient.post<ArchitectureDeriveRisksPreview>(
      `/architecture/${id}/derive-risks/`,
      {}
    );
  },

  /**
   * POST /api/v1/architecture/{id}/derive-risks/ (`mode="write"`): the
   * canonical persistence path (W12a) — persists each draft as a Risk linked
   * back via the `mitigates` TraceLink, born `proposed` where the workflow
   * supports it (#1089).
   */
  deriveRisksWrite(id: UUID): Promise<ArchitectureDeriveRisksReceipt> {
    return apiClient.post<ArchitectureDeriveRisksReceipt>(
      `/architecture/${id}/derive-risks/`,
      { mode: "write" }
    );
  },
};

/** One draft of `POST /architecture/{id}/derive-risks/` (`mode="preview"`). */
export interface ArchitectureDeriveRisksDraft {
  title: string;
  description?: string;
  probability?: string;
  impact?: string;
  category?: string;
}

export interface ArchitectureDeriveRisksPreview {
  drafts: ArchitectureDeriveRisksDraft[];
  architecture_element_id: string;
  /** #1358: the preview persists nothing — stated on the wire. */
  ephemeral?: boolean;
  is_mock_fallback?: boolean;
}

export interface ArchitectureDeriveRisksWrittenEntry {
  id: string;
  status: string;
  trace_link_id: string;
  proposal: { is_proposal: boolean; reason?: string };
}

export interface ArchitectureDeriveRisksReceipt {
  written: ArchitectureDeriveRisksWrittenEntry[];
  is_mock_fallback?: boolean;
  failed?: Array<{ draft?: unknown; error: string }>;
}
