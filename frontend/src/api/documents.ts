/**
 * ARCH-L1-001 ReactFrontend — Document artifact API (Plan F F2-T8, ADR-026).
 *
 * Wraps the REST surface from F2-T5:
 *
 *   GET    /api/v1/documents/?workspace_id=[&include_deleted=true]
 *   GET    /api/v1/documents/{id}/
 *   POST   /api/v1/documents/
 *   PATCH  /api/v1/documents/{id}/            (If-Match: "<version>")
 *   DELETE /api/v1/documents/{id}/            (optional change_reason)
 *   POST   /api/v1/documents/{id}/reactivate/
 *   GET    /api/v1/documents/{id}/transitions/
 *   POST   /api/v1/documents/{id}/transitions/
 *
 * The transitions pair is Document-specific rather than the generic
 * `workflow-transitions` wrapper: Document's POST guards the **entity**
 * version (`expected_version` / `If-Match`), not the WorkflowItemState
 * revision (ADR-026 §9).
 */

import { apiClient, getAllPages } from "./client";
import type {
  CustomFields,
  Document,
  DocumentKind,
  UUID,
} from "../types";

export interface DocumentCreatePayload {
  workspace_id: UUID;
  title: string;
  kind: DocumentKind;
  description?: string;
  body?: string;
  doc_date?: string | null;
  custom_fields?: CustomFields;
}

/**
 * PATCH payload. Only fields present are sent; `doc_date: null` clears the
 * stored date. Frozen fields (`frozen_fields`) must be omitted by the caller —
 * the service rejects any write that touches one with `409 FIELD_FROZEN`.
 */
export interface DocumentUpdatePayload {
  title?: string;
  kind?: DocumentKind;
  description?: string;
  body?: string;
  doc_date?: string | null;
  change_reason?: string;
  custom_fields?: CustomFields;
}

/** One move allowed from the document's current state. */
export interface DocumentAllowedTransition {
  target_state: string;
  requires_change_reason: boolean;
  signature_gate: boolean;
}

/** Response of `GET /api/v1/documents/{id}/transitions/`. */
export interface DocumentTransitionsResponse {
  current_state: string | null;
  /** The Document revision (the value to echo as `expected_version`). */
  version: number;
  workflow_version?: number;
  states: string[];
  allowed_transitions: DocumentAllowedTransition[];
  proposed_by?: string | null;
}

/** Response of `POST /api/v1/documents/{id}/transitions/`. */
export interface DocumentTransitionResult {
  id: UUID;
  previous_state: string;
  new_state: string;
  /** The Document revision after the transition. */
  version: number;
  document: Document;
}

export interface DocumentTransitionOptions {
  changeReason?: string;
  credential?: string;
  expectedVersion?: number;
}

export const documentsApi = {
  /**
   * Fetch every document of a workspace, following pagination links until
   * exhaustion (the list endpoint is paginated like every other artifact
   * list; `getList` alone would silently stop after page one).
   */
  listAll(workspaceId: UUID, includeDeleted = false): Promise<Document[]> {
    return getAllPages<Document>("/documents/", {
      workspace_id: workspaceId,
      ...(includeDeleted ? { include_deleted: "true" } : {}),
    });
  },

  get(id: UUID): Promise<Document> {
    return apiClient.get<Document>(`/documents/${id}/`);
  },

  create(payload: DocumentCreatePayload): Promise<Document> {
    return apiClient.post<Document>("/documents/", payload);
  },

  /**
   * PATCH a document. `expectedVersion` becomes the strong `If-Match`
   * precondition (KA-F-08): a stale value answers 412, while a stale body
   * `expected_version` answers 409. The UI forwards the version it rendered.
   */
  update(
    id: UUID,
    payload: DocumentUpdatePayload,
    expectedVersion?: number
  ): Promise<Document> {
    return apiClient.patch<Document>(
      `/documents/${id}/`,
      payload,
      undefined,
      expectedVersion !== undefined
        ? { "If-Match": `"${expectedVersion}"` }
        : undefined
    );
  },

  /**
   * Soft-delete a document (G1.5 V2). The backend may require a
   * `change_reason` depending on the workspace preset.
   */
  delete(id: UUID, changeReason?: string): Promise<void> {
    return apiClient.delete(
      `/documents/${id}/`,
      changeReason ? { change_reason: changeReason } : undefined
    );
  },

  /** Undo a soft delete (G1.5 V5). */
  reactivate(id: UUID): Promise<{ document: Document }> {
    return apiClient.post<{ document: Document }>(
      `/documents/${id}/reactivate/`,
      {}
    );
  },

  /** GET the current state and the moves allowed from it. */
  transitions(id: UUID): Promise<DocumentTransitionsResponse> {
    return apiClient.get<DocumentTransitionsResponse>(
      `/documents/${id}/transitions/`
    );
  },

  /**
   * POST a transition. The F-1 freeze, the F-5 re-open version bump and the
   * G-1…G-4 gates live in `DocumentService.transition_status`; this wrapper
   * only forwards the caller's input.
   */
  transition(
    id: UUID,
    targetState: string,
    options: DocumentTransitionOptions = {}
  ): Promise<DocumentTransitionResult> {
    return apiClient.post<DocumentTransitionResult>(
      `/documents/${id}/transitions/`,
      {
        target_state: targetState,
        change_reason: options.changeReason ?? "",
        credential: options.credential ?? "",
        ...(options.expectedVersion !== undefined
          ? { expected_version: options.expectedVersion }
          : {}),
      }
    );
  },
};
