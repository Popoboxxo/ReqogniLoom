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
