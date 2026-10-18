/**
 * Glossary term and version-bound reference types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { GlossaryReferenceMode, SystemFieldValues } from "./common";

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
