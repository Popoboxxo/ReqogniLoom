/**
 * ARCH-L1-001 ReactFrontend — Suggestions API (ADR-019 / issue #1155).
 *
 * leaf_id: COMP-RF-SUG-001
 * req_id:  ADR-019 (generischer Vorschlags-Lebenszyklus, WP4),
 *          #1155 Aspekt 2 ("Vorschlags-Schleife")
 *
 * Thin wrapper over the REST surface of the persisted Suggestion inbox
 * (backend/rest_api/suggestion_views.py):
 *
 *   GET  /api/v1/suggestions/?workspace_id=<uuid>[&status=open][&kind=...]
 *   POST /api/v1/suggestions/<id>/accept/
 *   POST /api/v1/suggestions/<id>/reject/     body: {reason?: string}
 *
 * The list answers the standard pagination envelope
 * (`{count,next,previous,page_size,max_page_size,results}`); accept/reject
 * answer the updated serialized suggestion. Errors use the canonical envelope
 * (`{error:{code,message,details}}`): 403 PERMISSION_DENIED, 409
 * PRODUCER_CONTEXT_REQUIRED, 404 NOT_FOUND, 400 VALIDATION_ERROR — surfaced
 * unchanged by `client.ts` so callers can render `error.message` directly.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse } from "../types";

/** The four value kinds the backend registry knows (ADR-019 §2). */
export type SuggestionKind =
  | "artifact_create"
  | "trace_link"
  | "interview_grounding"
  | "context_edge";

/** Lifecycle states of a persisted suggestion. */
export type SuggestionStatus = "open" | "accepted" | "rejected" | "superseded";

/**
 * One row of `GET /api/v1/suggestions/`.
 *
 * Mirrors the serializer contract. Provenance (`producer`, `proposed_by`,
 * `proposed_at`, `decided_by`, `decided_at`) is server-set from the
 * authenticated principal / API key — never from a request body — so the UI
 * can render it as-is. `payload` is untrusted input for the accept path and is
 * therefore typed loosely.
 */
export interface Suggestion {
  id: string;
  kind: SuggestionKind;
  status: SuggestionStatus;
  /** Service/agent label that produced the suggestion. */
  producer: string | null;
  /** Display label of the actor who proposed it. */
  proposed_by: string | null;
  proposed_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  target_item_type: string | null;
  target_item_id: string | null;
  payload: Record<string, unknown>;
  workspace_id: string;
  created_at: string;
}

export interface ListSuggestionsParams {
  workspaceId: string;
  /** Defaults to `open` on the caller side; omitted → server default. */
  status?: SuggestionStatus;
  kind?: SuggestionKind;
  page?: number;
  pageSize?: number;
}

/** GET the (paginated) suggestion inbox for a workspace. */
export async function listSuggestions(
  params: ListSuggestionsParams,
): Promise<PaginatedResponse<Suggestion>> {
  const query: Record<string, string> = {
    workspace_id: params.workspaceId,
  };
  if (params.status) query.status = params.status;
  if (params.kind) query.kind = params.kind;
  if (params.page !== undefined) query.page = String(params.page);
  if (params.pageSize !== undefined) query.page_size = String(params.pageSize);
  return getList<Suggestion>("/suggestions/", query);
}

/**
 * POST accept — delegates server-side to the existing domain accept path and
 * returns the now-decided suggestion.
 */
export function acceptSuggestion(id: string): Promise<Suggestion> {
  return apiClient.post<Suggestion>(`/suggestions/${id}/accept/`, {});
}

/**
 * POST reject with an optional reason. The reason is advisory metadata only;
 * reject never destroys the target artifact (ADR-019 Zusage 7(e)).
 */
export function rejectSuggestion(id: string, reason?: string): Promise<Suggestion> {
  const trimmed = reason?.trim();
  return apiClient.post<Suggestion>(
    `/suggestions/${id}/reject/`,
    trimmed ? { reason: trimmed } : {},
  );
}
