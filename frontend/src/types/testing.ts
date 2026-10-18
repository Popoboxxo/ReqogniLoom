/**
 * TestCase and TestRun types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { CustomFields, ISODateTime, SystemFieldValues, UUID } from "./common";

// ---------------------------------------------------------------------------
// TestCase (mirrors TestCaseSerializer)
// ---------------------------------------------------------------------------

export interface TestCase extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  /**
   * #399 (MAJOR-1): the backing Artifact id, distinct from the TestCase pk —
   * the baseline-membership endpoint and `affected_item_ids` prefill key on
   * Artifact ids, never on the entity pk.
   */
  artifact_id?: UUID;
  title: string;
  description: string;
  status: string;
  suspect?: boolean;
  /** #424: content provenance (`manual` | `ai_generated` | `unknown`). */
  origin?: "manual" | "ai_generated" | "unknown";
  /** #424: human content sign-off — only toggled via the review endpoint. */
  reviewed?: boolean;
  /** #402: `nominal` (default) or `off_nominal`. */
  scenario_kind?: "nominal" | "off_nominal";
  /** #399: additive baseline-drift summary on the detail retrieve. */
  baseline_drift?: { drifted: boolean; count: number };
  version: number;
  uid?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// TestRun (REQ-L2-AS-030)
// ---------------------------------------------------------------------------

export interface TestRunResult {
  id: UUID;
  test_run_id: UUID;
  test_case_id: UUID | null;
  test_case_title: string;
  status: "passed" | "failed" | "blocked" | "not_run";
  message: string;
  duration_ms: number | null;
  executed_at: ISODateTime | null;
  created_at: ISODateTime;
}

export interface TestRunResultSummary {
  total: number;
  passed: number;
  failed: number;
  blocked: number;
  not_run: number;
}

export interface TestRun {
  id: UUID;
  workspace_id: UUID;
  name: string;
  status: "in_progress" | "passed" | "failed" | "partial" | "closed";
  ci_job_id: string;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  result_summary: TestRunResultSummary;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
