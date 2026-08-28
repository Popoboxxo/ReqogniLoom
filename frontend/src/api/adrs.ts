/**
 * ARCH-L1-001 ReactFrontend — ADRs API.
 *
 * leaf_id: COMP-RF-003 (ADR editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/adrs/ endpoints.
 */

import { apiClient, getAllPages, getList } from "./client";
import type { Adr, ArtifactDiffResult, ArtifactVersion, PaginatedResponse, UUID } from "../types";

export const adrsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Adr>> {
    return getList<Adr>("/adrs/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * Fetch all ADRs for a workspace, following pagination links until
   * exhaustion (issue C — list() only returned the first page, capped at
   * PAGE_SIZE=25).
   */
  async listAll(workspaceId: UUID): Promise<Adr[]> {
    return getAllPages<Adr>("/adrs/", { workspace_id: workspaceId });
  },

  get(id: UUID): Promise<Adr> {
    return apiClient.get<Adr>(`/adrs/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    context?: string;
    consequences?: string;
    status?: string;
  }): Promise<Adr> {
    return apiClient.post<Adr>("/adrs/", data);
  },

  update(
    id: UUID,
    data: Partial<Pick<Adr, "title" | "description" | "context" | "consequences" | "status">> & {
      /** Extended preset: audit rationale forwarded to the backend audit log. */
      change_reason?: string;
    }
  ): Promise<Adr> {
    return apiClient.patch<Adr>(`/adrs/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/adrs/${id}/`);
  },

  /**
   * POST /adrs/{id}/supersede/ — UI-32 (Systemaudit 2026-08-27 AP-5):
   * dedicated REST entry point for `AdrService.transition_status`'s
   * `superseded_by_id` parameter (REQ-L3-ADR-005), which the generic
   * `.../transitions/` action never exposed (see the backend action's
   * docstring). Records a `decides` TraceLink from `supersededById` to
   * `id` and transitions `id` to `Superseded` through the WorkflowEngine.
   *
   * `credential` (F5, Systemaudit 2026-08-27 AP-5 review): the backend
   * action already forwards a `credential` field to
   * `AdrService.transition_status` (signature-gate support, same contract
   * `.../transitions/` uses), but no caller ever supplied one — a workspace
   * whose "Approved -> Superseded" move has `signature_gate: true` could not
   * complete a supersede at all. Optional and passed through unchanged; wiring
   * a `SignatureDialog` prompt into `AdrForm.tsx`'s supersede panel (detecting
   * `signature_gate` via `.../transitions/` GET, same as the generic
   * WorkflowStatusEditor flow) is a separate, larger UI change and is not done
   * here — see the AP-5 review report's F5 note.
   */
  supersede(
    id: UUID,
    supersededById: UUID,
    changeReason?: string,
    credential?: string
  ): Promise<Adr> {
    return apiClient.post<Adr>(`/adrs/${id}/supersede/`, {
      superseded_by_id: supersededById,
      change_reason: changeReason ?? "",
      credential: credential ?? "",
    });
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/adrs/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two ADR versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/adrs/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for an ADR. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/adrs/${id}/versions/`);
  },
};
