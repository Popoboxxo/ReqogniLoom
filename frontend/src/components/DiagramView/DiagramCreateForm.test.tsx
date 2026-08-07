/**
 * DiagramCreateForm — create form wiring and defaults (GH-353 Task 9).
 *
 * req_id: REQ-L2-DS-001
 *
 * Tests verify:
 *   - node_graph becomes the default structured option (json is filtered out)
 *   - selecting node_graph produces the correct default payload
 *   - format labels are properly applied
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { DiagramCreateFormProps } from "./DiagramCreateForm";

vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => (typeof fallbackOrOptions === "string" ? fallbackOrOptions : key);
  return { useTranslation: () => ({ t }) };
});

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "Test Workspace" },
  }),
}));

const createDiagramMock = vi.fn();
vi.mock("./useDiagramData", () => ({
  useCreateDiagram: () => ({
    createDiagram: createDiagramMock,
    isSaving: false,
  }),
}));

import { DiagramCreateForm } from "./DiagramCreateForm";

describe("DiagramCreateForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers node_graph as a format option", () => {
    render(
      <DiagramCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />,
    );

    const formatSelect = screen.getByTestId("diagram-format-select") as HTMLSelectElement;
    const options = Array.from(formatSelect.options).map((opt) => opt.value);

    expect(options).toContain("node_graph");
  });

  it("does not offer json as a format option (filtered out in UI)", () => {
    render(
      <DiagramCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />,
    );

    const formatSelect = screen.getByTestId("diagram-format-select") as HTMLSelectElement;
    const options = Array.from(formatSelect.options).map((opt) => opt.value);

    expect(options).not.toContain("json");
  });

  it("still offers canvas_stroke, mermaid, and plantuml formats", () => {
    render(
      <DiagramCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />,
    );

    const formatSelect = screen.getByTestId("diagram-format-select") as HTMLSelectElement;
    const options = Array.from(formatSelect.options).map((opt) => opt.value);

    expect(options).toContain("canvas_stroke");
    expect(options).toContain("mermaid");
    expect(options).toContain("plantuml");
  });

  it("labels canvas_stroke as 'Freehand Sketch'", () => {
    render(
      <DiagramCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />,
    );

    const formatSelect = screen.getByTestId("diagram-format-select") as HTMLSelectElement;
    const canvasStrokeOption = Array.from(formatSelect.options).find(
      (opt) => opt.value === "canvas_stroke",
    );

    expect(canvasStrokeOption?.textContent).toBe("Freehand Sketch");
  });

  it("labels node_graph as 'Structured Graph'", () => {
    render(
      <DiagramCreateForm onCreated={vi.fn()} onCancel={vi.fn()} />,
    );

    const formatSelect = screen.getByTestId("diagram-format-select") as HTMLSelectElement;
    const nodeGraphOption = Array.from(formatSelect.options).find(
      (opt) => opt.value === "node_graph",
    );

    expect(nodeGraphOption?.textContent).toBe("Structured Graph");
  });

  it("produces correct default payload when node_graph is selected", async () => {
    createDiagramMock.mockResolvedValue({ id: "diag-001" });
    const onCreated = vi.fn();
    const user = userEvent.setup();

    render(
      <DiagramCreateForm onCreated={onCreated} onCancel={vi.fn()} />,
    );

    // Fill in the name
    const nameInput = screen.getByTestId("diagram-name-input") as HTMLInputElement;
    await user.type(nameInput, "Test Graph Diagram");

    // Change format to node_graph
    const formatSelect = screen.getByTestId("diagram-format-select") as HTMLSelectElement;
    await user.selectOptions(formatSelect, "node_graph");

    // Submit the form
    const saveBtn = screen.getByTestId("diagram-save-btn");
    await user.click(saveBtn);

    // Verify the create mutation was called with correct payload
    expect(createDiagramMock).toHaveBeenCalledWith({
      workspace_id: "ws-001",
      name: "Test Graph Diagram",
      diagram_type: "block",
      payload_format: "node_graph",
      content: JSON.stringify({ schema_version: 1, nodes: [], edges: [] }),
      description: "",
    });

    expect(onCreated).toHaveBeenCalledWith("diag-001");
  });
});
