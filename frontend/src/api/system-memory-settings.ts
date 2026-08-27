/**
 * ARCH-L1-001 ReactFrontend — System Memory Settings API (Memory Admin UI
 * Phase 3, spec 2026-08-26).
 *
 * Wraps /api/v1/system/memory-settings/ (GET/PUT) and its /reset/ POST.
 * System-Admin only. `honcho_api_key` is write-only end-to-end -- GET/PUT
 * responses only ever carry `honcho_api_key_is_set`.
 */

import { apiClient } from "./client";

export type EmbeddingProviderName = "sentence-transformers" | "ollama" | "openai" | "mock";
/**
 * SELECTABLE memory backends. "honcho" delegates memory to an external Honcho
 * instance and additionally needs a Honcho base URL configured (below);
 * without one it saves fine but reports unhealthy in System Health.
 * A deployment can still REPORT another effective value via its env var —
 * hence `SystemMemorySettings.memory_backend` below is a plain string.
 */
export type MemoryBackendName = "pgvector" | "honcho";

/** Effective (override-or-env) configuration, with per-field override flags. */
export interface SystemMemorySettings {
  embedding_provider: EmbeddingProviderName;
  embedding_provider_is_override: boolean;
  embedding_model_name: string | null;
  embedding_model_name_is_override: boolean;
  ollama_base_url: string | null;
  ollama_base_url_is_override: boolean;
  embedding_timeout: number;
  embedding_timeout_is_override: boolean;
  /** Effective value — may be any env-configured name, not just a selectable one. */
  memory_backend: string;
  memory_backend_is_override: boolean;
  honcho_base_url: string | null;
  honcho_base_url_is_override: boolean;
  honcho_api_key_is_set: boolean;
  warning: string | null;
}

export interface SystemMemorySettingsUpdate {
  embedding_provider?: EmbeddingProviderName | null;
  embedding_model_name?: string | null;
  ollama_base_url?: string | null;
  embedding_timeout?: number | null;
  memory_backend?: MemoryBackendName | null;
  honcho_base_url?: string | null;
  honcho_api_key?: string;
}

export const systemMemorySettingsApi = {
  async get(): Promise<SystemMemorySettings> {
    return apiClient.get<SystemMemorySettings>("/system/memory-settings/");
  },
  async update(payload: SystemMemorySettingsUpdate): Promise<SystemMemorySettings> {
    return apiClient.put<SystemMemorySettings>("/system/memory-settings/", payload);
  },
  async reset(): Promise<SystemMemorySettings> {
    return apiClient.post<SystemMemorySettings>("/system/memory-settings/reset/", {});
  },
};
