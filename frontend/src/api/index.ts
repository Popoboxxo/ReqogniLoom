/**
 * ARCH-L1-001 ReactFrontend — API barrel export.
 *
 * req_id: REQ-L2-RF-010
 */
export {
  apiClient,
  getList,
  setUnauthorizedHandler,
  resetUnauthorizedGuard,
} from "./client";
export { requirementsApi } from "./requirements";
export { groupsApi, loadGroupsWithMembers } from "./groups";
export type {
  RequirementGroup,
  GroupMember,
  GroupWithMembers,
} from "./groups";
export { stakeholderNeedApi } from "./stakeholder-need";
export { architectureApi } from "./architecture";
export { tracelinksApi } from "./tracelinks";
export { artifactsApi } from "./artifacts";
export { baselinesApi } from "./baselines";
export type { Baseline } from "./baselines";
export { changeRequestsApi } from "./change-requests";
export type {
  ChangeRequest,
  CreateChangeRequestPayload,
} from "./change-requests";
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
export type {
  BackupMetadata,
  RestoreResult,
  SystemHealthStatus,
  SystemHealthComponent,
  SystemHealthAuditEvent,
  SystemHealthSnapshot,
} from "./admin-ops";
export { versionApi } from "./version";
export type { VersionInfo } from "./version";
export { itemPermissionsApi } from "./item-permissions";
export type { ItemPermission, ItemPermissionLevel } from "./item-permissions";
export { workflowsApi } from "./workflows";
export type {
  WorkflowDefinition,
  WorkflowDefinitionTransitionResult,
  WorkflowPresetKey,
} from "./workflows";
// P2.3: one canonical item-transition result. `WorkflowTransitionResult` is the
// `/{resource}/{id}/transitions/` payload every artifact type shares (state
// change + optional entity revision); its base type lives in the type layer.
// The workspace-*definition* PATCH re-exported above stays a separate name
// (`WorkflowDefinitionTransitionResult`, `{id, target_state}`) — never the same
// symbol twice in this barrel.
export type {
  WorkflowTransitionResult,
} from "./workflow-transitions";
export type { WorkflowTransitionStateChange } from "../types/workflow";
// P1.8 (M-12): the tenant-wide, per-(item_type, preset) global workflow
// defaults live next to the workspace-scoped workflowsApi so callers never
// need a deep import into ./workflow-defaults.
export { workflowDefaultsApi } from "./workflow-defaults";
export type {
  GlobalWorkflowDefinitionGraph,
  GlobalWorkflowMutationResult,
} from "./workflow-defaults";
export { auditApi } from "./audit";
export type {
  AuditScopeKind,
  AuditSeverity,
  AuditFinding,
  AuditCounts,
  AuditReport,
  RemediationProposal,
  RemediationActionKind,
  RemediateRequest,
  RemediateResult,
  RunAuditOptions,
  WaiverState,
  WaiverLifecycle,
  SuppressionView,
  WaiverListResponse,
  WaiveRequest,
} from "./audit";
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
  // Issue #1265 — central statistics registry + values-by-keys
  MetricCatalog,
  MetricCatalogEntry,
  MetricValues,
  MetricValueEntry,
  MetricScope,
  MetricValuesQueryOptions,
} from "./metrics";

export { attributeDefinitionsApi } from "./attribute-definitions";
export { attributeCatalogApi } from "./attributeCatalog";
export type {
  AddToDefinitionInput,
  AddToDefinitionResult,
  AttributeCatalogDocument,
  AttributeCatalogEntry,
  CatalogEntryInput,
  CatalogEntryDocument,
  CatalogImportResult,
  CatalogListFilters,
  CatalogLocalizedText,
} from "./attributeCatalog";
export type {
  AttributeSpec,
  AttributeType,
  AttributeEditable,
  AttributeAudience,
  AttributeOption,
  GlobalAttributeDefinition,
  ResolvedAttributeDefinition,
  WidgetKey,
} from "./attribute-definitions";

// ---------------------------------------------------------------------------
// Shared types — re-exported from the ArtifactInspector module so callers
// can import the 10-kind union from the central API barrel (UI standards
// §4.0 / §4.5 — DiffPanel and ArtifactDiff use it as the type contract).
// ---------------------------------------------------------------------------
export type { ArtifactKind } from "../components/shared/ArtifactInspector/types";

// ---------------------------------------------------------------------------
// Menschen-im-System spec §4/§5 — artifact comments and the notification feed.
// ---------------------------------------------------------------------------
export { commentsApi } from "./comments";
export type { Comment, ListCommentsOptions } from "./comments";
// Issue #1792 (S2): the on-demand AI summary behind the inspector's Summary tab.
// Issue #1793 (S8): the stored per-type stands the overview block reads.
export {
  fetchArtifactSummary,
  fetchTypeSummary,
  fetchWorkspaceSummaries,
  refreshTypeSummary,
  SUMMARY_DEGRADED_REASONS,
} from "./artifact-summary";
export type {
  ArtifactSummary,
  FetchArtifactSummaryOptions,
  RefreshedTypeSummary,
  StoredSummary,
  SummaryDegradedReason,
  WorkspaceSummaryList,
} from "./artifact-summary";
export { NOTIFICATION_FEED_LIMIT, notificationsApi } from "./notifications";
export type { Notification, NotificationFeed, NotificationKind } from "./notifications";
