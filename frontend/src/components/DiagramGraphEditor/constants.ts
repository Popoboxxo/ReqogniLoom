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

/** Mirrors diagram.node_graph.KNOWN_ARTIFACT_ENTITY_TYPES. */
export const GRAPH_ARTIFACT_ENTITY_TYPES: readonly GraphArtifactEntityType[] = [
  "Requirement",
  "StakeholderNeed",
  "ArchitectureElement",
  "TestCase",
  "Adr",
  "Risk",
  "Issue",
  "GlossaryTerm",
  "Goal",
  "MainGoal",
];
