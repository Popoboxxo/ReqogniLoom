/**
 * DiagramDetailView — preview instead of inline edit (Phase 6 / decision E2-D4).
 *
 * req_id: REQ-L2-DS-001, REQ-L1-057, REQ-L2-DS-006
 *
 * Three behaviours the decision hinges on:
 *   - canvas diagrams show the SERVER-RENDERED SVG export read-only; the
 *     editable Fabric surface must NOT be mounted in the overview pane;
 *   - the primary action navigates to the matching fullscreen editor route
 *     (D3) instead of turning the pane into a form;
 *   - formats with no fullscreen editor (plantuml/json) keep their inline
 *     source editor — dropping it would remove the only way to edit them.
 *
 * `useDiagramDetail` is mocked rather than the REST layer: this file is about
 * what the presenter renders for a given detail row, and the query wiring is
 * already covered by the DiagramView smoke tests.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import type { DiagramDetail } from "../../types";
import type { DiagramDetailData } from "./useDiagramData";

vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => (typeof fallbackOrOptions === "string" ? fallbackOrOptions : key);
  return { useTranslation: () => ({ t }) };
});

// The canvas editor must never be reached from this pane; if a regression
// mounts it again, this stub makes it visible instead of silently working.
vi.mock("../canvas/CanvasEditor", () => ({
  CanvasEditor: () => <div data-testid="canvas-editor-mounted" />,
}));
vi.mock("../shared/ArtifactInspector", () => ({
  RightSidebar: () => <aside data-testid="right-sidebar" />,
}));
vi.mock("../WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));

const useDiagramDetailMock = vi.fn();
vi.mock("./useDiagramData", () => ({
  useDiagramDetail: (id: string) => useDiagramDetailMock(id),
}));

import { DiagramDetailView } from "./DiagramDetailView";

const DIAGRAM_ID = "diag-001";

function detailRow(over: Partial<DiagramDetail>): DiagramDetail {
  return {
    id: DIAGRAM_ID,
    name: "Power Distribution",
    diagram_type: "block",
    description: "",
    current_version: null,
    created_at: "2026-02-01T10:00:00Z",
    version_count: 1,
    payload_format: "mermaid",
    content: "graph TD\n A --> B",
    version_number: 3,
    ...over,
  } as DiagramDetail;
}

function hookResult(over: Partial<DiagramDetailData>): DiagramDetailData {
  return {
    detail: detailRow({}),
    isLoading: false,
    canvasSvg: undefined,
    isCanvasLoading: false,
    saveContent: vi.fn(),
    deleteDiagram: vi.fn(),
    isSaving: false,
    saveError: null,
    resetSaveError: vi.fn(),
    ...over,
  };
}

function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

const renderDetail = () =>
  render(
    <MemoryRouter initialEntries={[`/diagrams/${DIAGRAM_ID}`]}>
      <LocationProbe />
      <Routes>
        <Route
          path="/diagrams/:id"
          element={
            <DiagramDetailView
              diagramId={DIAGRAM_ID}
              onBack={vi.fn()}
              onChanged={vi.fn()}
            />
          }
        />
        <Route path="/diagrams/:id/canvas" element={<div>canvas route</div>} />
        <Route path="/diagrams/:id/mermaid" element={<div>mermaid route</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe("DiagramDetailView preview (E2-D4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the server-rendered SVG for a canvas diagram, without mounting the editor", () => {
    useDiagramDetailMock.mockReturnValue(
      hookResult({
        detail: detailRow({ payload_format: "canvas_stroke", content: null }),
        canvasSvg: '<svg data-testid="server-svg"><rect /></svg>',
      }),
    );

    renderDetail();

    expect(screen.getByTestId("diagram-canvas-svg")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-canvas-svg").querySelector("svg")).not.toBeNull();
    expect(screen.queryByTestId("canvas-editor-mounted")).not.toBeInTheDocument();
  });

  it("falls back to an empty-canvas hint when the export carries no SVG", () => {
    useDiagramDetailMock.mockReturnValue(
      hookResult({
        detail: detailRow({ payload_format: "canvas_stroke", content: null }),
        canvasSvg: undefined,
      }),
    );

    renderDetail();

    expect(screen.getByText("This canvas is still empty.")).toBeInTheDocument();
    expect(screen.queryByTestId("diagram-canvas-svg")).not.toBeInTheDocument();
  });

  it("navigates a canvas diagram to the fullscreen canvas route", async () => {
    useDiagramDetailMock.mockReturnValue(
      hookResult({ detail: detailRow({ payload_format: "canvas_stroke" }) }),
    );
    const user = userEvent.setup();

    renderDetail();
    await user.click(screen.getByTestId("diagram-open-editor-btn"));

    expect(screen.getByTestId("location")).toHaveTextContent(
      `/diagrams/${DIAGRAM_ID}/canvas`,
    );
  });

  it("navigates a mermaid diagram to the fullscreen mermaid route instead of editing inline", async () => {
    useDiagramDetailMock.mockReturnValue(
      hookResult({ detail: detailRow({ payload_format: "mermaid" }) }),
    );
    const user = userEvent.setup();

    renderDetail();
    // No inline "Edit Source" affordance for a format that owns an editor.
    expect(screen.queryByTestId("diagram-edit-btn")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("diagram-open-editor-btn"));

    expect(screen.getByTestId("location")).toHaveTextContent(
      `/diagrams/${DIAGRAM_ID}/mermaid`,
    );
  });

  it("keeps the inline source editor for formats with no fullscreen editor", async () => {
    useDiagramDetailMock.mockReturnValue(
      hookResult({
        detail: detailRow({ payload_format: "plantuml", content: "@startuml\n@enduml" }),
      }),
    );
    const user = userEvent.setup();

    renderDetail();

    expect(screen.queryByTestId("diagram-open-editor-btn")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("diagram-edit-btn"));
    expect(screen.getByTestId("diagram-source-textarea")).toBeInTheDocument();
  });
});
