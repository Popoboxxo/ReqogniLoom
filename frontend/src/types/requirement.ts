/**
 * Requirement, StakeholderNeed and acceptance-criteria types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { CustomFields, ISODateTime, SystemFieldValues, UUID } from "./common";

// ---------------------------------------------------------------------------
// Requirement (mirrors RequirementSerializer)
// ---------------------------------------------------------------------------

/**
 * #344: mirrors the backend `RequirementType` choices
 * (`backend/persistence/models.py`), which are additionally pinned by the DB
 * CHECK constraint added in migration 0050. The previous union
 * (`'SyReq' | 'SWReq' | 'HWReq'`) drifted from the backend: writing SWReq or
 * HWReq was rejected with 400 and the whole edit was discarded.
 */
export type RequirementType = 'SyReq' | 'UseCase' | 'FeatureReq';
export type MoscowPriority = 'Must' | 'Should' | 'Could' | "Won't";
export type VerificationMethod = 'Test' | 'Review' | 'Analysis' | 'Inspection';

/**
 * Issue #394: V-model cascade level (`persistence.models.RequirementLevel`).
 * The number *is* the cascade level: 1=System, 2=Subsystem, 3=Component,
 * 4=Presentation. `null`/`undefined` means the level has not been assigned yet
 * — mirrors the backend field, which is nullable and not backfilled.
 *
 * SYSTEMAUDIT_2026-08-27 P1-9: `0` was dropped along with the backend enum's
 * old off-by-one vocabulary (`0=System .. 4=Material`). L0 is a Stakeholder
 * Need, a separate entity type, never a Requirement — see backend migration
 * `0067_requirement_level_cascade_vocabulary`, which remapped stored rows.
 */
export type RequirementLevel = 1 | 2 | 3 | 4;

// #1288: one structured acceptance criterion. `evidence_ref` is the optional
// uuid of the verifying artifact/test-run set by an external verification tool.
export interface CriteriaItem {
  text: string;
  fulfilled: boolean;
  evidence_ref?: string | null;
}

/** Ordered L1-L4 levels for select inputs; mirrors the backend enum order. */
export const REQUIREMENT_LEVELS: RequirementLevel[] = [1, 2, 3, 4];

export interface StakeholderNeed extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  parent_id?: string;
  artifact_id: UUID;
  title: string;
  description: string;
  category: string;
  status: string;
  version: number;
  uid?: string;
  moscow_priority?: MoscowPriority;
  suspect?: boolean;
  change_reason?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Requirement extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  artifact_id?: UUID;
  parent_id?: string;
  title: string;
  description: string;
  // #871/#583 (IEEE 29148 §5.2.6): justification and origin of the requirement.
  rationale?: string;
  source?: string;
  // #43: acceptance criteria describing when the requirement is fulfilled.
  acceptance_criteria?: string;
  category: string;
  status: string;
  version: number;
  uid?: string;
  type?: RequirementType;
  moscow_priority?: MoscowPriority;
  complexity_fibonacci?: number;
  verification_method?: VerificationMethod;
  // Issue #394: V-model cascade level (1=System ... 4=Presentation). NULL
  // until assigned explicitly. See `RequirementLevel` above.
  level?: RequirementLevel | null;
  // #1289: provenance of `level` — 'derived' (recomputed from the hierarchy)
  // or 'manual' (an explicit override). Lets the UI mark the level as derived.
  level_source?: "derived" | "manual";
  // #1288: structured acceptance criteria (ordered, individually check-off-able).
  acceptance_criteria_items?: CriteriaItem[];
  suspect?: boolean;
  change_reason?: string;
  /** #399: additive baseline-drift summary on the detail retrieve. */
  baseline_drift?: { drifted: boolean; count: number };
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Requirement categories (REQ-L2-RF-001)
// ---------------------------------------------------------------------------

// GESAMTTEST_BERICHT_2026-08-21.md §6/§10.2: "stakeholder" was offered as a
// Requirement category with 0 of 792 real requirements ever using it.
// Investigated rather than assumed: this app already has a dedicated,
// separate L0 artifact type for stakeholder-level content (`StakeholderNeed`,
// its own list/form/route, not a Requirement variant), and CLAUDE.md's own
// canonical requirements-category list (functional/non-functional/API/UI-UX/
// data/integration/test/workflow/baseline/traceability/AI/resilience) never
// includes "stakeholder" either — so this wasn't a legitimate category with
// no data yet, it was a stale/mistaken option that blurred the Need-vs-
// Requirement boundary. Removed (not "genuinely valid, just unused").
export const REQ_CATEGORIES = [
  "functional",
  "non-functional",
  "api",
  "ui-ux",
  "data",
  "integration",
] as const;

export type ReqCategory = typeof REQ_CATEGORIES[number];

/**
 * The same six values as `AttributeOption[]` — the shape the definition-driven
 * form's `EnumSelect` consumes (issue #889).
 *
 * `Requirement.category` is a `CharField(blank=True)` with no Django `choices`,
 * so the introspected attribute definition declares it as free text while the
 * create dialog (`REQ_CATEGORIES`) and the list filter only recognize these
 * values. Deriving the option list from `REQ_CATEGORIES` — rather than writing
 * a second literal — is what keeps create, edit and filter on ONE source.
 * Labels default to the value, exactly as the create dialog renders them.
 */
export const REQ_CATEGORY_OPTIONS: {
  value: string;
  label_de: string;
  label_en: string;
}[] = REQ_CATEGORIES.map((value) => ({
  value,
  label_de: value,
  label_en: value,
}));

// ---------------------------------------------------------------------------
// Requirement Editor Constants (COMP-RF-003)
// ---------------------------------------------------------------------------
//
// GH-453: `WORKFLOW_STATES` used to live here — one Title-Case array that all
// six artifact lists used to build their status filter. It matched no entity's
// actual vocabulary (see backend/workflow/definition_store.py PRESET_SCHEMAS),
// so picking an option produced an empty list. Filter options are now derived
// from the loaded items via `utils/workflowStatus.buildStatusFilterOptions`,
// and display text comes from `getWorkflowStatusLabel`.
