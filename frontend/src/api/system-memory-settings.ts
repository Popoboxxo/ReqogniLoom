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
export type MemoryBackendName = "pgvector" | "honcho" | "qdrant";

/**
 * Honcho dialectic/reasoning depth (#1286) — the same vocabulary the `ask`
 * surface already accepts (`memory.ts: MemoryReasoningLevel`, mirroring
 * `honcho-ai`'s `peer.chat(reasoning_level=...)`). Kept as its own literal
 * here so the settings module has no import cycle back into the memory client.
 */
export type HonchoDialecticLevel = "minimal" | "low" | "medium" | "high" | "max";

/** All valid dialectic levels, ascending. Single source for the select + validation. */
export const HONCHO_DIALECTIC_LEVELS: readonly HonchoDialecticLevel[] = [
  "minimal",
  "low",
  "medium",
  "high",
  "max",
];

/** Runtime guard for the dialectic level — rejects any unknown backend/env value. */
export function isHonchoDialecticLevel(value: unknown): value is HonchoDialecticLevel {
  return (
    typeof value === "string" &&
    (HONCHO_DIALECTIC_LEVELS as readonly string[]).includes(value)
  );
}


/** One backend setting rendered by the admin surface (Plan A T-A0b-5). */
export interface BackendSettingField {
  name: string;
  type: "str" | "int" | "float" | "bool" | "choice" | "secret";
  env_var: string | null;
  label_key: string;
  choices: string[];
  min_value: number | null;
  max_length: number | null;
  default: unknown;
}

/** The additive `backends.<name>` block of the settings response. */
export interface BackendSettingsBlock {
  schema: BackendSettingField[];
  /** Effective, non-secret values (DB override > env > default). */
  values: Record<string, unknown>;
  is_override: Record<string, boolean>;
  /** Presence only — a secret value is never returned by the API. */
  secrets_set: Record<string, boolean>;
  capabilities: Record<string, unknown>;
}

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
  /**
   * #1286 additional Honcho configuration. Like every other field here these
   * are the effective (override-or-env) values plus a per-field override flag.
   *
   * REST-contract note (stream boundary): the backend's
   * `SystemMemorySettingsWriteSerializer` (memory_rest.py) does NOT yet declare
   * these keys, so a PUT carrying them is silently ignored server-side and the
   * GET response omits them (all `undefined`). The fields are wired through the
   * client/UI ahead of the backend contract; see the follow-up note in
   * `MemorySystemSettingsSection.tsx`. `honcho_version` is strictly read-only
   * and is populated from Honcho's `/health` (null when unreachable/unsupported).
   */
  honcho_dialectic_level: HonchoDialecticLevel | null;
  honcho_dialectic_level_is_override: boolean;
  honcho_peer_name: string | null;
  honcho_peer_name_is_override: boolean;
  honcho_workspace_id: string | null;
  honcho_workspace_id_is_override: boolean;
  honcho_app_id: string | null;
  honcho_app_id_is_override: boolean;
  honcho_session_ttl: number | null;
  honcho_session_ttl_is_override: boolean;
  /** Read-only: Honcho SDK/instance version reported by Honcho's `/health`. */
  honcho_version: string | null;
  /** RFC #1002 PR B: fixed-window write ratelimit for `memory.write`. */
  memory_write_rate_limit_per_hour: number;
  memory_write_rate_limit_per_hour_is_override: boolean;
  /**
   * T-A0b-3/T-A0b-5: schema-driven backend blocks. Optional because an older
   * server (or a test double) may predate the additive field; the UI then
   * falls back to the flat compatibility fields above.
   */
  backends?: Record<string, BackendSettingsBlock>;
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
  honcho_dialectic_level?: HonchoDialecticLevel | null;
  honcho_peer_name?: string | null;
  honcho_workspace_id?: string | null;
  honcho_app_id?: string | null;
  honcho_session_ttl?: number | null;
  /** `null` clears the override so the env default wins; `0` = unlimited. */
  memory_write_rate_limit_per_hour?: number | null;
  /** T-A0b-3: backend-neutral maps (non-secret values / encrypted secrets). */
  backend_options?: Record<string, Record<string, unknown>>;
  backend_secrets?: Record<string, Record<string, string>>;
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
