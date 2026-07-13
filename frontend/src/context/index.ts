/**
 * ARCH-L1-001 ReactFrontend — Context barrel export.
 *
 * req_id: REQ-L2-RF-007, REQ-L2-RF-008, REQ-L2-RF-010, REQ-L1-084
 */
export { AuthProvider, useAuth } from "./AuthContext";
export type { AuthState } from "./AuthContext";
export { WorkspaceProvider, useWorkspace } from "./WorkspaceContext";
export type { WorkspaceState } from "./WorkspaceContext";
export { EntityTypeProvider, useEntityType, isRequirement, isArchitectureElement, isSysReq, isStReq } from "./EntityTypeContext";
export type { EntityType, EntitySubType, RequirementSubType, ArchitectureSubType, AttributeVisibilityConfig, VisibleFieldsMap, EntityTypeContextValue } from "./EntityTypeContext";
