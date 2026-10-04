/**
 * ARCH-L1-001 ReactFrontend — API Keys API.
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — Personal Access Token management)
 * req_id:  REQ-L2-RF-027, REQ-L3-AT001-003 (API key lifecycle: create / list / revoke)
 *
 * Wraps /api/v1/api-keys/ endpoints (ApiKeyViewSet).
 * Keys are scoped to the authenticated user; the plaintext key is returned
 * exactly ONCE on create and can never be retrieved again.
 */

import { apiClient, asList } from "./client";
import type { PaginatedResponse, UUID } from "../types";

export interface ApiKeyMetadata {
  id: UUID;
  name: string;
  created_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
}

export interface ApiKeyCreateResult {
  id: UUID;
  name: string;
  /** Shown exactly once — never persisted or retrievable again. */
  plaintext: string;
  warning: string;
}

export const apiKeysApi = {
  /**
   * GET /api/v1/api-keys/ — metadata-only listing of the caller's keys.
   *
   * INT-05 (AUD-2026-09-074): the endpoint now paginates, so the body is the
   * standard `{count, next, ..., results}` envelope. The request asks for the
   * ceiling (`page_size=100`) because the settings panel renders the full key
   * list and the number of keys a user holds is small; `asList` keeps the
   * wrapper working during the deprecation window if an older backend still
   * answers with a bare array.
   */
  list(): Promise<ApiKeyMetadata[]> {
    return apiClient
      .get<PaginatedResponse<ApiKeyMetadata> | ApiKeyMetadata[]>("/api-keys/?page_size=100")
      .then(asList<ApiKeyMetadata>);
  },

  /** POST /api/v1/api-keys/ — create a key; plaintext returned once. */
  create(name: string): Promise<ApiKeyCreateResult> {
    return apiClient.post<ApiKeyCreateResult>("/api-keys/", { name });
  },

  /** DELETE /api/v1/api-keys/<id>/ — revoke a key (effective immediately). */
  revoke(id: UUID): Promise<void> {
    return apiClient.delete(`/api-keys/${id}/`);
  },
};
