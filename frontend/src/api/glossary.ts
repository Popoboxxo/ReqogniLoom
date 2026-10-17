import { apiClient, getAllPages } from './client';
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  GlossaryReferenceInsertResult,
  GlossaryReferenceResolutionPayload,
  GlossaryReferenceUpgradeResult,
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

  // -----------------------------------------------------------------------
  // Version-bound references (#1266)
  // -----------------------------------------------------------------------

  /**
   * Resolve every `[[glossary:<uuid>@<rev>]]` token in `text` against the
   * pinned revision (or the current head in `always_head` mode). Returns the
   * workspace mode, a drift summary and one entry per distinct token.
   */
  resolveReferences: async (
    workspaceId: string,
    text: string
  ): Promise<GlossaryReferenceResolutionPayload> => {
    return apiClient.post<GlossaryReferenceResolutionPayload>(
      '/glossary/references/resolve/',
      { workspace_id: workspaceId, text }
    );
  },

  /**
   * Insert a glossary reference for `sourceArtifactId`: creates the usage
   * trace link (`uses-term`/`references`) and returns the token text to embed,
   * pinned to the term's current revision unless the workspace is in
   * `always_head` mode.
   */
  insertReference: async (
    workspaceId: string,
    sourceArtifactId: string,
    globalUuid: string
  ): Promise<GlossaryReferenceInsertResult> => {
    return apiClient.post<GlossaryReferenceInsertResult>(
      '/glossary/references/insert/',
      {
        workspace_id: workspaceId,
        source_artifact_id: sourceArtifactId,
        global_uuid: globalUuid,
      }
    );
  },

  /**
   * Rewrite every drifted version pin in `text` to the term's current head —
   * the "raise the version" bulk action for a single field.
   */
  upgradeReferencesToHead: async (
    workspaceId: string,
    text: string
  ): Promise<GlossaryReferenceUpgradeResult> => {
    return apiClient.post<GlossaryReferenceUpgradeResult>(
      '/glossary/references/upgrade-to-head/',
      { workspace_id: workspaceId, text }
    );
  },

  // -----------------------------------------------------------------------
  // AI glossary derivation (#1358 REST parity / #1360 UI entry)
  // -----------------------------------------------------------------------

  /**
   * POST /api/v1/glossary/derive/ (`mode="preview"`, the default): AI term
   * drafts for the workspace. `ephemeral: true` — nothing is persisted.
   */
  derivePreview: async (workspaceId: string): Promise<GlossaryDerivePreview> => {
    return apiClient.post<GlossaryDerivePreview>('/glossary/derive/', {
      workspace_id: workspaceId,
    });
  },

  /**
   * POST /api/v1/glossary/derive/ (`mode="write"`): the canonical persistence
   * path (W12a) — persists the derivation through the same Layer-2 seam the
   * MCP tool uses, born `proposed` where the workflow supports it (#1089).
   */
  deriveWrite: async (workspaceId: string): Promise<GlossaryDeriveReceipt> => {
    return apiClient.post<GlossaryDeriveReceipt>('/glossary/derive/', {
      workspace_id: workspaceId,
      mode: 'write',
    });
  },
};

/** One draft of `POST /glossary/derive/` (`mode="preview"`). */
export interface GlossaryDeriveDraft {
  term: string;
  definition: string;
  synonyms?: string[];
  abbreviation?: string;
}

export interface GlossaryDerivePreview {
  drafts: GlossaryDeriveDraft[];
  workspace_id: string;
  /** #1358: the preview persists nothing — stated on the wire. */
  ephemeral?: boolean;
  is_mock_fallback?: boolean;
}

/** One persisted term of the `mode="write"` receipt. */
export interface GlossaryDeriveWrittenEntry {
  id: string;
  status: string;
  proposal: { is_proposal: boolean; reason?: string };
}

export interface GlossaryDeriveReceipt {
  written: GlossaryDeriveWrittenEntry[];
  is_mock_fallback?: boolean;
  failed?: Array<{ draft?: unknown; error: string }>;
}
