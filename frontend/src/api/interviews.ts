/**
 * Interview-management web widget — frontend API client (plan Task 4).
 *
 * Thin wrapper over the REST facade `/api/v1/interviews/...` (plan Task 1/3),
 * itself a thin adapter over `application.interview_service.InterviewService`
 * -- the same engine the `interview.*` MCP tool group and the Hermes plugin's
 * `mcpClient.ts` wrap. This module intentionally duplicates
 * `InterviewField`/`InterviewState`/`InterviewSummary` rather than sharing
 * them with the plugin: there is no shared package between the plugin and
 * this frontend, so a small, independent duplication here is the correct
 * choice over a premature shared-package abstraction.
 */

import { apiClient, getAllPages, getList } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One field the interview protocol still needs an answer for. */
export interface InterviewField {
  name: string;
  type: "text" | "textarea" | "enum" | "number";
  choices: string[] | null;
}

/** One turn in an interview session's conversation history. */
export interface InterviewTranscriptEntry {
  role: string;
  text: string;
  timestamp: string;
}

/**
 * Full interview session state, as returned by the `state`/`answer`/`chat`
 * actions. NOTE: `InterviewService.get_state()` (backend/application/
 * interview_service.py) keys this dict as `session_id`, not `id` -- the REST
 * facade's `state`/`answer`/`chat` actions return that dict as-is. Only the
 * `start` action (`create()`, which merges `_session_to_dict()`'s `id` into
 * the `get_state()` result) is guaranteed to carry `id`. See this file's
 * developer report for the concrete risk this poses if the REST facade
 * (backend Task 1/2/3, built concurrently) doesn't reconcile the two keys.
 */
export interface InterviewState {
  id: string;
  status: "in_progress" | "completed" | "abandoned";
  phase: string;
  collected_fields: Record<string, unknown>;
  missing_fields: InterviewField[];
  grounding_snapshot: {
    /** Absent until `/grounding/` is explicitly called (lazy AI-ranked
     * computation) -- `start()` returns `{}`, not `{ candidates: [] }`. */
    candidates?: { artifact_id: string; title: string; score: number | null }[];
  };
  transcript: InterviewTranscriptEntry[];
}

/** Summary shape returned by list()/get() (`_session_to_dict()`). */
export interface InterviewSummary {
  id: string;
  workspace_id: string;
  artifact_type: string;
  status: string;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const interviewsApi = {
  /** Start a new interview session for `artifactType` in `workspaceId`. */
  start(workspaceId: UUID, artifactType: string): Promise<InterviewState> {
    return apiClient.post<InterviewState>("/interviews/", {
      artifact_type: artifactType,
      workspace_id: workspaceId,
    });
  },

  /** List interview sessions in `workspaceId`, optionally filtered by `status`. */
  async list(workspaceId: UUID, status?: string): Promise<InterviewSummary[]> {
    const params: Record<string, string> = { workspace_id: workspaceId };
    if (status) params.status = status;
    const page = await getList<InterviewSummary>("/interviews/", params);
    return page.results;
  },

  /**
   * Fetch all interview sessions for a workspace, following pagination links
   * until exhaustion (same issue #443-style truncation `adrsApi.listAll` and
   * siblings already fix -- `list()` above only returns the first page).
   */
  async listAll(workspaceId: UUID): Promise<InterviewSummary[]> {
    return getAllPages<InterviewSummary>("/interviews/", { workspace_id: workspaceId });
  },

  /** Fetch a session's summary (id/workspace_id/artifact_type/status). */
  get(id: UUID): Promise<InterviewSummary> {
    return apiClient.get<InterviewSummary>(`/interviews/${id}/`);
  },

  /** Fetch a session's full state (phase, collected/missing fields, grounding). */
  getState(id: UUID): Promise<InterviewState> {
    return apiClient.get<InterviewState>(`/interviews/${id}/state/`);
  },

  /** Record an answer for `field` and return the updated state. */
  answer(id: UUID, field: string, value: unknown): Promise<InterviewState> {
    return apiClient.post<InterviewState>(`/interviews/${id}/answer/`, {
      field,
      value,
    });
  },

  /** Structural + AI-ranked grounding candidates for the session. */
  groundingContext(id: UUID): Promise<InterviewState["grounding_snapshot"]> {
    return apiClient.get<InterviewState["grounding_snapshot"]>(
      `/interviews/${id}/grounding/`
    );
  },

  /** Turn the session's collected answers into a real artifact. */
  formalize(id: UUID): Promise<{ resulting_artifact_ids: string[]; status: string }> {
    return apiClient.post<{ resulting_artifact_ids: string[]; status: string }>(
      `/interviews/${id}/formalize/`,
      {}
    );
  },

  /** Send a free-form chat message and get back the assistant's reply + updated state. */
  chat(id: UUID, message: string): Promise<{ reply: string; state: InterviewState }> {
    return apiClient.post<{ reply: string; state: InterviewState }>(
      `/interviews/${id}/chat/`,
      { message }
    );
  },

  /** User-initiated cancel of an in-progress session (workflow: -> abandoned). */
  abandon(id: UUID): Promise<{ status: string }> {
    return apiClient.post<{ status: string }>(`/interviews/${id}/abandon/`, {});
  },
};
