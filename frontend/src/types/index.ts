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
  /**
   * @deprecated Legacy free-form prompt blob, no longer read or written by the
   * UI (issue #119). Prompt templates live in the `PromptTemplate` model and
   * are edited via `/api/v1/prompt-templates/slots/` (see
   * `api/prompt-templates.ts`). Still serialized by the backend, so the field
   * is kept on the type until it is dropped there.
   */
  ai_prompts?: Record<string, string>;
  decomposition_link_type?: string;
  default_link_type?: string;
  is_active: boolean;
  closed_at: ISODateTime | null;
  closed_by: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  /** Ziele-Feature (Goal/MainGoal) für diesen Workspace aktiviert. */
  goals_enabled?: boolean;
  /** KI-gestützte MainGoal-Generierung aktiviert (erfordert goals_enabled). */
  goals_ai_enabled?: boolean;
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

/**
 * #344: mirrors the backend `RequirementType` choices
 * (`backend/persistence/models.py`), which are additionally pinned by the DB
 * CHECK constraint added in migration 0050. The previous union
 * (`'SyReq' | 'SWReq' | 'HWReq'`) drifted from the backend: writing SWReq or
 * HWReq was rejected with 400 and the whole edit was discarded.
 */
export type RequirementType = 'SyReq' | 'UseCase' | 'FeatureReq';
export type MoscowPriority = 'Must' | 'Should' | 'Could' | "Won't";
export type VerificationMethod = 'Test' | 'Review' | 'Analysis' | 'Inspection';

/**
 * Issue #394: V-model hierarchy level (`persistence.models.RequirementLevel`).
 * `null`/`undefined` means the level has not been assigned yet — mirrors the
 * backend field, which is nullable and not backfilled for existing rows.
 */
export type RequirementLevel = 0 | 1 | 2 | 3 | 4;

/** Ordered L0-L4 levels for select inputs; mirrors the backend enum order. */
export const REQUIREMENT_LEVELS: RequirementLevel[] = [0, 1, 2, 3, 4];

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
  artifact_id?: UUID;
  parent_id?: string;
  title: string;
  description: string;
  // #43: acceptance criteria describing when the requirement is fulfilled.
  acceptance_criteria?: string;
  category: string;
  status: string;
  version: number;
  uid?: string;
  type?: RequirementType;
  moscow_priority?: MoscowPriority;
  complexity_fibonacci?: number;
  verification_method?: VerificationMethod;
  // Issue #394: V-model hierarchy level (0=System ... 4=Material). NULL until
  // assigned explicitly.
  level?: RequirementLevel | null;
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

/**
 * Structural role derived from the element's position in the decomposition tree
 * (SysEng 2.0 §1.2). Computed by the backend, read-only — never sent on write.
 * root → "system", inner node → "subsystem", leaf → "component".
 */
export type ArchitectureRole = "system" | "subsystem" | "component";

export type ASILLevel = "QM" | "A" | "B" | "C" | "D" | null;

export type MakeOrBuyDecision = "Make" | "Buy" | "Reuse" | null;

