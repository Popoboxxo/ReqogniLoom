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
      page_size: "100",
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
      Pick<
        ArchitectureElement,
        | "title"
        | "description"
        | "element_type"
        | "parent_id"
        | "asil_level"
        | "make_or_buy"
        | "custom_fields"
      >
    > & {
      change_reason?: string;
      /**
       * Systemaudit 2026-08-27 UI-08: optimistic-concurrency guard (mirrors
       * the backend's `ArchitectureElementSerializer.expected_version` /
       * `ArchitectureService.update_architecture_element`). When provided
       * and it no longer matches the element's current `version`, the
       * backend rejects the PATCH with 409 CONFLICT instead of silently
       * overwriting a concurrent edit. Omit to keep the previous
       * backwards-compatible (unchecked) behavior — e.g. `reparent()` below,
       * which is a narrow drag & drop move, not a full-form save.
       */
      expected_version?: number;
    }
  ): Promise<ArchitectureElement> {
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
};
