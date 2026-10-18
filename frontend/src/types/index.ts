/**
 * Shared domain types for ARCH-L1-001 ReactFrontend.
 *
 * leaf_id: COMP-RF-001..004
 * req_id:  REQ-L2-RF-001..012
 *
 * All types mirror the REST API serializer fields from ARCH-L1-002.
 * Generic API field names are kept as-is; only UI labels change per terminology profile.
 */

import type { CustomFields, GlossaryReferenceMode, ISODateTime, SystemFieldValues, UUID } from "./common";

export * from "./common";
export * from "./auth";
export * from "./workspace";
export * from "./requirement";
export * from "./architecture";
export * from "./traceability";

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
  name: string;
  interface_type: string;
  /**
   * The matched ICD's current contract revision. Backend Task 28c-2 dropped
   * the companion `version_id`: the embedding moved onto the ICD row itself,
   * so there is no version row left to identify.
   */
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

export interface TestCase extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  /**
   * #399 (MAJOR-1): the backing Artifact id, distinct from the TestCase pk —
   * the baseline-membership endpoint and `affected_item_ids` prefill key on
   * Artifact ids, never on the entity pk.
   */
  artifact_id?: UUID;
  title: string;
  description: string;
  status: string;
  suspect?: boolean;
  /** #424: content provenance (`manual` | `ai_generated` | `unknown`). */
  origin?: "manual" | "ai_generated" | "unknown";
  /** #424: human content sign-off — only toggled via the review endpoint. */
  reviewed?: boolean;
  /** #402: `nominal` (default) or `off_nominal`. */
  scenario_kind?: "nominal" | "off_nominal";
  /** #399: additive baseline-drift summary on the detail retrieve. */
  baseline_drift?: { drifted: boolean; count: number };
  version: number;
  uid?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
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

export interface Adr extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  // Task 2.1: the backing Artifact id (Adr.artifact, backend/application/models.py)
  // is not yet exposed by AdrSerializer — unlike Requirement/StakeholderNeed/
  // ArchitectureElement, which all serialize a separate `artifact_id`. Declared
  // here (optional, currently always undefined) for parity with the other
  // artifact types. NOTE (Task 27): the workspace-defined custom-field
  // renderer that used to consume this id is gone along with its backend
  // (custom fields are attribute definitions now, tracked gap #7). The field
  // stays declared for the next consumer of the backing Artifact id.
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
export interface Goal extends SystemFieldValues {
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
  /**
   * UI-28 (Systemaudit 2026-08-27 AP-5): only ever `true`/`false` on the
   * response of `POST /main-goals/generate/` — every other MainGoal
   * response omits it (not a persisted field, see MainGoalSerializer).
   */
  is_mock_fallback?: boolean;
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
  // undefined) for parity with the other artifact types.
  artifact_id?: UUID;
  title: string;
  description: string;
  probability: RiskProbability;
  impact: RiskImpact;
  risk_score: number;
  /**
   * UI-39 (Systemaudit 2026-08-27 AP-5): FMEA detectability score
   * (1=easy to detect .. 10=impossible), mirrors RiskSerializer.detection.
   */
  detection?: number;
  /**
   * UI-39: Risk Priority Number (probability × impact × detection),
   * read-only computed property (RiskSerializer.rpn).
   */
  rpn?: number;
  severity: RiskSeverity;
  category: RiskCategory;
  owner: string;
  /**
   * REQ-L1-029 (FMEA): structured User FK for risk assignment, mirrors
   * RiskSerializer.owner_user_id (kept alongside the legacy free-text
   * `owner` field). Task 19: the attribute-definition bootstrap serves this
   * under the same name (see bootstrap_attribute_definitions.py's
   * WIDGET_FIELD_ALIASES — the raw Django FK field is named `owner_user`,
   * aliased to match this serializer field).
   */
  owner_user_id?: UUID | null;
  /** Read-only display label for `owner_user_id` (RiskSerializer.owner_user_display). */
  owner_user_display?: string | null;
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

export interface Issue extends SystemFieldValues {
  id: UUID;
  workspace_id: UUID;
  // Task 2.3: same as Adr.artifact_id / Risk.artifact_id above — the backing
  // Artifact id is not yet exposed by IssueSerializer. Declared here
  // (optional, currently always undefined) for parity with the other
  // artifact types.
  artifact_id?: UUID;
  title: string;
  description: string;
  severity: IssueSeverity;
  category: IssueCategory;
  status: IssueStatus;
  tags: string[];
  /**
   * Task 20 finding: `IssueSerializer` never declared this field at all
   * (mirrors Task 19's `owner_user_id` finding on Risk) even though
   * `IssueService.create_issue`/`update_issue` both already accept and
   * persist it — via REST, every save silently discarded it and every read
   * came back empty (the MCP generic tool group was unaffected: it forwards
   * arbitrary params straight to the service, bypassing this serializer).
   * Fixed at the serializer/view layer alongside this migration.
   */
  due_date?: ISODateTime | null;
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
// Glossary
// ---------------------------------------------------------------------------

export interface GlossaryTerm extends SystemFieldValues {
  id: string;
  workspace_id: string;
  term: string;
  definition: string;
  synonyms: string[];
  abbreviation?: string;
  is_global?: boolean;
  /** Lifecycle/workflow state. #831: exposed under the artifact-consistent
   *  wire key `status` (like Requirement/Adr/Risk/Issue/...). Since the
   *  Datenmodell-Konsolidierung the underlying soft-delete flag lives on the
   *  backing Artifact, but the API field name is `status`. */
  status?: "active" | "outdated" | "deprecated" | "deleted";
  /**
   * UI-59 (Systemaudit 2026-08-27 AP-5): optimistic-lock version counter —
   * mirrors GlossaryTermSerializer.version. Was missing here even though the
   * wire payload always includes it, which forced GlossaryView.tsx to pass
   * `currentVersion={undefined}` into the (otherwise fully wired) shared
   * VersionPanel/DiffPanel, hiding the versions/diff UI that REQ-142 already
   * built for every other artifact kind including "glossary".
   */
  version?: number;
  /**
   * #1266: stable global UUID of the term (== backing Artifact id), the
   * identity a `[[glossary:<uuid>@<revision>]]` reference token pins. Exposed
   * read-only by the backend (`GlossaryTermSerializer.global_uuid`).
   */
  global_uuid?: string;
  created_at?: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// Glossary references (#1266) — version-bound `[[glossary:<uuid>@<rev>]]`
// tokens embedded in markdown/text fields, resolved by the backend against the
// pinned revision (or the current head in `always_head` mode).
// ---------------------------------------------------------------------------

/** One distinct `(global_uuid, revision)` token resolved against the history. */
export interface GlossaryReferenceResolution {
  global_uuid: string;
  requested_revision: number | null;
  resolved_revision: number;
  head_revision: number;
  term: string;
  definition: string;
  /** False when no term with that global UUID exists (foreign/stale token). */
  resolved: boolean;
  /** True when a pinned revision is behind the term's current head. */
  drift: boolean;
}

export interface GlossaryReferenceResolutionPayload {
  mode: GlossaryReferenceMode;
  has_drift: boolean;
  references: GlossaryReferenceResolution[];
}

export interface GlossaryReferenceInsertResult {
  token: string;
  global_uuid: string;
  term: string;
  definition: string;
  version: number;
  link_type: string;
  mode: GlossaryReferenceMode;
}

export interface GlossaryReferenceUpgradeResult {
  text: string;
  upgraded: number;
}
