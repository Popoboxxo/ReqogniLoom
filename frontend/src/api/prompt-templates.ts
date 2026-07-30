/**
 * ARCH-L1-001 ReactFrontend — prompt template API (REQ-L2-PT-001).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001 (Tenant-scoped editable LLM prompt templates)
 *
 * Wraps the backend endpoints under /api/v1/prompt-templates/.
 *   GET   → current prompt slot content + factory defaults (defaults_dict)
 *   PATCH → partial update of one or more slots
 *   POST /reset/ → restore all slots (or a single slot) to their defaults
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Prompt slot identifiers understood by the backend. */
export type PromptSlot =
  | "need_to_sysreq"
  | "sysreq_to_arch_assign"
  | "sysreq_decompose_next_level"
  | "goal_aggregate";

export const PROMPT_SLOTS: readonly PromptSlot[] = [
  "need_to_sysreq",
  "sysreq_to_arch_assign",
  "sysreq_decompose_next_level",
  "goal_aggregate",
] as const;

/** Read shape returned by GET /prompt-templates/. */
export interface PromptTemplate {
  need_to_sysreq: string;
  sysreq_to_arch_assign: string;
  sysreq_decompose_next_level: string;
  goal_aggregate: string;
  defaults_dict: Record<PromptSlot, string>;
}

/** Write shape for PATCH /prompt-templates/ (all slots optional). */
export interface PromptTemplateUpdate {
  need_to_sysreq?: string;
  sysreq_to_arch_assign?: string;
  sysreq_decompose_next_level?: string;
  goal_aggregate?: string;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const promptTemplatesApi = {
  /** Fetch the active tenant's prompt templates. */
  async get(): Promise<PromptTemplate> {
    return apiClient.get<PromptTemplate>("/prompt-templates/");
  },

  /** Partially update one or more prompt slots. */
  async update(payload: PromptTemplateUpdate): Promise<PromptTemplate> {
    return apiClient.patch<PromptTemplate>("/prompt-templates/", payload);
  },

  /**
   * Reset prompt content to the factory defaults. Pass a ``slot`` to reset a
   * single slot; omit it to reset all slots.
   */
  async reset(slot?: PromptSlot): Promise<PromptTemplate> {
    return apiClient.post<PromptTemplate>(
      "/prompt-templates/reset/",
      slot ? { slot } : {}
    );
  },
};
