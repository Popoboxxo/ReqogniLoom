/**
 * Shared domain types for ARCH-L1-001 ReactFrontend.
 *
 * leaf_id: COMP-RF-001..004
 * req_id:  REQ-L2-RF-001..012
 *
 * All types mirror the REST API serializer fields from ARCH-L1-002.
 * Generic API field names are kept as-is; only UI labels change per terminology profile.
 */

export * from "./common";
export * from "./auth";
export * from "./workspace";
export * from "./requirement";
export * from "./architecture";
export * from "./traceability";
export * from "./similarity";
export * from "./testing";
export * from "./artifact";
export * from "./diagram";
export * from "./diff";
export * from "./glossary";
