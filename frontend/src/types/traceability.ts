/**
 * Trace-link types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { ISODateTime, UUID } from "./common";

// ---------------------------------------------------------------------------
// TraceLink (mirrors TraceLinkSerializer)
// ---------------------------------------------------------------------------

/**
 * A trace-link type key.
 *
 * Deliberately a plain string, not a union: the catalog is tenant- and
 * workspace-configurable, so no compile-time list can be complete. The
 * previous 14-member union was a second, independently maintained source of
 * truth that had already drifted from the backend (audit finding B4).
 * Read the live values from `useLinkTypes()`.
 */
export type LinkType = string;

export interface TraceLink {
  id: UUID;
  source_id: UUID;
  target_id: UUID;
  link_type: string;
  version: number;
  created_at: ISODateTime;
  /** REQ-002: human-readable title of the source artifact (optional, may be absent in legacy responses). */
  source_title?: string;
  /** REQ-002: human-readable title of the target artifact. */
  target_title?: string;
  /** REQ-002: artifact type of the source (e.g. "Requirement", "ArchitectureElement"). */
  source_type?: string;
  /** REQ-002: artifact type of the target. */
  target_type?: string;
  /**
   * UI-P3: the source artifact has been soft-deleted (workflow `outdate()`).
   * TraceLinks deliberately survive the soft-delete of an endpoint so the audit
   * trail stays intact, so such a link is still returned by the API — this flag
   * is the only way to tell it apart from a link to a live artifact.
   * Absent in pre-UI-P3 API responses; treat `undefined` as `false`.
   */
  source_is_outdated?: boolean;
  /** UI-P3: the target artifact has been soft-deleted. See `source_is_outdated`. */
  target_is_outdated?: boolean;
  /** Why this link exists (Q1.6). Empty string when never filled in. */
  rationale?: string;
  /** Set when this link caused the other endpoint to be flagged suspect. */
  suspect_flagged_at?: ISODateTime | null;
  /** `audit.AuditEntry.id` of the change that triggered the flag above. */
  suspect_source_change?: UUID | null;
}