export interface ArchitectureElement {
  id: UUID;
  workspace_id: UUID;
  /** Owning Artifact — the key for workspace custom fields (REQ-016). */
  artifact_id?: UUID;
  title: string;
  description: string;
  element_type: ElementType;
  parent_id?: UUID | null;
  level?: number;
  /** SysEng 2.0 §1.2: derived structural role (read-only, computed from tree position). */
  role?: ArchitectureRole;
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

// Harmonized with backend/traceability/types.py::LinkType (14 types, incl.
// `decomposes` — see docs/UMSETZUNGSPLAN_SYSENG_2.0.md §1.4)
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
  | "decides"
  | "decomposes";

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
  // Task 2.1: the backing Artifact id (Adr.artifact, backend/application/models.py)
  // is not yet exposed by AdrSerializer — unlike Requirement/StakeholderNeed/
  // ArchitectureElement, which all serialize a separate `artifact_id`. Declared
  // here (optional, currently always undefined) so <ArtifactCustomFields> in
  // AdrForm is wired the same way as the other forms and starts working the
  // moment the backend field ships, instead of needing another frontend change.
  artifact_id?: UUID;
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
// Goal / MainGoal (mirror GoalSerializer/MainGoalSerializer, REQ-L2-TE-020)
// ---------------------------------------------------------------------------

/**
 * Goal — lineage-versioned workspace artifact (Variante A: every edit creates
 * a new row sharing the same `lineage_id`).
 */
export interface Goal {
  id: UUID;
  workspace_id: UUID;
  /** Owning Artifact — the key for workspace custom fields (REQ-016). */
  artifact_id?: UUID;
  lineage_id: UUID;
  sequence_number: number;
  title: string;
  description: string;
  status: string;
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/**
 * MainGoal — single workspace-scoped version chain (not lineage-based like
 * Goal). `source` distinguishes an LLM-aggregated draft from a manually
 * authored one; `approve` transitions a draft to `Freigegeben`.
 */
export interface MainGoal {
  id: UUID;
  workspace_id: UUID;
  sequence_number: number;
  content: string;
  source: "ai" | "manual";
  generated_from_goal_ids?: string[];
  status: string;
  version: number;
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
  // Task 2.2: same as Adr.artifact_id above — the backing Artifact id is not
  // yet exposed by RiskSerializer. Declared here (optional, currently always
  // undefined) so <ArtifactCustomFields> in RiskForm is wired the same way as
  // the other forms and starts working the moment the backend field ships.
  artifact_id?: UUID;
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
  // Task 2.3: same as Adr.artifact_id / Risk.artifact_id above — the backing
  // Artifact id is not yet exposed by IssueSerializer. Declared here
  // (optional, currently always undefined) so <ArtifactCustomFields> in
  // IssueForm is wired the same way as the other forms and starts working
  // the moment the backend field ships.
  artifact_id?: UUID;
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

export type PayloadFormat =
  | "mermaid"
  | "plantuml"
  | "json"
  | "canvas_stroke"
  | "node_graph";

// ---------------------------------------------------------------------------
// Node Graph payload (payload_format=node_graph, GH-353 Task 1/8) — mirrors
// backend/diagram/node_graph.py exactly (field names, enum values). Any drift
// here is a silent contract break with the backend validator.
// ---------------------------------------------------------------------------

export type GraphNodeType = "box" | "rounded" | "ellipse" | "diamond" | "note" | "group";

export type GraphEdgeType = "flow" | "association" | "dependency" | "containment";

export type GraphStyleAccent =
  | "default"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "muted";

export type GraphEdgeLineStyle = "solid" | "dashed";

export type GraphHandlePosition = "top" | "right" | "bottom" | "left";

/** Mirrors diagram.node_graph.KNOWN_ARTIFACT_ENTITY_TYPES. */
export type GraphArtifactEntityType =
  | "Requirement"
  | "StakeholderNeed"
  | "ArchitectureElement"
  | "TestCase"
  | "Adr"
  | "Risk"
  | "Issue"
  | "GlossaryTerm"
  | "Goal"
  | "MainGoal";

export interface GraphArtifactRef {
  entity_type: GraphArtifactEntityType;
  id: UUID;
}

export interface GraphNodePosition {
  x: number;
  y: number;
}

export interface GraphNodeSize {
  width: number;
  height: number;
}

export interface GraphNodeStyle {
  accent?: GraphStyleAccent;
}

export interface GraphEdgeStyle {
  line?: GraphEdgeLineStyle;
}

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  position: GraphNodePosition;
  size?: GraphNodeSize;
  style?: GraphNodeStyle;
  artifact_ref?: GraphArtifactRef;
  parent_id?: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: GraphEdgeType;
  label?: string;
  source_handle?: GraphHandlePosition | null;
  target_handle?: GraphHandlePosition | null;
  style?: GraphEdgeStyle;
}

export interface GraphViewport {
  x: number;
  y: number;
  zoom: number;
}

/** Envelope for payload_format=node_graph (transported as a JSON string in `content`). */
export interface NodeGraphPayload {
  schema_version: 1;
  nodes: GraphNode[];
  edges: GraphEdge[];
  viewport?: GraphViewport;
}

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
  // REQ-173: WorkflowEngine lifecycle state, seeds the WorkflowStatusEditor
  // before its /transitions/ fetch resolves. Optional — the endpoint stays
  // authoritative for the current state.
  status?: string;
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
  status: "in_progress" | "passed" | "failed" | "partial" | "closed";
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
  /**
   * Addressing token for `/diff/` and baseline pinning. For single-row
   * artifact types this is the backend's optimistic-lock counter, NOT a
   * revision number — it also increments on writes that change nothing
   * user-visible (issue #213).
   */
  version: number;
  label: string;
  modified_at?: string | null;
  /**
   * Whether a retrievable snapshot is stored for this version. `false` for
   * the empty creation baseline and for historical lock-counter values of
   * single-row types. Older backends omit the flag; treat that as `true`.
   */
  content_available?: boolean;
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
//
// GH-453: `WORKFLOW_STATES` used to live here — one Title-Case array that all
// six artifact lists used to build their status filter. It matched no entity's
// actual vocabulary (see backend/workflow/definition_store.py PRESET_SCHEMAS),
// so picking an option produced an empty list. Filter options are now derived
// from the loaded items via `utils/workflowStatus.buildStatusFilterOptions`,
// and display text comes from `getWorkflowStatusLabel`.

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
