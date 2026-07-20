/**
 * ARCH-L1-001 ReactFrontend — Requirements API.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L2-RF-003 (Requirements-Editor)
 *
 * Wraps /api/v1/requirements/ endpoints.
 */

import { apiClient, getList } from "./client";
import type {
  Requirement,
  PaginatedResponse,
  UUID,
  ArtifactDiffResult,
  ArtifactVersion,
  SimilarRequirement,
} from "../types";

/**
 * REQ-143: a single allowed workflow transition from the current state.
 */
export interface AllowedTransition {
  target_state: string;
  requires_change_reason: boolean;
  signature_gate: boolean;
}

/**
 * REQ-143: response of GET /requirements/{id}/transitions/ — the current
 * WorkflowEngine state plus the moves allowed from it.
 */
export interface RequirementTransitions {
  current_state: string | null;
  states: string[];
  allowed_transitions: AllowedTransition[];
}

/**
 * REQ-143: response of POST /requirements/{id}/transitions/.
 */
export interface RequirementTransitionResult {
  id: string;
  previous_state: string;
  new_state: string;
  requirement: Requirement;
}

/**
 * REQ-144: a single entry of the append-only workflow transition history,
 * as returned by GET /requirements/{id}/workflow-history/. Mirrors the
 * WorkflowHistoryEntry model, minus the raw signature_seal (only a derived
 * `sealed` boolean crosses the API boundary).
 */
export interface WorkflowHistoryEntry {
  id: string;
  from_state: string | null;
  to_state: string;
  actor: string;
  change_reason: string;
  transitioned_at: string;
  sealed: boolean;
}

