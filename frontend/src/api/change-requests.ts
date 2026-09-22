/**
 * ARCH-L1-001 ReactFrontend — Change Requests API.
 *
 * Wraps /api/v1/change-requests/. Used by the #399 drift shortcut in the
 * artifact editor header: a drifted, baselined artifact offers a direct entry
 * into the CCB path, pre-filling the artifact as an affected item.
 *
 * `affected_item_ids` is a write-only serializer field (spec section 4.4) and
 * the server validates the ids workspace-/tenant-scoped
 * (`ChangeRequestService._validate_affected_items`).
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** Mirror of the subset of `ChangeRequestSerializer` the shortcut reads back. */
export interface ChangeRequest {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description?: string;
  status: string;
  version: number;
}

export interface CreateChangeRequestPayload {
  workspace_id: UUID;
  title: string;
  description?: string;
  /** Write-only: artifacts to register as affected items of the new CR. */
  affected_item_ids?: UUID[];
}

export const changeRequestsApi = {
  create(payload: CreateChangeRequestPayload): Promise<ChangeRequest> {
    return apiClient.post<ChangeRequest>("/change-requests/", payload);
  },
};
