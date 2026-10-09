import { apiClient, getAllPages } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  StakeholderNeed,
  PaginatedResponse,
} from "../types";

export interface DerivedRequirementDraft {
  title: string;
  description: string;
  rationale: string;
  suggested_parent_id: string;
}

/**
 * Issue #1095 — the `proposal` block the accept endpoint returns.
 *
 * It is always present so the client can never mistake a plain `draft` for a
 * reviewable AI proposal. `is_proposal` is read back from the workflow engine
 * (never the intended state), `reason` names why the graph could not express
 * a proposal when it could not.
 */
export interface DerivedRequirementProposal {
  /** The workflow state the artefact actually ended up in. */
  state: string;
  /** True only when `state === "proposed"` — i.e. a human will be shown it. */
  is_proposal: boolean;
  /** Whether the workspace graph could express a proposal at all. */
  supported: boolean;
  /** Who authored it (`ai-derivation` for this endpoint). */
  proposed_by: string;
  /** Human-facing provenance label. */
  label: string;
  /** Empty on success; otherwise why the proposal state was unavailable. */
  reason: string;
}

/** One artefact the server persisted for an accepted draft. */
export interface AcceptedDerivedRequirement {
  id: string;
  /** The real workflow state, read back from the engine. */
  status: string;
  /** The `derives-from` TraceLink back to the source need, created server-side. */
  trace_link_id: string;
  proposal: DerivedRequirementProposal;
}

/** The 201 body of `POST /needs/{id}/derive-requirements/accept/`. */
export interface AcceptDerivedRequirementsResult {
  count: number;
  created: AcceptedDerivedRequirement[];
  /** The batch's shared authoring decision (first entry's read-back). */
  proposal: DerivedRequirementProposal;
}

export const stakeholderNeedApi = {
  listByWorkspace: async (workspaceId: string, params?: Record<string, string>): Promise<PaginatedResponse<StakeholderNeed>> => {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
    return apiClient.get<PaginatedResponse<StakeholderNeed>>(`/workspaces/${workspaceId}/needs/${qs}`);
  },

  /**
   * Fetch all Stakeholder Needs for a workspace, following pagination links
   * until exhaustion (issue C — listByWorkspace() only returned page 1).
   */
  listAll: async (workspaceId: string): Promise<StakeholderNeed[]> => {
    return getAllPages<StakeholderNeed>(`/workspaces/${workspaceId}/needs/`);
  },

  get: async (id: string): Promise<StakeholderNeed> => {
    return apiClient.get<StakeholderNeed>(`/needs/${id}/`);
  },

  create: async (workspaceId: string, data: Partial<StakeholderNeed>): Promise<StakeholderNeed> => {
    return apiClient.post<StakeholderNeed>(`/workspaces/${workspaceId}/needs/`, data);
  },

  /**
   * REQ-162: `change_reason` is mandatory when the workspace preset requires
   * it (Extended preset — see backend/application/preset_policy_service.py,
   * `is_change_reason_required`).
   *
   * Task 23 (rollout wave 2c): widened from a fixed `Partial<Pick<StakeholderNeed,
   * ...>>` to `Record<string, unknown>`, same deviation as `risksApi.update`/
   * `issuesApi.update` (Tasks 19/20). The payload now comes from `ArtifactForm`
   * (`NeedArtifactForm`'s `formValuesToNeedPatch`), a generic definition-driven
   * value bag whose keys are whatever the resolved attribute definition
   * currently lists, not a fixed compile-time-known set — the backend's own
   * per-field 400s remain the actual validation authority (see
   * StakeholderNeedViewSet.partial_update / field_validation.py).
   */
  update: async (id: string, data: Record<string, unknown>): Promise<StakeholderNeed> => {
    return apiClient.patch<StakeholderNeed>(`/needs/${id}/`, data);
  },

  delete: async (id: string, change_reason?: string): Promise<void> => {
    return apiClient.delete(`/needs/${id}/`, { data: { change_reason } });
  },

  /** Async fire-and-forget Celery dispatch. Result not persisted/read by UI. */
  derive: async (id: string): Promise<{ task_id: string; message: string }> => {
    return apiClient.post<{ task_id: string; message: string }>(`/needs/${id}/derive/`, {});
  },

  /** Draft/Accept (REQ-L2-AI-001/002): returns proposed requirements without persisting. */
  deriveRequirements: async (
    id: string,
    n = 3
  ): Promise<{ drafts: DerivedRequirementDraft[] }> => {
    return apiClient.post<{ drafts: DerivedRequirementDraft[] }>(
      `/needs/${id}/derive-requirements/`,
      { n }
    );
  },

  /**
   * Issue #1095 — the server-side half of the Accept step.
   *
   * `deriveRequirements` is draft-only by design, so persisting the drafts the
   * human selected used to happen here: `requirementsApi.create` from a *user*
   * principal plus a hand-built `derives-from` TraceLink. Because
   * `workflow.services.initial_state_for` seeds "proposed" only for an `agent`
   * principal, every accepted draft was born `draft` instead — the artefact
   * existed, the panel reported success, and no human was ever shown it
   * (#1089). This posts the batch once and lets the server decide the state
   * through the single `ai_proposal_service` seam.
   *
   * `id` is the need's PK (the same identifier `deriveRequirements` takes),
   * NOT its artifact id — the endpoint resolves it via
   * `StakeholderNeedService.get`.
   *
   * The client sends neither `status` nor `from_ai`: the workflow state and
   * the AI provenance are derived server-side (#269/#851). `drafts` is the
   * only accepted top-level key; anything else is a 400 `VALIDATION_ERROR`.
   */
  acceptDerivedRequirements: async (
    id: string,
    drafts: Array<{ title: string; description?: string; rationale?: string }>
  ): Promise<AcceptDerivedRequirementsResult> => {
    return apiClient.post<AcceptDerivedRequirementsResult>(
      `/needs/${id}/derive-requirements/accept/`,
      { drafts }
    );
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/needs/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Stakeholder Need versions. Signature
   * mirrors `requirementsApi.diff` / `architectureApi.diff` so the
   * DiffPanel can swap fetchers per kind without changing the call site.
   */
  diff: async (id: string, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> => {
    return apiClient.get<ArtifactDiffResult>(
      `/needs/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for a Stakeholder Need. */
  versions: async (id: string): Promise<ArtifactVersion[]> => {
    return apiClient.get<ArtifactVersion[]>(`/needs/${id}/versions/`);
  },
};
