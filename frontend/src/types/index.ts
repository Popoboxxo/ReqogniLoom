/**
 * Shared domain types for ARCH-L1-001 ReactFrontend.
 *
 * leaf_id: COMP-RF-001..004
 * req_id:  REQ-L2-RF-001..012
 *
 * All types mirror the REST API serializer fields from ARCH-L1-002.
 * Generic API field names are kept as-is; only UI labels change per terminology profile.
 */

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

export type UUID = string;
export type ISODateTime = string;

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface User {
  id: UUID;
  username: string;
  email: string;
  is_staff: boolean;
}

// ---------------------------------------------------------------------------
// Workspace (not yet in backend API — see ESCALATION notes)
// ---------------------------------------------------------------------------

export type WorkspacePreset = "minimal" | "standard" | "extended";
export type TerminologyProfile = "dev_mode" | "se_mode";

export interface Workspace {
  id: UUID;
  name: string;
  preset: WorkspacePreset;
  terminology_profile: TerminologyProfile;
  language: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface WorkspaceWithMetrics extends Workspace {
  requirement_count: number;
  open_item_count: number;
}

// ---------------------------------------------------------------------------
// Requirement (mirrors RequirementSerializer)
// ---------------------------------------------------------------------------

export interface Requirement {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  category: string;
  status: string;
  version: number;
  change_reason?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// ArchitectureElement (mirrors ArchitectureElementSerializer)
// ---------------------------------------------------------------------------

export type ElementType =
  | "component"
  | "interface"
  | "subsystem"
  | "layer"
  | "module";

export interface ArchitectureElement {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  element_type: string;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// TraceLink (mirrors TraceLinkSerializer)
// ---------------------------------------------------------------------------

export type LinkType =
  | "parent-child"
  | "derives-from"
  | "satisfies"
  | "verifies"
  | "implements"
  | "refines";

export interface TraceLink {
  id: UUID;
  source_id: UUID;
  target_id: UUID;
  link_type: string;
  version: number;
  created_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Artifact (mirrors ArtifactSerializer)
// ---------------------------------------------------------------------------

export interface Artifact {
  id: UUID;
  workspace_id: UUID;
  artifact_type: string;
  parent_id: UUID | null;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Paginated response (mirrors StandardPagination format)
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---------------------------------------------------------------------------
// API error format (mirrors build_error_response)
// ---------------------------------------------------------------------------

export interface ApiErrorDetail {
  field?: string;
  errors?: string[];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details: ApiErrorDetail[];
  };
}

// ---------------------------------------------------------------------------
// Preset visibility rules (REQ-L2-RF-007)
// ---------------------------------------------------------------------------

export const PRESET_VISIBILITY: Record<WorkspacePreset, Record<string, boolean>> = {
  minimal: {
    baselines: false,
    global_baselines: false,
    workflow_config: false,
    approver_ui: false,
    architecture: true,
    requirements: true,
    traceability: true,
    dashboard: true,
  },
  standard: {
    baselines: true,
    global_baselines: false,
    workflow_config: true,
    approver_ui: false,
    architecture: true,
    requirements: true,
    traceability: true,
    dashboard: true,
  },
  extended: {
    baselines: true,
    global_baselines: true,
    workflow_config: true,
    approver_ui: true,
    architecture: true,
    requirements: true,
    traceability: true,
    dashboard: true,
  },
};

// ---------------------------------------------------------------------------
// Terminology profile label maps (REQ-L2-RF-008)
// ---------------------------------------------------------------------------

export type TerminologyLabels = {
  requirement: string;
  requirements: string;
  epic: string;
  story: string;
  task: string;
  system: string;
  subsystem: string;
  component: string;
};

export const TERMINOLOGY_LABELS: Record<TerminologyProfile, TerminologyLabels> = {
  dev_mode: {
    requirement: "Story",
    requirements: "Stories",
    epic: "Epic",
    story: "Story",
    task: "Task",
    system: "System",
    subsystem: "Module",
    component: "Component",
  },
  se_mode: {
    requirement: "Requirement",
    requirements: "Requirements",
    epic: "System",
    story: "Subsystem",
    task: "Component",
    system: "System",
    subsystem: "Subsystem",
    component: "Component",
  },
};
