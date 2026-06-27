/**
 * ARCH-L1-001 ReactFrontend — API barrel export.
 *
 * req_id: REQ-L2-RF-010
 */
export { apiClient, getList, setAuthToken, getAuthToken, setUnauthorizedHandler } from "./client";
export { requirementsApi } from "./requirements";
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
