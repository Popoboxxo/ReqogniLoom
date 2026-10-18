/**
 * Shared domain types for ARCH-L1-001 ReactFrontend.
 *
 * leaf_id: COMP-RF-001..004
 * req_id:  REQ-L2-RF-001..012
 *
 * All types mirror the REST API serializer fields from ARCH-L1-002.
 * Generic API field names are kept as-is; only UI labels change per terminology profile.
 */

import type { GlossaryReferenceMode, SystemFieldValues } from "./common";

export * from "./common";
export * from "./auth";
export * from "./workspace";
export * from "./requirement";
export * from "./architecture";
export * from "./traceability";
export * from "./similarity";
export * from "./testing";
export * from "./artifact";
export * from "./diagram";

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
}

// ---------------------------------------------------------------------------
// Glossary
// ---------------------------------------------------------------------------

export interface GlossaryTerm extends SystemFieldValues {
  id: string;
  workspace_id: string;
  term: string;
  definition: string;
  synonyms: string[];
  abbreviation?: string;
  is_global?: boolean;
  /** Lifecycle/workflow state. #831: exposed under the artifact-consistent
   *  wire key `status` (like Requirement/Adr/Risk/Issue/...). Since the
   *  Datenmodell-Konsolidierung the underlying soft-delete flag lives on the
   *  backing Artifact, but the API field name is `status`. */
  status?: "active" | "outdated" | "deprecated" | "deleted";
  /**
   * UI-59 (Systemaudit 2026-08-27 AP-5): optimistic-lock version counter —
   * mirrors GlossaryTermSerializer.version. Was missing here even though the
   * wire payload always includes it, which forced GlossaryView.tsx to pass
   * `currentVersion={undefined}` into the (otherwise fully wired) shared
   * VersionPanel/DiffPanel, hiding the versions/diff UI that REQ-142 already
   * built for every other artifact kind including "glossary".
   */
  version?: number;
  /**
   * #1266: stable global UUID of the term (== backing Artifact id), the
   * identity a `[[glossary:<uuid>@<revision>]]` reference token pins. Exposed
   * read-only by the backend (`GlossaryTermSerializer.global_uuid`).
   */
  global_uuid?: string;
  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// Glossary references (#1266) — version-bound `[[glossary:<uuid>@<rev>]]`
// tokens embedded in markdown/text fields, resolved by the backend against the
// pinned revision (or the current head in `always_head` mode).
// ---------------------------------------------------------------------------

/** One distinct `(global_uuid, revision)` token resolved against the history. */
export interface GlossaryReferenceResolution {
  global_uuid: string;
  requested_revision: number | null;
  resolved_revision: number;
  head_revision: number;
  term: string;
  definition: string;
  /** False when no term with that global UUID exists (foreign/stale token). */
  resolved: boolean;
  /** True when a pinned revision is behind the term's current head. */
  drift: boolean;
}

export interface GlossaryReferenceResolutionPayload {
  mode: GlossaryReferenceMode;
  has_drift: boolean;
  references: GlossaryReferenceResolution[];
}

export interface GlossaryReferenceInsertResult {
  token: string;
  global_uuid: string;
  term: string;
  definition: string;
  version: number;
  link_type: string;
  mode: GlossaryReferenceMode;
}

export interface GlossaryReferenceUpgradeResult {
  text: string;
  upgraded: number;
}
