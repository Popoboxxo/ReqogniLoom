/**
 * ArchitectureElement (MBSE) types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { CustomFields, ISODateTime, SystemFieldValues, UUID } from "./common";

// ---------------------------------------------------------------------------
// ArchitectureElement (mirrors ArchitectureElementSerializer)
// ---------------------------------------------------------------------------

export type ElementType =
  | "component"
  | "interface"
  | "subsystem"
  | "layer"
  | "module";

/**
 * Structural role derived from the element's position in the decomposition tree
 * (SysEng 2.0 §1.2). Computed by the backend, read-only — never sent on write.
 * root → "system", inner node → "subsystem", leaf → "component".
 */
export type ArchitectureRole = "system" | "subsystem" | "component";

export type ASILLevel = "QM" | "A" | "B" | "C" | "D" | null;

export type MakeOrBuyDecision = "Make" | "Buy" | "Reuse" | null;

export interface ArchitectureElement extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  /** Owning Artifact — the key for workspace custom fields (REQ-016). */
  artifact_id?: UUID;
  title: string;
  description: string;
  element_type: ElementType;
  parent_id?: UUID | null;
  level?: number;
  /** SysEng 2.0 §1.2: derived structural role (read-only, computed from tree position). */
  role?: ArchitectureRole;
  version: number;
  uid?: string | null;
  asil_level?: ASILLevel;
  make_or_buy?: MakeOrBuyDecision;
  suspect?: boolean;
  change_reason?: string;
  custom_fields?: CustomFields;
  /** Soft-delete flag. Since the Datenmodell-Konsolidierung it lives on the
   *  backing Artifact and is orthogonal to `status` (the workflow state). */
  lifecycle_status?: "active" | "outdated" | "deprecated" | "deleted";
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
