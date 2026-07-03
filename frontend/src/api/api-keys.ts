/**
 * ARCH-L1-001 ReactFrontend — API Keys API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-L3-AT001-003 (API key lifecycle: create / list / revoke)
 *
 * Wraps /api/v1/api-keys/ endpoints (ApiKeyViewSet).
 * Keys are scoped to the authenticated user; the plaintext key is returned
 * exactly ONCE on create and can never be retrieved again.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

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
  /** GET /api/v1/api-keys/ — metadata-only listing of the caller's keys. */
  list(): Promise<ApiKeyMetadata[]> {
    return apiClient.get<ApiKeyMetadata[]>("/api-keys/");
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
