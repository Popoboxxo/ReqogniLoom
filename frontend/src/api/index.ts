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
