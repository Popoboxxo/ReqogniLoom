/**
 * Generic artifact and governed artifact types (ADR/Risk/Issue/Goal).
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { CustomFields, ISODateTime, SystemFieldValues, UUID } from "./common";

// ---------------------------------------------------------------------------
// Artifact (mirrors ArtifactSerializer)
// ---------------------------------------------------------------------------

export interface Artifact {
  id: UUID;
  workspace_id: UUID;
  artifact_type: string;
  parent_id: UUID | null;
  custom_fields?: CustomFields;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// ADR (mirrors AdrSerializer, REQ-L1-029)
// ---------------------------------------------------------------------------

export type AdrStatus =
  | "Draft"
  | "In Review"
  | "Approved"
  | "Rejected"
  | "Superseded"
  | "Deleted"; // REQ-006: soft-delete marker; set by backend delete endpoint

export interface Adr extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  // Task 2.1: the backing Artifact id (Adr.artifact, backend/application/models.py)
  // is not yet exposed by AdrSerializer — unlike Requirement/StakeholderNeed/
  // ArchitectureElement, which all serialize a separate `artifact_id`. Declared
  // here (optional, currently always undefined) for parity with the other
  // artifact types. NOTE (Task 27): the workspace-defined custom-field
  // renderer that used to consume this id is gone along with its backend
  // (custom fields are attribute definitions now, tracked gap #7). The field
  // stays declared for the next consumer of the backing Artifact id.
  artifact_id?: UUID;
  title: string;
  description: string;
  context: string;
  consequences: string;
  status: AdrStatus;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Goal / MainGoal (mirror GoalSerializer/MainGoalSerializer, REQ-L2-TE-020)
// ---------------------------------------------------------------------------

/**
 * Goal — lineage-versioned workspace artifact (Variante A: every edit creates
 * a new row sharing the same `lineage_id`).
 */
export interface Goal extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  /** Owning Artifact — the key for workspace custom fields (REQ-016). */
  artifact_id?: UUID;
  lineage_id: UUID;
  sequence_number: number;
  title: string;
  description: string;
  status: string;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/**
 * MainGoal — single workspace-scoped version chain (not lineage-based like
 * Goal). `source` distinguishes an LLM-aggregated draft from a manually
 * authored one; `approve` transitions a draft to `Freigegeben`.
 */
export interface MainGoal {
  id: UUID;
  workspace_id: UUID;
  sequence_number: number;
  content: string;
  source: "ai" | "manual";
  generated_from_goal_ids?: string[];
  status: string;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  /**
   * UI-28 (Systemaudit 2026-08-27 AP-5): only ever `true`/`false` on the
   * response of `POST /main-goals/generate/` — every other MainGoal
   * response omits it (not a persisted field, see MainGoalSerializer).
   */
  is_mock_fallback?: boolean;
}

// ---------------------------------------------------------------------------
// Risk (mirrors RiskSerializer, REQ-L1-029)
// ---------------------------------------------------------------------------

export type RiskProbability = "low" | "medium" | "high";
export type RiskImpact = "low" | "medium" | "high";
export type RiskSeverity = "low" | "medium" | "high";
export type RiskCategory = "technical" | "operational" | "organizational" | "business";
export type RiskStatus = "Identified" | "Monitored" | "Mitigated" | "Accepted" | "Closed";

export interface Risk {
  id: UUID;
  workspace_id: UUID;
  // Task 2.2: same as Adr.artifact_id above — the backing Artifact id is not
  // yet exposed by RiskSerializer. Declared here (optional, currently always
  // undefined) for parity with the other artifact types.
  artifact_id?: UUID;
  title: string;
  description: string;
  probability: RiskProbability;
  impact: RiskImpact;
  risk_score: number;
  /**
   * UI-39 (Systemaudit 2026-08-27 AP-5): FMEA detectability score
   * (1=easy to detect .. 10=impossible), mirrors RiskSerializer.detection.
   */
  detection?: number;
  /**
   * UI-39: Risk Priority Number (probability × impact × detection),
   * read-only computed property (RiskSerializer.rpn).
   */
  rpn?: number;
  severity: RiskSeverity;
  category: RiskCategory;
  owner: string;
  /**
   * REQ-L1-029 (FMEA): structured User FK for risk assignment, mirrors
   * RiskSerializer.owner_user_id (kept alongside the legacy free-text
   * `owner` field). Task 19: the attribute-definition bootstrap serves this
   * under the same name (see bootstrap_attribute_definitions.py's
   * WIDGET_FIELD_ALIASES — the raw Django FK field is named `owner_user`,
   * aliased to match this serializer field).
   */
  owner_user_id?: UUID | null;
  /** Read-only display label for `owner_user_id` (RiskSerializer.owner_user_display). */
  owner_user_display?: string | null;
  mitigation_strategy: string;
  status: RiskStatus;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Issue (mirrors IssueSerializer, REQ-L1-029)
// ---------------------------------------------------------------------------

export type IssueSeverity = "critical" | "high" | "medium" | "low";
export type IssueCategory = "defect" | "improvement" | "documentation" | "question";
export type IssueStatus = "Open" | "In Progress" | "Resolved" | "Closed" | "Wontfix";

export interface Issue extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  // Task 2.3: same as Adr.artifact_id / Risk.artifact_id above — the backing
  // Artifact id is not yet exposed by IssueSerializer. Declared here
  // (optional, currently always undefined) for parity with the other
  // artifact types.
  artifact_id?: UUID;
  title: string;
  description: string;
  severity: IssueSeverity;
  category: IssueCategory;
  status: IssueStatus;
  tags: string[];
  /**
   * Task 20 finding: `IssueSerializer` never declared this field at all
   * (mirrors Task 19's `owner_user_id` finding on Risk) even though
   * `IssueService.create_issue`/`update_issue` both already accept and
   * persist it — via REST, every save silently discarded it and every read
   * came back empty (the MCP generic tool group was unaffected: it forwards
   * arbitrary params straight to the service, bypassing this serializer).
   * Fixed at the serializer/view layer alongside this migration.
   */
  due_date?: ISODateTime | null;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
