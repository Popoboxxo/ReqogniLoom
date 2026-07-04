import { api } from './client';
import type { GlossaryTerm } from '../types';

export interface GlossaryTermPayload {
  workspace_id: string;
  term: string;
  definition: string;
  synonyms?: string[];
  abbreviation?: string;
}

export const glossaryApi = {
  list: async (workspaceId: string): Promise<GlossaryTerm[]> => {
    const response = await api.get<{ results: GlossaryTerm[] }>(`/glossary/?workspace_id=${workspaceId}`);
    return response.data.results;
  },

  get: async (id: string): Promise<GlossaryTerm> => {
    const response = await api.get<GlossaryTerm>(`/glossary/${id}/`);
    return response.data;
  },

  create: async (payload: GlossaryTermPayload): Promise<GlossaryTerm> => {
    const response = await api.post<GlossaryTerm>('/glossary/', payload);
    return response.data;
  },

  update: async (id: string, payload: Partial<GlossaryTermPayload>): Promise<GlossaryTerm> => {
    const response = await api.patch<GlossaryTerm>(`/glossary/${id}/`, payload);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/glossary/${id}/`);
  },
};
