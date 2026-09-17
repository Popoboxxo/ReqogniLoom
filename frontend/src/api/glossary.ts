import { apiClient, getAllPages } from './client';
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
  /**
   * Fetch all glossary terms for a workspace, following pagination links
   * until exhaustion (issue #177 — list() only returned the first page,
   * capped at PAGE_SIZE=25, silently hiding the rest of the glossary).
   */
  list: async (workspaceId: string): Promise<GlossaryTerm[]> => {
    return getAllPages<GlossaryTerm>('/glossary/', { workspace_id: workspaceId });
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
  // Diff / Versions (REQ-142)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Glossary term versions. Signature
   * mirrors `requirementsApi.diff` / `architectureApi.diff` so the
   * DiffPanel can swap fetchers per kind without changing the call site.
   */
  diff: async (id: string, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> => {
    return apiClient.get<ArtifactDiffResult>(
      `/glossary/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /**
   * Version list for a Glossary term, backed by the immutable
   * GlossaryTermVersion history table (REQ-142).
   */
  versions: async (id: string): Promise<ArtifactVersion[]> => {
    return apiClient.get<ArtifactVersion[]>(`/glossary/${id}/versions/`);
  },
};
