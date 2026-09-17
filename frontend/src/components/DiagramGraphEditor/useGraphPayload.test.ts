/**
 * GH-353 Task 8 — useGraphPayload.ts (de)serialization round-trip tests.
 *
 * Verifies `payloadToFlowNodes`/`payloadToFlowEdges`/`flowToPayload` against
 * Task 1's exact schema (backend/diagram/node_graph.py): every field name and
 * enum value used here mirrors that module, and a full payload (every
 * optional field populated, on at least one node/edge) must round-trip
 * losslessly through the React Flow node/edge representation.
 */

import { describe, expect, it } from "vitest";
import {
  EMPTY_NODE_GRAPH_PAYLOAD,
  flowToPayload,
  parseNodeGraphContent,
  parseNodeGraphContentStrict,
  payloadToFlowEdges,
  payloadToFlowNodes,
} from "./useGraphPayload";
import type { NodeGraphPayload } from "../../types";

const FULL_PAYLOAD: NodeGraphPayload = {
  schema_version: 1,
  nodes: [
    {
      id: "n1",
      type: "box",
      label: "Start",
      position: { x: 10, y: 20 },
    },
    {
      id: "n2",
      type: "diamond",
      label: "Decision",
      position: { x: 210, y: 20 },
      size: { width: 220, height: 90 },
      style: { accent: "warning" },
      artifact_ref: { entity_type: "Requirement", id: "3fa85f64-5717-4562-b3fc-2c963f66afa6" },
      parent_id: null,
    },
    {
      id: "grp",
      type: "group",
      label: "Subsystem",
      position: { x: 0, y: 0 },
    },
    {
      id: "n3",
      type: "note",
      label: "child of group",
      position: { x: 5, y: 5 },
      parent_id: "grp",
    },
  ],
  edges: [
    {
      id: "e1",
      source: "n1",
      target: "n2",
      type: "flow",
      label: "next",
      source_handle: "bottom",
      target_handle: "top",
      style: { line: "dashed" },
    },
    {
      id: "e2",
      source: "n2",
      target: "n3",
      type: "dependency",
      source_handle: "right",
      target_handle: "left",
    },
  ],
  viewport: { x: 12, y: -8, zoom: 1.5 },
};

describe("payloadToFlowNodes / payloadToFlowEdges / flowToPayload round-trip", () => {
  it("round-trips a full payload (every optional field populated) losslessly", () => {
    const flowNodes = payloadToFlowNodes(FULL_PAYLOAD);
    const flowEdges = payloadToFlowEdges(FULL_PAYLOAD);
    const result = flowToPayload(flowNodes, flowEdges, FULL_PAYLOAD.viewport);

    expect(result).toEqual(FULL_PAYLOAD);
  });

  it("round-trips the empty envelope", () => {
    const flowNodes = payloadToFlowNodes(EMPTY_NODE_GRAPH_PAYLOAD);
    const flowEdges = payloadToFlowEdges(EMPTY_NODE_GRAPH_PAYLOAD);
    const result = flowToPayload(flowNodes, flowEdges);

    expect(result).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
  });

  it("carries node position edits (drag) through to the saved payload", () => {
    const flowNodes = payloadToFlowNodes(FULL_PAYLOAD);
    const flowEdges = payloadToFlowEdges(FULL_PAYLOAD);
    const moved = flowNodes.map((n) => (n.id === "n1" ? { ...n, position: { x: 999, y: 888 } } : n));

    const result = flowToPayload(moved, flowEdges, FULL_PAYLOAD.viewport);
    const n1 = result.nodes.find((n) => n.id === "n1")!;
    expect(n1.position).toEqual({ x: 999, y: 888 });
    // Everything else about n1 is preserved.
    expect(n1.label).toBe("Start");
    expect(n1.type).toBe("box");
  });

  it("preserves each node's own domain data (label/type/style/artifact_ref/parent_id)", () => {
    const flowNodes = payloadToFlowNodes(FULL_PAYLOAD);
    const flowEdges = payloadToFlowEdges(FULL_PAYLOAD);
    const result = flowToPayload(flowNodes, flowEdges);

    const n2 = result.nodes.find((n) => n.id === "n2")!;
    expect(n2.style).toEqual({ accent: "warning" });
    expect(n2.artifact_ref).toEqual({
      entity_type: "Requirement",
      id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    });
    expect(n2.size).toEqual({ width: 220, height: 90 });

    const n3 = result.nodes.find((n) => n.id === "n3")!;
    expect(n3.parent_id).toBe("grp");
  });

  it("defaults a missing edge handle to bottom/top (dagre's TB convention) rather than dropping it", () => {
    const payload: NodeGraphPayload = {
      schema_version: 1,
      nodes: [
        { id: "a", type: "box", label: "A", position: { x: 0, y: 0 } },
        { id: "b", type: "box", label: "B", position: { x: 100, y: 100 } },
      ],
      edges: [{ id: "e1", source: "a", target: "b", type: "flow" }],
    };
    const flowEdges = payloadToFlowEdges(payload);
    expect(flowEdges[0].sourceHandle).toBe("bottom");
    expect(flowEdges[0].targetHandle).toBe("top");

    const result = flowToPayload(payloadToFlowNodes(payload), flowEdges);
    expect(result.edges[0].source_handle).toBe("bottom");
    expect(result.edges[0].target_handle).toBe("top");
  });
});

describe("parseNodeGraphContent", () => {
  it("parses a valid JSON-encoded payload string", () => {
    const content = JSON.stringify(FULL_PAYLOAD);
    expect(parseNodeGraphContent(content)).toEqual(FULL_PAYLOAD);
  });

  it("falls back to the empty envelope for null/undefined content", () => {
    expect(parseNodeGraphContent(null)).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
    expect(parseNodeGraphContent(undefined)).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
    expect(parseNodeGraphContent("")).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
  });

  it("falls back to the empty envelope for malformed JSON", () => {
    expect(parseNodeGraphContent("{not json")).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
  });

  it("falls back to the empty envelope when nodes/edges are missing", () => {
    expect(parseNodeGraphContent(JSON.stringify({ schema_version: 1 }))).toEqual(
      EMPTY_NODE_GRAPH_PAYLOAD
    );
  });
});

describe("parseNodeGraphContentStrict (GH-353 final review I4)", () => {
  it("parses a valid JSON-encoded payload string, same as the tolerant variant", () => {
    const content = JSON.stringify(FULL_PAYLOAD);
    expect(parseNodeGraphContentStrict(content)).toEqual(FULL_PAYLOAD);
  });

  it("returns the empty envelope for null/undefined/empty content (not an error)", () => {
    expect(parseNodeGraphContentStrict(null)).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
    expect(parseNodeGraphContentStrict(undefined)).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
    expect(parseNodeGraphContentStrict("")).toEqual(EMPTY_NODE_GRAPH_PAYLOAD);
  });

  it("throws on malformed JSON instead of silently falling back", () => {
    expect(() => parseNodeGraphContentStrict("{not json")).toThrow();
  });

  it("throws when nodes/edges are missing (valid JSON, wrong shape) instead of silently falling back", () => {
    expect(() =>
      parseNodeGraphContentStrict(JSON.stringify({ schema_version: 1 }))
    ).toThrow(/NodeGraphPayload/);
  });
});
