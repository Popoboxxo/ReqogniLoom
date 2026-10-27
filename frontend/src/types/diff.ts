/**
 * Artifact diff / version types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

// ---------------------------------------------------------------------------
// ArtifactDiff (REQ-L2-RF-014, COMP-AS-019)
// ---------------------------------------------------------------------------

export type DiffFieldStatus = "added" | "removed" | "modified" | "unchanged";

export interface DiffField {
  name: string;
  status: DiffFieldStatus;
  from?: string;
  to?: string;
  lines?: string[];
}

export interface ArtifactDiffResult {
  from_version: number;
  to_version: number;
  entity_type: string;
  fields: DiffField[];
  note?: string;
}

export interface ArtifactVersion {
  /**
   * Addressing token for `/diff/` and baseline pinning. For single-row
   * artifact types this is the backend's optimistic-lock counter, NOT a
   * revision number — it also increments on writes that change nothing
   * user-visible (issue #213).
   */
  version: number;
  label: string;
  modified_at?: string | null;
  /**
   * Whether a retrievable snapshot is stored for this version. `false` for
   * the empty creation baseline and for historical lock-counter values of
   * single-row types. Older backends omit the flag; treat that as `true`.
   */
  content_available?: boolean;
  /**
   * True for the synthetic, empty "creation baseline" row (version 0) the
   * backend prepends to every version list (issue #272). Its `label` is an
   * English API field, so the UI localises the row from this flag instead of
   * comparing that string. Older backends omit it; treat that as `false`.
   */
  is_creation_baseline?: boolean;
}
