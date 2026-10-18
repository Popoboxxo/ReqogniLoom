/**
 * Semantic similarity-search hit types (REQ-L2-VS-004).
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { UUID } from "./common";

// ---------------------------------------------------------------------------
// SimilarRequirement (REQ-L2-VS-004 — mirrors SimilarRequirementSerializer)
// ---------------------------------------------------------------------------

export interface SimilarRequirement {
  id: UUID;
  uid?: string | null;
  title: string;
  category: string;
  status: string;
  /** Cosine similarity in [~-1, 1]; higher means more similar. */
  similarity_score: number;
}

/** A single ICD similarity-search hit (REQ-L2-VS-004). */
export interface SimilarIcd {
  icd_id: UUID;
  name: string;
  interface_type: string;
  /**
   * The matched ICD's current contract revision. Backend Task 28c-2 dropped
   * the companion `version_id`: the embedding moved onto the ICD row itself,
   * so there is no version row left to identify.
   */
  version_number: number;
  /** Cosine similarity in [~-1, 1]; higher means more similar. */
  similarity_score: number;
}

/** A single trace-link similarity-search hit (REQ-L2-VS-004). */
export interface SimilarTraceLink {
  id: UUID;
  source_id: UUID;
  target_id: UUID;
  link_type: string;
  /** Cosine similarity in [~-1, 1]; higher means more similar. */
  similarity_score: number;
}
