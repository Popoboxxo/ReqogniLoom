import { apiClient, getList } from './client';
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  GlossaryTerm,
} from '../types';

export interface GlossaryTermPayload {
  workspace_id: string;
  term: string;
  definition: string;
  synonyms?: string[];
  abbreviation?: string;
}

export const glossaryApi = {
  list: async (workspaceId: string): Promise<GlossaryTerm[]> => {
    const response = await getList<GlossaryTerm>('/glossary/', { workspace_id: workspaceId });
    return response.results;
  },

  get: async (id: string): Promise<GlossaryTerm> => {
    return apiClient.get<GlossaryTerm>(`/glossary/${id}/`);
  },

  create: async (payload: GlossaryTermPayload): Promise<GlossaryTerm> => {
    return apiClient.post<GlossaryTerm>('/glossary/', payload);
  },

  update: async (id: string, payload: Partial<GlossaryTermPayload>): Promise<GlossaryTerm> => {
    return apiClient.patch<GlossaryTerm>(`/glossary/${id}/`, payload);
  },

  delete: async (id: string): Promise<void> => {
    return apiClient.delete(`/glossary/${id}/`);
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — stubs (UI standards §4.5 / §11 Backend gaps)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Glossary term versions. Signature
   * mirrors `requirementsApi.diff` / `architectureApi.diff` so the
   * DiffPanel can swap fetchers per kind without changing the call site.
   * TODO(backend): wire to GET /api/v1/glossary/{id}/diff/ (not exposed yet).
   */
  diff: async (id: string, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> => {
    return Promise.reject(
      new Error(
        `Not Implemented: Glossary /diff/ endpoint for ${id} (from v${fromVersion} to v${toVersion}) — see UI standards §11.`
      )
    );
  },

  /**
   * Version list for a Glossary term. The backend does not expose a
   * `/versions/` endpoint for Glossary terms. DiffPanel will short-circuit
   * to its empty state for Glossary in the meantime.
   * TODO(backend): wire to GET /api/v1/glossary/{id}/versions/.
   */
  versions: async (id: string): Promise<ArtifactVersion[]> => {
    return Promise.reject(
      new Error(
        `Not Implemented: Glossary /versions/ endpoint for ${id} — see UI standards §11.`
      )
    );
  },
};
