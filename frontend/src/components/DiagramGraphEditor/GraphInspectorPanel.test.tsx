/**
 * GH-353 Task 8 — GraphInspectorPanel: node/edge property editing and the
 * artifact-ref picker (Task 8 brief: "search/select against the known
 * artifact types from Task 1's table").
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import { GraphInspectorPanel } from "./GraphInspectorPanel";
import type { GraphFlowEdge, GraphFlowNode } from "./graph-layout";
import type { GraphNode } from "../../types";

function makeFlowNode(node: GraphNode): GraphFlowNode {
  return {
    id: node.id,
    type: "graphNode",
    position: node.position,
    data: { node },
  };
}

const EDGES: GraphFlowEdge[] = [];

describe("GraphInspectorPanel — artifact-ref picker", () => {
  it("defaults the entity-type select to the first known artifact type when no ref is set", () => {
    const node: GraphNode = { id: "n1", type: "box", label: "N1", position: { x: 0, y: 0 } };
    render(
      <GraphInspectorPanel
        nodes={[makeFlowNode(node)]}
        edges={EDGES}
        selection={{ kind: "node", id: "n1" }}
        onSelect={vi.fn()}
        editMode
        onUpdateNode={vi.fn()}
        onUpdateEdge={vi.fn()}
        onDeleteNode={vi.fn()}
        onDeleteEdge={vi.fn()}
      />
    );

    expect(screen.getByTestId("graph-inspector-artifact-entity-type")).toHaveValue("Requirement");
    expect(screen.getByTestId("graph-inspector-artifact-id")).toHaveValue("");
    // No ref yet -> the "unlinked" hint shows, not the clear button.
    expect(screen.queryByTestId("graph-inspector-artifact-clear")).not.toBeInTheDocument();
  });

  it("picking an entity type and typing an id patches the node's artifact_ref", () => {
    const node: GraphNode = { id: "n1", type: "box", label: "N1", position: { x: 0, y: 0 } };
    const onUpdateNode = vi.fn();
    render(
      <GraphInspectorPanel
        nodes={[makeFlowNode(node)]}
        edges={EDGES}
        selection={{ kind: "node", id: "n1" }}
        onSelect={vi.fn()}
        editMode
        onUpdateNode={onUpdateNode}
        onUpdateEdge={vi.fn()}
        onDeleteNode={vi.fn()}
        onDeleteEdge={vi.fn()}
      />
    );

    fireEvent.change(screen.getByTestId("graph-inspector-artifact-entity-type"), {
      target: { value: "ArchitectureElement" },
    });
    expect(onUpdateNode).toHaveBeenLastCalledWith("n1", {
      artifact_ref: { entity_type: "ArchitectureElement", id: "" },
    });

    fireEvent.change(screen.getByTestId("graph-inspector-artifact-id"), {
      target: { value: "3fa85f64-5717-4562-b3fc-2c963f66afa6" },
    });
    expect(onUpdateNode).toHaveBeenLastCalledWith("n1", {
      artifact_ref: { entity_type: "Requirement", id: "3fa85f64-5717-4562-b3fc-2c963f66afa6" },
    });
  });

  it("shows the clear button once a ref is set, and clearing removes it", () => {
    const node: GraphNode = {
      id: "n1",
      type: "box",
      label: "N1",
      position: { x: 0, y: 0 },
      artifact_ref: { entity_type: "Risk", id: "3fa85f64-5717-4562-b3fc-2c963f66afa6" },
    };
    const onUpdateNode = vi.fn();
    render(
      <GraphInspectorPanel
        nodes={[makeFlowNode(node)]}
        edges={EDGES}
        selection={{ kind: "node", id: "n1" }}
        onSelect={vi.fn()}
        editMode
        onUpdateNode={onUpdateNode}
        onUpdateEdge={vi.fn()}
        onDeleteNode={vi.fn()}
        onDeleteEdge={vi.fn()}
      />
    );

    expect(screen.getByTestId("graph-inspector-artifact-entity-type")).toHaveValue("Risk");
    const clearBtn = screen.getByTestId("graph-inspector-artifact-clear");
    fireEvent.click(clearBtn);
    expect(onUpdateNode).toHaveBeenCalledWith("n1", { artifact_ref: undefined });
  });

  it("disables the picker fields outside edit mode", () => {
    const node: GraphNode = { id: "n1", type: "box", label: "N1", position: { x: 0, y: 0 } };
    render(
      <GraphInspectorPanel
        nodes={[makeFlowNode(node)]}
        edges={EDGES}
        selection={{ kind: "node", id: "n1" }}
        onSelect={vi.fn()}
        editMode={false}
        onUpdateNode={vi.fn()}
        onUpdateEdge={vi.fn()}
        onDeleteNode={vi.fn()}
        onDeleteEdge={vi.fn()}
      />
    );

    expect(screen.getByTestId("graph-inspector-artifact-entity-type")).toBeDisabled();
    expect(screen.getByTestId("graph-inspector-artifact-id")).toBeDisabled();
  });

  it("shows the empty prompt when nothing is selected", () => {
    render(
      <GraphInspectorPanel
        nodes={[]}
        edges={EDGES}
        selection={{ kind: "none" }}
        onSelect={vi.fn()}
        editMode
        onUpdateNode={vi.fn()}
        onUpdateEdge={vi.fn()}
        onDeleteNode={vi.fn()}
        onDeleteEdge={vi.fn()}
      />
    );

    expect(screen.queryByTestId("graph-inspector-artifact-entity-type")).not.toBeInTheDocument();
  });
});
