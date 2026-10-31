/**
 * Diagram, node-graph, canvas-stroke and Mermaid types.
 *
 * Split out of the monolithic `types/index.ts` (F-16); re-exported by the
 * `@/types` barrel so existing import paths stay stable. Definitions are
 * moved verbatim.
 */

import type { ISODateTime, UUID } from "./common";

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
  // #1374: the backing Artifact id — what `POST /api/v1/trace-links/` expects
  // as `source_id`/`target_id` (link endpoints resolve to Artifact ids, never
  // to `id`). `global_uuid` is the same value under the stable-identity name
  // Requirement/Glossary publish (#1261/#1270). Optional read-only: absent
  // (or null) for a workspace-less legacy diagram, which owns no Artifact.
  artifact_id?: UUID | null;
  global_uuid?: UUID | null;
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
