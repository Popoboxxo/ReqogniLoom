/**
 * GH-353 Task 8 — DiagramGraphEditor shared constants + selection types.
 */

import type { GraphArtifactEntityType, GraphEdgeType, GraphNodeType, GraphStyleAccent } from "../../types";

/** What the user has currently selected on the canvas. */
export type Selection =
  | { kind: "none" }
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string };

/** Mirrors diagram.node_graph.NODE_TYPES. */
export const GRAPH_NODE_TYPES: readonly GraphNodeType[] = [
  "box",
  "rounded",
  "ellipse",
  "diamond",
  "note",
  "group",
];

/** Mirrors diagram.node_graph.EDGE_TYPES. */
export const GRAPH_EDGE_TYPES: readonly GraphEdgeType[] = [
  "flow",
  "association",
  "dependency",
  "containment",
];

/** Mirrors diagram.node_graph.STYLE_ACCENTS. */
export const GRAPH_STYLE_ACCENTS: readonly GraphStyleAccent[] = [
  "default",
  "primary",
  "success",
  "warning",
  "danger",
  "muted",
];

/**
 * Entity types offered by the artifact-ref picker (GraphInspectorPanel).
 *
 * Mirrors diagram.node_graph.KNOWN_ARTIFACT_ENTITY_TYPES, EXCEPT
 * "GlossaryTerm" (I2, GH-353 final review): GlossaryTerm has no backing
 * Artifact row (see backend/diagram/traceability_connector.py
 * ``_resolve_target_artifact_id``'s docstring — it always falls through to
 * ``return None``), so a node referencing it can never resolve and always
 * fails to save with a generic, confusing error. Removed from the picker
 * rather than fixed on the backend — that's a pre-existing data-model gap,
 * not something this fix attempts to close.
 */
export const GRAPH_ARTIFACT_ENTITY_TYPES: readonly GraphArtifactEntityType[] = [
  "Requirement",
  "StakeholderNeed",
  "ArchitectureElement",
  "TestCase",
  "Adr",
  "Risk",
  "Issue",
  "Goal",
  "MainGoal",
];