export const requirementsApi = {
  /**
   * REQ-144: optional `status` filters the list by the WorkflowEngine
   * lifecycle mirror (e.g. "in_review" for the review queue).
   */
  list(workspaceId: UUID, status?: string): Promise<PaginatedResponse<Requirement>> {
    const params: Record<string, string> = { workspace_id: workspaceId };
    if (status) params.status = status;
    return getList<Requirement>("/requirements/", params);
  },

  /**
   * Fetch all requirements for a workspace, following pagination links until
   * exhaustion. Use this when the full list is needed (e.g. dropdowns).
   */
  async listAll(workspaceId: UUID): Promise<Requirement[]> {
    const seen = new Set<UUID>();
    const all: Requirement[] = [];
    let resp = await getList<Requirement>("/requirements/", {
      workspace_id: workspaceId,
      page_size: "100",
    });
    for (const r of resp.results) {
      if (!seen.has(r.id)) {
        seen.add(r.id);
        all.push(r);
      }
    }
    let nextUrl: string | null = resp.next;
    let pageCount = 0;
     
    while (nextUrl && pageCount < 100) {
      pageCount += 1;
      // The backend may return `next` as an absolute URL, a path starting
      // with /api/v1, or a path relative to /api/v1. apiClient.get prepends
      // /api/v1, so we always need the path relative to that prefix.
      const m = nextUrl.match(/^(https?:\/\/[^/]+)?(\/api\/v1)?(\/.*)$/);
      const pathWithQuery = m ? m[3] : nextUrl;
      const nextResp = await apiClient.get<PaginatedResponse<Requirement>>(
        pathWithQuery.startsWith("/") ? pathWithQuery : `/${pathWithQuery}`
      );
      for (const r of nextResp.results) {
        if (!seen.has(r.id)) {
          seen.add(r.id);
          all.push(r);
        }
      }
      nextUrl = nextResp.next;
    }
    return all;
  },

  get(id: UUID): Promise<Requirement> {
    return apiClient.get<Requirement>(`/requirements/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    category?: string;
    custom_fields?: Requirement["custom_fields"];
  }): Promise<Requirement> {
    return apiClient.post<Requirement>("/requirements/", data);
  },

  // REQ-143: `status` is intentionally NOT part of the update contract — it is
  // a read-only WorkflowEngine mirror. Use `transition()` to change the state.
  update(
    id: UUID,
    data: Partial<Pick<Requirement, "title" | "description" | "category" | "change_reason" | "type" | "moscow_priority" | "complexity_fibonacci" | "verification_method" | "custom_fields">>
  ): Promise<Requirement> {
    return apiClient.patch<Requirement>(`/requirements/${id}/`, data);
  },

  /** REQ-143: GET the current workflow state and allowed next transitions. */
  getTransitions(id: UUID): Promise<RequirementTransitions> {
    return apiClient.get<RequirementTransitions>(
      `/requirements/${id}/transitions/`
    );
  },

  /**
   * REQ-143: perform a workflow transition (role/change_reason/gate enforced).
   * REQ-144: `credential` carries the password/TOTP token for transitions
   * whose `signature_gate` is true (see SignatureDialog).
   */
  transition(
    id: UUID,
    targetState: string,
    changeReason?: string,
    credential?: string
  ): Promise<RequirementTransitionResult> {
    return apiClient.post<RequirementTransitionResult>(
      `/requirements/${id}/transitions/`,
      {
        target_state: targetState,
        change_reason: changeReason ?? "",
        credential: credential ?? "",
      }
    );
  },

  /** REQ-144: GET the append-only workflow transition history for a requirement. */
  getWorkflowHistory(id: UUID): Promise<WorkflowHistoryEntry[]> {
    return apiClient.get<WorkflowHistoryEntry[]>(
      `/requirements/${id}/workflow-history/`
    );
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/requirements/${id}/`);
  },

  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/requirements/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/requirements/${id}/versions/`);
  },

  derive(
    id: UUID,
    data: { title: string; architecture_element_id: UUID; description?: string }
  ): Promise<{ requirement: Requirement; trace_link_ids: UUID[] }> {
    return apiClient.post<{ requirement: Requirement; trace_link_ids: UUID[] }>(
      `/requirements/${id}/derive/`,
      data
    );
  },

  /**
   * REQ-008: AI-assisted decomposition of a requirement to next-level drafts.
   *
   * Calls POST /api/v1/requirements/{id}/decompose-next-level/ which returns
   * proposed child requirement drafts without persisting them (Draft/Accept
   * pattern, REQ-L2-AI-001). Requires at least one allocated-to arch element.
   */
  aiDecomposeNextLevel(
    id: UUID
  ): Promise<{
    drafts: Array<{
      title: string;
      description: string;
      rationale: string;
      suggested_arch_element_id: string | null;
    }>;
    parent_requirement_id: string;
  }> {
    return apiClient.post(
      `/requirements/${id}/decompose-next-level/`,
      {}
    );
  },

  /**
   * SysEng 2.0 N5: AI-assisted TestCase draft derivation for a requirement.
   *
   * Calls POST /api/v1/requirements/{id}/derive-testcase/ which returns a
   * single TestCase draft (title, description, steps) without persisting it
   * (Draft/Accept pattern, REQ-L2-AI-001). Standard feature — no rigor-preset
   * gate, unlike aiDecomposeNextLevel.
   */
  aiDeriveTestcase(
    id: UUID
  ): Promise<{
    draft: {
      title: string;
      description: string;
      steps: Array<{ step: string; expected_result: string }>;
    };
    requirement_id: string;
  }> {
    return apiClient.post(`/requirements/${id}/derive-testcase/`, {});
  },

  /**
   * REQ-L2-VS-004: fetch the top-N requirements most similar to the given one
   * by semantic (cosine) similarity over pgvector embeddings.
   *
   * The backend returns 400 when the query requirement has no embedding yet,
   * and 503 when pgvector is unavailable — callers should surface these.
   */
  getSimilarRequirements(
    requirementId: UUID,
    limit = 10
  ): Promise<SimilarRequirement[]> {
    return apiClient.get<SimilarRequirement[]>(
      `/requirements/similar/?requirement_id=${requirementId}&limit=${limit}`
    );
  },
};
