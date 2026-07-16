/**
 * ARCH-L1-001 ReactFrontend — API barrel export.
 *
 * req_id: REQ-L2-RF-010
 */
export { apiClient, getList, setAuthToken, getAuthToken, setUnauthorizedHandler } from "./client";
export { requirementsApi } from "./requirements";
export { stakeholderNeedApi } from "./stakeholder-need";
export { architectureApi } from "./architecture";
export { tracelinksApi } from "./tracelinks";
export { artifactsApi } from "./artifacts";
export { baselinesApi } from "./baselines";
export type { Baseline } from "./baselines";
export { workspacesApi } from "./workspaces";
export { searchApi } from "./search";
export type { SearchHit, SearchResponse } from "./search";
export { adrsApi } from "./adrs";
export { risksApi } from "./risks";
export { issuesApi } from "./issues";
export { testRunsApi } from "./test-runs";
export { importApi } from "./import";
export type { ImportResult, ImportRowError, EntityType } from "./import";
export { diagramsApi } from "./diagrams";
export type {
  CreateDiagramPayload,
  UpdateDiagramPayload,
} from "./diagrams";
export { icdsApi } from "./icds";
export type {
  Icd,
  IcdDetail,
  IcdTimelineEntry,
  IcdTraceability,
  CreateIcdPayload,
  NewVersionPayload,
} from "./icds";
export { apiKeysApi } from "./api-keys";
export type { ApiKeyMetadata, ApiKeyCreateResult } from "./api-keys";
export { adminOpsApi, RESTORE_CONFIRMATION_TEXT } from "./admin-ops";
export type { BackupMetadata, RestoreResult } from "./admin-ops";
export { versionApi } from "./version";
export type { VersionInfo } from "./version";
export { itemPermissionsApi } from "./item-permissions";
export type { ItemPermission, ItemPermissionLevel } from "./item-permissions";
export { attributeVisibilityApi } from "./attribute-visibility";
export { workflowsApi } from "./workflows";
export type { WorkflowDefinition, WorkflowTransitionResult } from "./workflows";
export { metricsApi } from "./metrics";
export type {
  MetricsResult,
  MetricsQueryOptions,
  MetricType,
  VolatilityMetric,
  TraceabilityCoverageMetric,
  WorkflowGapMetric,
  WorkflowGapItem,
  RiskMetric,
  RiskSeverity,
  ThresholdWarning,
} from "./metrics";

// ---------------------------------------------------------------------------
// Shared types — re-exported from the ArtifactInspector module so callers
// can import the 10-kind union from the central API barrel (UI standards
// §4.0 / §4.5 — DiffPanel and ArtifactDiff use it as the type contract).
// ---------------------------------------------------------------------------
export type { ArtifactKind } from "../components/shared/ArtifactInspector/types";
