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

export const requirementsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Requirement>> {
    return getList<Requirement>("/requirements/", {
      workspace_id: workspaceId,
    });
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

  update(
    id: UUID,
    data: Partial<Pick<Requirement, "title" | "description" | "category" | "status" | "change_reason" | "type" | "moscow_priority" | "complexity_fibonacci" | "verification_method" | "custom_fields">>
  ): Promise<Requirement> {
    return apiClient.patch<Requirement>(`/requirements/${id}/`, data);
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
