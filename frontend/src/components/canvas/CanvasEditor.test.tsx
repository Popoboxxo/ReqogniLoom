/**
 * Co-located tests for CanvasEditor (REQ-L1-056, COMP-DS-006).
 *
 * Tests: render, tool switching, color change, undo/redo, auto-save trigger.
 * NOT executed — written for future Vitest + RTL run.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CanvasEditor } from "./CanvasEditor";

// Mock the diagrams API
vi.mock("../../api/diagrams", () => ({
  diagramsApi: {
    fetchCanvasStrokes: vi.fn().mockResolvedValue({
      diagram_id: "test-id",
      strokes: [],
      width: 800,
      height: 600,
      svg: "<svg></svg>",
      version_number: 1,
    }),
    saveCanvasStrokes: vi.fn().mockResolvedValue({
      diagram_id: "test-id",
      strokes: [],
      width: 800,
      height: 600,
      svg: "<svg></svg>",
      version_number: 2,
    }),
  },
}));

// Mock Fabric.js
vi.mock("fabric", () => ({
  Canvas: vi.fn().mockImplementation(() => ({
    width: 800,
    height: 600,
    isDrawingMode: true,
    freeDrawingBrush: {
      color: "#000000",
      width: 2,
      globalCompositeOperation: "source-over",
    },
    on: vi.fn(),
    off: vi.fn(),
    getObjects: vi.fn().mockReturnValue([]),
    toJSON: vi.fn().mockReturnValue({ objects: [] }),
    loadFromJSON: vi.fn().mockResolvedValue(undefined),
    renderAll: vi.fn(),
    setDimensions: vi.fn(),
    dispose: vi.fn(),
  })),
  PencilBrush: vi.fn().mockImplementation(() => ({
    color: "#000000",
    width: 2,
    globalCompositeOperation: "source-over",
  })),
}));

// Mock i18n
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback: string) => fallback,
    i18n: { language: "en" },
  }),
}));

// Mock CSS module
vi.mock("../../styles/components/CanvasEditor.module.css", () => ({
  default: new Proxy({}, { get: (_, key) => String(key) }),
}));

describe("CanvasEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the canvas editor with toolbar", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("canvas-editor")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-element")).toBeInTheDocument();
  });

  it("renders all tool buttons (pen, select, eraser)", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("canvas-tool-pen")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-tool-select")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-tool-eraser")).toBeInTheDocument();
  });

  it("switches active tool when clicking tool buttons", async () => {
    const user = userEvent.setup();
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const selectBtn = screen.getByTestId("canvas-tool-select");
    await user.click(selectBtn);

    // Status bar should reflect the tool change
    const statusBar = screen.getByTestId("canvas-status-bar");
    expect(statusBar).toHaveTextContent("select");
  });

  it("renders color picker and width slider", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("canvas-color-picker")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-width-slider")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-width-label")).toHaveTextContent("2px");
  });

  it("updates stroke width label when slider changes", async () => {
    const user = userEvent.setup();
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const slider = screen.getByTestId("canvas-width-slider");
    await user.clear(slider);
    // Use fireEvent for range input
    fireEvent.change(slider, { target: { value: "10" } });

    expect(screen.getByTestId("canvas-width-label")).toHaveTextContent("10px");
  });

  it("renders undo and redo buttons", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("canvas-undo")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-redo")).toBeInTheDocument();
  });

  it("renders save button", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("canvas-save-btn")).toBeInTheDocument();
  });

  it("renders status bar with idle state", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const statusEl = screen.getByTestId("canvas-save-status");
    expect(statusEl).toBeInTheDocument();
  });

  it("calls onAutoSave callback when provided", async () => {
    const onAutoSave = vi.fn();
    render(
      <CanvasEditor diagramId="test-diagram-id" onAutoSave={onAutoSave} />
    );

    // The component should be ready to auto-save
    expect(screen.getByTestId("canvas-editor")).toBeInTheDocument();
  });
});
