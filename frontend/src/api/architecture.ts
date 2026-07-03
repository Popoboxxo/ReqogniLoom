/**
 * ARCH-L1-001 ReactFrontend — ArchitectureElements API.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-004 (Architecture-Editor)
 *
 * Wraps /api/v1/architecture/ endpoints.
 * NOTE: Backend route is /api/v1/architecture/ (not /architecture-elements/).
 */

import { apiClient, getList } from "./client";
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
  async listAll(workspaceId: UUID): Promise<ArchitectureElement[]> {
    const seen = new Set<UUID>();
    const all: ArchitectureElement[] = [];
    let resp = await getList<ArchitectureElement>("/architecture/", {
      workspace_id: workspaceId,
    });
    for (const el of resp.results) {
      if (!seen.has(el.id)) {
        seen.add(el.id);
        all.push(el);
      }
    }
    // Follow pagination links. The `next` field is either null or a full
    // absolute URL pointing at the next page.
    let nextUrl: string | null = resp.next;
    let pageCount = 0;
    // eslint-disable-next-line no-constant-condition
    while (nextUrl && pageCount < 100) {
      pageCount += 1;
      // The backend may return `next` as an absolute URL, a path starting
      // with /api/v1, or a path relative to /api/v1. apiClient.get prepends
      // /api/v1, so we always need the path relative to that prefix.
      const m = nextUrl.match(/^(https?:\/\/[^/]+)?(\/api\/v1)?(\/.*)$/);
      const pathWithQuery = m ? m[3] : nextUrl;
      const nextResp = await apiClient.get<PaginatedResponse<ArchitectureElement>>(
        pathWithQuery.startsWith("/") ? pathWithQuery : `/${pathWithQuery}`
      );
      for (const el of nextResp.results) {
        if (!seen.has(el.id)) {
          seen.add(el.id);
          all.push(el);
        }
      }
      nextUrl = nextResp.next;
    }
    return all;
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

  update(
    id: UUID,
    data: Partial<
      Pick<ArchitectureElement, "title" | "description" | "element_type">
    >
  ): Promise<ArchitectureElement> {
    return apiClient.patch<ArchitectureElement>(`/architecture/${id}/`, data);
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
};
