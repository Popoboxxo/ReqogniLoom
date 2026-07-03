/**
 * ARCH-L1-001 ReactFrontend — Workflows API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-L2-RA-001 (WorkflowDefinition endpoints)
 *
 * Wraps /api/v1/workflows/ (WorkflowDefinitionViewSet).
 *
 * Backend contract notes (rest_api/views.py::WorkflowDefinitionViewSet):
 *   - GET  /workflows/           always returns an empty result set — the
 *     WorkflowFacade does not expose a list operation. The client keeps the
 *     call for forward-compatibility.
 *   - POST /workflows/           initializes workflow states for an artifact
 *     ({workspace_id, artifact_id, name}) → 201 {"message": ...}
 *   - PATCH /workflows/<id>/     performs a state transition on the entity
 *     ({target_state, change_reason?}) → 200 {"id", "target_state"}
 *   - DELETE                     always 403 (definitions cannot be deleted).
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID } from "../types";

export interface WorkflowDefinition {
  id: UUID;
  workspace_id: UUID;
  artifact_id: UUID;
  name: string;
  version: number;
  created_at: string;
}

export interface WorkflowTransitionResult {
  id: string;
  target_state: string;
}

export const workflowsApi = {
  /** GET /api/v1/workflows/ — currently always empty (see contract notes). */
  list(workspaceId: UUID): Promise<PaginatedResponse<WorkflowDefinition>> {
    return getList<WorkflowDefinition>("/workflows/", {
      workspace_id: workspaceId,
    });
  },

  /** POST /api/v1/workflows/ — initialize workflow states for an artifact. */
  initialize(data: {
    workspace_id: UUID;
    artifact_id: UUID;
    name: string;
  }): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>("/workflows/", data);
  },

  /** PATCH /api/v1/workflows/<entityId>/ — transition an entity's state. */
  transition(
    entityId: UUID,
    targetState: string,
    changeReason?: string
  ): Promise<WorkflowTransitionResult> {
    return apiClient.patch<WorkflowTransitionResult>(`/workflows/${entityId}/`, {
      target_state: targetState,
      change_reason: changeReason ?? "",
    });
  },
};
