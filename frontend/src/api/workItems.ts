/**
 * ARCH-L1-001 ReactFrontend — WorkItem REST wrapper (Plan F F3-T9, #1374).
 *
 * Wraps the live REST surface from F3-T5:
 *
 *   GET    /api/v1/work-items/?workspace_id=[&document_id=][&include_deleted=]
 *   GET    /api/v1/work-items/{id}/
 *   POST   /api/v1/work-items/
 *   PATCH  /api/v1/work-items/{id}/            (If-Match: "<version>")
 *   DELETE /api/v1/work-items/{id}/            (optional change_reason)
 *   POST   /api/v1/work-items/{id}/reactivate/
 *   GET    /api/v1/work-items/{id}/transitions/
 *   POST   /api/v1/work-items/{id}/transitions/
 *   GET    /api/v1/work-items/{id}/versions/
 *   GET    /api/v1/work-items/{id}/diff/
 *   GET    /api/v1/work-items/resume/?workspace_id=&document_id=&actor=
 *
 * `expected_version`/`If-Match` guard the item's own revision (KA-F-08): a
 * stale strong tag answers 412, a stale body `expected_version` 409.
 */

import { apiClient, getAllPages } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  CustomFields,
  UUID,
  WorkItem,
  WorkItemKind,
  WorkItemResume,
  WorkItemTransitionResult,
  WorkItemTransitionsResponse,
} from "../types";

export interface WorkItemCreatePayload {
  workspace_id: UUID;
  document_id: UUID;
  title: string;
  kind: WorkItemKind;
  ordinal?: number;
  body?: string;
  progress?: number | null;
  blocked_reason?: string;
  next_action?: string;
  evidence_ref?: string;
  due_date?: string | null;
  exit_criteria?: string;
  custom_fields?: CustomFields;
  /** Free-text agent/machine identity for the heartbeat (A-3). */
  actor?: string;
}

/**
 * PATCH payload. Only fields present are sent; `progress: null` and
 * `due_date: null` clear the stored value. `document_id` is immutable — the
 * service rejects a move to another document instead of silently ignoring it.
 */
export interface WorkItemUpdatePayload {
  title?: string;
  kind?: WorkItemKind;
  ordinal?: number;
  body?: string;
  progress?: number | null;
  blocked_reason?: string;
  next_action?: string;
  evidence_ref?: string;
  due_date?: string | null;
  exit_criteria?: string;
  change_reason?: string;
  custom_fields?: CustomFields;
  actor?: string;
}

export interface WorkItemTransitionOptions {
  changeReason?: string;
  credential?: string;
  expectedVersion?: number;
  /** Required when the target state is `blocked` (rule 10). */
  blockedReason?: string;
  actor?: string;
}

export const workItemsApi = {
  /** Every item of a workspace (optionally one document), all pages. */
  listAll(
    workspaceId: UUID,
    documentId?: UUID,
    includeDeleted = false
  ): Promise<WorkItem[]> {
    return getAllPages<WorkItem>("/work-items/", {
      workspace_id: workspaceId,
      ...(documentId ? { document_id: documentId } : {}),
      ...(includeDeleted ? { include_deleted: "true" } : {}),
    });
  },

  get(id: UUID): Promise<WorkItem> {
    return apiClient.get<WorkItem>(`/work-items/${id}/`);
  },

  create(payload: WorkItemCreatePayload): Promise<WorkItem> {
    return apiClient.post<WorkItem>("/work-items/", payload);
  },

  /** PATCH an item; `expectedVersion` becomes the strong `If-Match` tag. */
  update(
    id: UUID,
    payload: WorkItemUpdatePayload,
    expectedVersion?: number
  ): Promise<WorkItem> {
    return apiClient.patch<WorkItem>(
      `/work-items/${id}/`,
      payload,
      undefined,
      expectedVersion !== undefined
        ? { "If-Match": `"${expectedVersion}"` }
        : undefined
    );
  },

  /** Soft-delete (G1.5 V2); the item stays readable with `status=outdated`. */
  delete(id: UUID, changeReason?: string): Promise<void> {
    return apiClient.delete(
      `/work-items/${id}/`,
      changeReason ? { change_reason: changeReason } : undefined
    );
  },

  /** Undo the soft delete (G1.5 V5). */
  reactivate(id: UUID): Promise<{ work_item: WorkItem }> {
    return apiClient.post<{ work_item: WorkItem }>(
      `/work-items/${id}/reactivate/`,
      {}
    );
  },

  transitions(id: UUID): Promise<WorkItemTransitionsResponse> {
    return apiClient.get<WorkItemTransitionsResponse>(
      `/work-items/${id}/transitions/`
    );
  },

  transition(
    id: UUID,
    targetState: string,
    options: WorkItemTransitionOptions = {}
  ): Promise<WorkItemTransitionResult> {
    return apiClient.post<WorkItemTransitionResult>(
      `/work-items/${id}/transitions/`,
      {
        target_state: targetState,
        change_reason: options.changeReason ?? "",
        credential: options.credential ?? "",
        ...(options.blockedReason !== undefined
          ? { blocked_reason: options.blockedReason }
          : {}),
        ...(options.expectedVersion !== undefined
          ? { expected_version: options.expectedVersion }
          : {}),
        ...(options.actor ? { actor: options.actor } : {}),
      }
    );
  },

  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/work-items/${id}/versions/`);
  },

  diff(
    id: UUID,
    fromVersion: number,
    toVersion: number
  ): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/work-items/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /**
   * The single read an agent needs to continue: newest checkpoint plus every
   * open item, sorted `(ordinal, id)`. Read-only by contract — it never
   * creates a heartbeat.
   */
  resume(
    workspaceId: UUID,
    documentId: UUID,
    actor = ""
  ): Promise<WorkItemResume> {
    const params = new URLSearchParams({
      workspace_id: workspaceId,
      document_id: documentId,
    });
    if (actor) params.set("actor", actor);
    return apiClient.get<WorkItemResume>(
      `/work-items/resume/?${params.toString()}`
    );
  },
};
