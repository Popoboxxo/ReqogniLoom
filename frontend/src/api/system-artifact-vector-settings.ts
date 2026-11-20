/**
 * Artifact vector store settings API (ADR-020 extension).
 *
 * Wraps /api/v1/system/artifact-vector-settings/ (GET/PUT) and its /reset/
 * POST. The read side is System-Admin; writes need a Django superuser, matching
 * the deployment-global memory-settings endpoint. Secrets are write-only: the
 * API only reports `secrets_set`.
 */

import { apiClient } from "./client";
import type { BackendSettingField, BackendSettingsBlock } from "./system-memory-settings";

export type { BackendSettingField, BackendSettingsBlock };

/** Read-only selection diagnostic (mirrors `vector_backend_diagnostic()`). */
export interface ArtifactVectorDiagnostic {
  requested: string;
  active: string;
  /**
   * Stable, machine-readable gate token (`""` when honoured):
   * `unknown_artifact_vector_backend`, `qdrant_client_missing`,
   * `qdrant_config_error` or `qdrant_base_url_missing`.
   */
  reason: string;
}

export interface ArtifactVectorSettings {
  /** Stored selector override; `null` means "the env var wins". */
  vector_backend: string | null;
  vector_backend_is_override: boolean;
  /** Resolved backend (override > env > pgvector). */
  effective_vector_backend: string;
  available_backends: string[];
  backends: Record<string, BackendSettingsBlock>;
  diagnostic: ArtifactVectorDiagnostic;
}

export interface ArtifactVectorSettingsUpdate {
  /** `null` clears the override so the env var wins again. */
  vector_backend?: string | null;
  backend_options?: Record<string, Record<string, unknown>>;
  backend_secrets?: Record<string, Record<string, string>>;
}

export const artifactVectorSettingsApi = {
  async get(): Promise<ArtifactVectorSettings> {
    return apiClient.get<ArtifactVectorSettings>("/system/artifact-vector-settings/");
  },
  async update(payload: ArtifactVectorSettingsUpdate): Promise<ArtifactVectorSettings> {
    return apiClient.put<ArtifactVectorSettings>(
      "/system/artifact-vector-settings/",
      payload
    );
  },
  async reset(): Promise<ArtifactVectorSettings> {
    return apiClient.post<ArtifactVectorSettings>(
      "/system/artifact-vector-settings/reset/",
      {}
    );
  },
};
