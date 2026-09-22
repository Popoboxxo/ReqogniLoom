/**
 * ARCH-L1-001 ReactFrontend — TestCases API (A.6, REQ-L1-035).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-035
 *
 * Wraps /api/v1/testcases/ endpoints. Used by the RequirementEditors
 * ``otherRequirements`` dropdown (test cases + requirements share the
 * TraceLink target slot) and by the TestRuns detail view (verifies-chain
 * title resolution).
 */

import { apiClient, getAllPages, getList } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  CustomFields,
  ISODateTime,
  PaginatedResponse,
  UUID,
} from "../types";

/**
 * SysEng 2.0 N5 (test.derive_from_requirement): a single TestCase step, as
 * persisted in the backend TestCase.steps JSONField and produced by the AI
 * derivation draft.
 */
export interface TestCaseStep {
  step: string;
  expected_result: string;
}

/**
 * Real `TestCase.test_type` model column (#864, B6a) — mirrors
 * `persistence/models.py::TestCaseType` (lowercase wire values). Distinct from
 * the legacy Title-case `artifact_type` tag handled by the MCP/legacy service
 * path.
 */
export type TestCaseType =
  | "system"
  | "integration"
  | "unit"
  | "inspection"
  | "analysis"
  | "demonstration";

/**
 * #424: provenance of a TestCase's content — mirror of
 * `persistence/models.py::TestCaseOrigin`.
 *
 * `ai_generated` + `reviewed === false` is exactly the pair the coverage
 * calculator excludes from verification evidence. `unknown` is system/
 * migration-owned (legacy rows) and is deliberately NOT client-writable
 * (spec section 4.4: serializer choices are `{manual, ai_generated}`).
 */
export type TestCaseOrigin = "manual" | "ai_generated" | "unknown";

/** #402: off-nominal classification — mirror of `ScenarioKind`. */
export type ScenarioKind = "nominal" | "off_nominal";

/**
 * #399: additive drift summary that `TestCaseViewSet.retrieve` (and the
 * Requirement retrieve) attach to their responses — `{drifted, count}`.
 * The full per-baseline detail lives behind
 * `GET /api/v1/artifacts/{id}/baseline-membership/` (`artifactsApi.
 * baselineMembership`), which the editor header calls once per open artifact.
 */
export interface BaselineDriftSummary {
  drifted: boolean;
  count: number;
}

/** Mirror of the backend TestCaseSerializer (REQ-L2-RA-001). */
export interface TestCase {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  status: string;
  steps?: TestCaseStep[];
  /** #864: real `TestCase.test_type` column; `null` when not set. */
  test_type?: TestCaseType | null;
  /**
   * #424: content provenance. Absent on responses from a backend older than
   * cluster 5 — treat `undefined` as "not asserted", never as `manual`.
   */
  origin?: TestCaseOrigin;
  /**
   * #424: human content sign-off, derived server-side from `origin` at create
   * time (`manual` → `true`, `ai_generated` → `false`) and toggled only
   * through `POST /testcases/{id}/review/`. Read-only in the serializer.
   */
  reviewed?: boolean;
  /** #402: nominal (default) or off-nominal scenario category. */
  scenario_kind?: ScenarioKind;
  /** #399: additive baseline-drift summary on the detail retrieve. */
  baseline_drift?: BaselineDriftSummary;
  version: number;
  uid?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export const testcasesApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<TestCase>> {
    return getList<TestCase>("/testcases/", { workspace_id: workspaceId });
  },

  /**
   * Fetch all TestCases for a workspace, following pagination links until
   * exhaustion (issue C — list() only returned the first page, capped at
   * PAGE_SIZE=25).
   */
  async listAll(workspaceId: UUID): Promise<TestCase[]> {
    return getAllPages<TestCase>("/testcases/", { workspace_id: workspaceId });
  },

  get(id: UUID): Promise<TestCase> {
    return apiClient.get<TestCase>(`/testcases/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    status?: string;
    /** SysEng 2.0 N5: test steps (e.g. from an accepted AI derivation draft). */
    steps?: TestCaseStep[];
    /**
     * #864: real `TestCase.test_type` column (lowercase enum values) — the
     * create contract now accepts it. Omit to leave the column NULL.
     */
    test_type?: TestCaseType;
    /**
     * #424: provenance the interactive client declares for the new row.
     * `ai_generated` is what the AI derivation panel sends; omit for a
     * human-authored test case (server default `manual`). `unknown` is not a
     * valid client value.
     */
    origin?: Exclude<TestCaseOrigin, "unknown">;
    /** #402: nominal (default) or off-nominal classification. */
    scenario_kind?: ScenarioKind;
    /** SysEng 2.0 N5: optional requirement to auto-link via a 'verifies' TraceLink. */
    linked_requirement_id?: UUID;
  }): Promise<TestCase> {
    return apiClient.post<TestCase>("/testcases/", data);
  },

  /**
   * #424: set the human content sign-off via
   * `POST /api/v1/testcases/{id}/review/`. Idempotent server-side; `reviewed`
   * defaults to `true`. The response is the full updated TestCase.
   */
  review(
    id: UUID,
    data: { reviewed?: boolean; change_reason?: string } = {}
  ): Promise<TestCase> {
    return apiClient.post<TestCase>(`/testcases/${id}/review/`, data);
  },

  /**
   * Task 22: widened to `Record<string, unknown>` (same deviation as
   * `risksApi.update`/`issuesApi.update`, Tasks 19/20) so the definition-
   * driven `TestCaseArtifactForm` can PATCH whatever the resolved attribute
   * definition exposes (e.g. `test_type`, `steps`) without this type lagging
   * behind it. The former `change_reason` field is dropped: verified live
   * that `TestCaseSerializer` never declared it and `TestCaseViewSet.
   * partial_update` never reads it — the deleted `TestCaseForm.tsx` sent a
   * value the backend silently discarded (see `TestCaseArtifactForm.tsx`'s
   * docstring for the full trace).
   */
  update(id: UUID, data: Record<string, unknown>): Promise<TestCase> {
    return apiClient.patch<TestCase>(`/testcases/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/testcases/${id}/`);
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/testcases/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two TestCase versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/testcases/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for a TestCase. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/testcases/${id}/versions/`);
  },
};
