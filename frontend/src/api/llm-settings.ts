/**
 * ARCH-L1-001 ReactFrontend — LLM settings API (REQ-L2-LLM-001).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-LLM-001 (Tenant-scoped LLM provider configuration)
 *
 * Wraps the backend endpoints under /api/v1/llm-settings/.
 *   GET   → current configuration (api_key never returned; api_key_is_set flag)
 *   PATCH → partial update (omit api_key to keep the stored one)
 *
 * The ``api_key`` field is write-only end-to-end: it is sent on update but the
 * backend never echoes it back. The UI relies on ``api_key_is_set`` to render a
 * "configured" indicator.
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type LlmProvider = "anthropic" | "openai" | "ollama" | "opencode_go" | "mock";

export const LLM_PROVIDERS: readonly LlmProvider[] = [
  "anthropic",
  "openai",
  "ollama",
  "opencode_go",
  "mock",
] as const;

/** Read shape returned by GET /llm-settings/ (api_key is never present). */
export interface LlmSettings {
  provider: LlmProvider;
  base_url: string;
  model_name: string;
  api_key_is_set: boolean;
}

/** Write shape for PATCH /llm-settings/ (api_key optional and write-only). */
export interface LlmSettingsUpdate {
  provider?: LlmProvider;
  base_url?: string;
  model_name?: string;
  api_key?: string;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const llmSettingsApi = {
  /** Fetch the active tenant's LLM configuration. */
  async get(): Promise<LlmSettings> {
    return apiClient.get<LlmSettings>("/llm-settings/");
  },

  /** Partially update the LLM configuration. */
  async update(payload: LlmSettingsUpdate): Promise<LlmSettings> {
    return apiClient.patch<LlmSettings>("/llm-settings/", payload);
  },
};
