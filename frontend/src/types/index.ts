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
  ai_prompts?: Record<string, string>;
  decomposition_link_type?: string;
  is_active: boolean;
  closed_at: ISODateTime | null;
  closed_by: UUID | null;
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

// ---------------------------------------------------------------------------
// Custom Fields (REQ-L2-AS-037) — user-defined flat key-value attributes,
// stored on the shared Artifact and exposed on every artifact-backed entity.
// ---------------------------------------------------------------------------

export type CustomFieldValue = string | number | boolean | null;

export type CustomFields = Record<string, CustomFieldValue>;

export type RequirementType = 'SyReq' | 'SWReq' | 'HWReq';
export type MoscowPriority = 'Must' | 'Should' | 'Could' | "Won't";
export type VerificationMethod = 'Test' | 'Review' | 'Analysis' | 'Inspection';

export interface StakeholderNeed {
  id: UUID;
  workspace_id: UUID;
  parent_id?: string;
  artifact_id: UUID;
  title: string;
  description: string;
  category: string;
  status: string;
  version: number;
  uid?: string;
  moscow_priority?: MoscowPriority;
  suspect?: boolean;
  change_reason?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Requirement {
  id: UUID;
  workspace_id: UUID;
  parent_id?: string;
  title: string;
  description: string;
  category: string;
  status: string;
  version: number;
  uid?: string;
  type?: RequirementType;
  moscow_priority?: MoscowPriority;
  complexity_fibonacci?: number;
  verification_method?: VerificationMethod;
  suspect?: boolean;
  change_reason?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// SimilarRequirement (REQ-L2-VS-004 — mirrors SimilarRequirementSerializer)
// ---------------------------------------------------------------------------

export interface SimilarRequirement {
  id: UUID;
  uid?: string | null;
  title: string;
  category: string;
  status: string;
  /** Cosine similarity in [~-1, 1]; higher means more similar. */
  similarity_score: number;
}

/** A single ICD similarity-search hit (REQ-L2-VS-004). */
export interface SimilarIcd {
  icd_id: UUID;
  version_id: UUID;
  name: string;
  interface_type: string;
  version_number: number;
  /** Cosine similarity in [~-1, 1]; higher means more similar. */
  similarity_score: number;
}

/** A single trace-link similarity-search hit (REQ-L2-VS-004). */
export interface SimilarTraceLink {
  id: UUID;
  source_id: UUID;
  target_id: UUID;
  link_type: string;
  /** Cosine similarity in [~-1, 1]; higher means more similar. */
  similarity_score: number;
}

// ---------------------------------------------------------------------------
// TestCase (mirrors TestCaseSerializer)
// ---------------------------------------------------------------------------

export interface TestCase {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  status: string;
  suspect?: boolean;
  version: number;
  uid?: string;
  custom_fields?: CustomFields;
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

export type ASILLevel = "QM" | "A" | "B" | "C" | "D" | null;

export type MakeOrBuyDecision = "Make" | "Buy" | "Reuse" | null;

export interface ArchitectureElement {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  element_type: ElementType;
  parent_id?: UUID | null;
  level?: number;
  version: number;
  uid?: string | null;
  asil_level?: ASILLevel;
  make_or_buy?: MakeOrBuyDecision;
  suspect?: boolean;
  change_reason?: string;
  custom_fields?: CustomFields;
  /** REQ-006: lifecycle status; 'deleted' elements are hidden in normal views */
  lifecycle_status?: "active" | "outdated" | "deprecated" | "deleted";
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// TraceLink (mirrors TraceLinkSerializer)
// ---------------------------------------------------------------------------

// Harmonized with backend/traceability/types.py::LinkType (12 types)
export type LinkType =
  | "parent-child"
  | "derives-from"
  | "satisfies"
  | "verifies"
  | "implements"
  | "refines"
  | "documents"
  | "realizes"
  | "traces"
  | "copy-of"
  | "allocated-to"
  | "uses-term"
  | "decides";

export interface TraceLink {
  id: UUID;
  source_id: UUID;
  target_id: UUID;
  link_type: string;
  version: number;
  created_at: ISODateTime;
  /** REQ-002: human-readable title of the source artifact (optional, may be absent in legacy responses). */
  source_title?: string;
  /** REQ-002: human-readable title of the target artifact. */
  target_title?: string;
  /** REQ-002: artifact type of the source (e.g. "Requirement", "ArchitectureElement"). */
  source_type?: string;
  /** REQ-002: artifact type of the target. */
  target_type?: string;
}

// ---------------------------------------------------------------------------
// Artifact (mirrors ArtifactSerializer)
// ---------------------------------------------------------------------------

export interface Artifact {
  id: UUID;
  workspace_id: UUID;
  artifact_type: string;
  parent_id: UUID | null;
  custom_fields?: CustomFields;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// ADR (mirrors AdrSerializer, REQ-L1-029)
// ---------------------------------------------------------------------------

export type AdrStatus =
  | "Draft"
  | "In Review"
  | "Approved"
  | "Rejected"
  | "Superseded"
  | "Deleted"; // REQ-006: soft-delete marker; set by backend delete endpoint

export interface Adr {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  context: string;
  consequences: string;
  status: AdrStatus;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Risk (mirrors RiskSerializer, REQ-L1-029)
// ---------------------------------------------------------------------------

export type RiskProbability = "low" | "medium" | "high";
export type RiskImpact = "low" | "medium" | "high";
export type RiskSeverity = "low" | "medium" | "high";
export type RiskCategory = "technical" | "operational" | "organizational" | "business";
export type RiskStatus = "Identified" | "Monitored" | "Mitigated" | "Accepted" | "Closed";

export interface Risk {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  probability: RiskProbability;
  impact: RiskImpact;
  risk_score: number;
  severity: RiskSeverity;
  category: RiskCategory;
  owner: string;
  mitigation_strategy: string;
  status: RiskStatus;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Issue (mirrors IssueSerializer, REQ-L1-029)
// ---------------------------------------------------------------------------

export type IssueSeverity = "critical" | "high" | "medium" | "low";
export type IssueCategory = "defect" | "improvement" | "documentation" | "question";
export type IssueStatus = "Open" | "In Progress" | "Resolved" | "Closed" | "Wontfix";

export interface Issue {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  severity: IssueSeverity;
  category: IssueCategory;
  status: IssueStatus;
  tags: string[];
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Diagram (mirrors DiagramSerializer, REQ-L0-016 / REQ-L2-DS-001)
// ---------------------------------------------------------------------------

export type DiagramType = "block" | "flow" | "context" | "canvas" | "mermaid";

export type PayloadFormat = "mermaid" | "plantuml" | "json" | "canvas_stroke";

export interface Diagram {
  id: UUID;
  name: string;
  diagram_type: DiagramType;
  description: string;
  current_version: UUID | null;
  created_at: ISODateTime | null;
  version_count?: number;
}

export interface DiagramDetail extends Diagram {
  payload_format: PayloadFormat | null;
  content: string | null;
  version_number: number | null;
}

export interface DiagramTraceLink {
  id: UUID;
  source_id: UUID;
  target_id: UUID;
  link_type: string;
  target_type: string;
  target_title: string;
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
    adr: false,
    risk: false,
    issue: false,
    csv_import: false,
    icds: false,
    diagrams: false,
    metrics: false,
    testCases: false,
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
    adr: true,
    risk: true,
    issue: true,
    csv_import: true,
    icds: true,
    diagrams: true,
    metrics: true,
    testCases: true,
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
    adr: true,
    risk: true,
    issue: true,
    csv_import: true,
    icds: true,
    diagrams: true,
    metrics: true,
    testCases: true,
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

// ---------------------------------------------------------------------------
// Requirement categories (REQ-L2-RF-001)
// ---------------------------------------------------------------------------

export const REQ_CATEGORIES = [
  "stakeholder",
  "functional",
  "non-functional",
  "api",
  "ui-ux",
  "data",
  "integration",
] as const;

export type ReqCategory = typeof REQ_CATEGORIES[number];

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
  status: "in_progress" | "passed" | "failed" | "partial";
  ci_job_id: string;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  result_summary: TestRunResultSummary;
  version: number;
  uid?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// ArtifactDiff (REQ-L2-RF-014, COMP-AS-019)
// ---------------------------------------------------------------------------

export type DiffFieldStatus = "added" | "removed" | "modified" | "unchanged";

export interface DiffField {
  name: string;
  status: DiffFieldStatus;
  from?: string;
  to?: string;
  lines?: string[];
}

export interface ArtifactDiffResult {
  from_version: number;
  to_version: number;
  entity_type: string;
  fields: DiffField[];
  note?: string;
}

export interface ArtifactVersion {
  version: number;
  label: string;
  modified_at?: string | null;
}

// ---------------------------------------------------------------------------
// Canvas Stroke types (REQ-L1-056, IF-L1-058/060, COMP-DS-006)
// ---------------------------------------------------------------------------

export type CanvasElementType =
  | "pen"
  | "rect"
  | "circle"
  | "line"
  | "text"
  | "arrow"
  | "connector";

export type CanvasTool =
  | "pen"
  | "select"
  | "eraser"
  | "rect"
  | "ellipse"
  | "text"
  | "connector";

export interface CanvasPoint {
  x: number;
  y: number;
}

export interface CanvasStroke {
  id?: string;
  type: CanvasElementType;
  color?: string;
  width?: number;
  fill?: string;
  opacity?: number;
  // Pen-specific
  points?: CanvasPoint[];
  // Shape-specific
  x?: number;
  y?: number;
  height?: number;
  cx?: number;
  cy?: number;
  r?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  // Text-specific
  content?: string;
  font_size?: number;
  // Connector-specific
  source_id?: string;
  target_id?: string;
}

export interface CanvasStrokeData {
  strokes: CanvasStroke[];
  width?: number;
  height?: number;
  /**
   * Full Fabric.js canvas serialization (REQ-L2-CV-005). Produced by
   * canvas.toJSON(["data"]) and carries all object types incl. custom
   * connector anchor metadata under each object's `data` property.
   * Sent alongside `strokes` for backward compatibility.
   */
  canvas_json?: FabricCanvasJson;
}

/**
 * Minimal shape of a Fabric.js canvas serialization. Fabric emits many more
 * keys; only `objects` is load-bearing for the backward-compatible load path.
 */
export interface FabricCanvasJson {
  objects: Array<Record<string, unknown>>;
  version?: string;
  background?: string;
  [key: string]: unknown;
}

export interface CanvasStrokeResponse {
  diagram_id: UUID;
  strokes: CanvasStroke[];
  width: number;
  height: number;
  svg: string;
  version_number: number | null;
  /** Fabric.js serialization when persisted via the toJSON path (REQ-L2-CV-005). */
  canvas_json?: FabricCanvasJson | null;
}

// ---------------------------------------------------------------------------
// Mermaid types (REQ-L1-057, IF-L1-059/061, COMP-DS-007)
// ---------------------------------------------------------------------------

export interface MermaidSourceResponse {
  diagram_id: UUID;
  source: string;
  diagram_type: string;
  is_valid: boolean;
  error_message: string;
}

export interface MermaidRenderHints {
  supported_formats: string[];
  renderer: string;
  notes: string;
}

export interface MermaidPreviewResponse {
  diagram_id: UUID;
  source: string;
  diagram_type: string;
  render_hints: MermaidRenderHints | null;
  fallback_mode: boolean;
  error_message: string;
}

// ---------------------------------------------------------------------------
// Requirement Editor Constants (COMP-RF-003)
// ---------------------------------------------------------------------------

export const WORKFLOW_STATES = [
  'Draft',
  'Review',
  'Approved',
  'In Progress',
  'Implemented',
  'Verified',
  'Rejected',
  'Deprecated',
];

// ---------------------------------------------------------------------------
// Glossary
// ---------------------------------------------------------------------------

export interface GlossaryTerm {
  id: string;
  workspace_id: string;
  term: string;
  definition: string;
  synonyms: string[];
  abbreviation?: string;
  is_global?: boolean;
  /** REQ-006: lifecycle status; 'deleted' terms are hidden in normal views */
  lifecycle_status?: "active" | "outdated" | "deprecated" | "deleted";
  created_at?: string;
  updated_at?: string;
}
