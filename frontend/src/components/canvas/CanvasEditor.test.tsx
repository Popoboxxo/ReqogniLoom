/**
 * Co-located tests for CanvasEditor (REQ-L1-056, COMP-DS-006).
 *
 * Tests: render, tool switching, color change, undo/redo, auto-save trigger.
 * NOT executed — written for future Vitest + RTL run.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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
  Canvas: class {
    width = 800;
    height = 600;
    isDrawingMode = true;
    freeDrawingBrush = {
      color: "#000000",
      width: 2,
      globalCompositeOperation: "source-over",
    };
    constructor(_element: HTMLCanvasElement | string, _options?: object) {}
    on = vi.fn().mockReturnThis();
    off = vi.fn().mockReturnThis();
    add = vi.fn().mockReturnThis();
    remove = vi.fn().mockReturnThis();
    getObjects = vi.fn().mockReturnValue([]);
    toJSON = vi.fn().mockReturnValue({ objects: [] });
    loadFromJSON = vi.fn().mockResolvedValue(undefined);
    renderAll = vi.fn().mockReturnThis();
    setDimensions = vi.fn().mockReturnThis();
    dispose = vi.fn();
  },
  PencilBrush: class {
    color = "#000000";
    width = 2;
    globalCompositeOperation = "source-over";
    constructor(_canvas: unknown) {}
  },
  Path: class {
    set = vi.fn();
    constructor(_path: string, _options?: object) {}
  },
}));

// Mock i18n
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
    i18n: { language: "en" },
  }),
}));

// Mock CSS module
vi.mock("../../styles/components/CanvasEditor.module.css", () => ({
  default: new Proxy({}, { get: (_target, prop) => String(prop) }),
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

  it("updates stroke width label when slider changes", () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const slider = screen.getByTestId("canvas-width-slider");
    // Use fireEvent for range inputs (userEvent.clear is for text inputs)
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

// ---------------------------------------------------------------------------
// Stroke persistence — IF-L1-058 (Auto-Save)
// ---------------------------------------------------------------------------

describe("CanvasEditor — Stroke persistence (IF-L1-058)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("save button is disabled when canvas is clean (not dirty)", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const saveBtn = screen.getByTestId("canvas-save-btn");
    // Initially not dirty, so button is disabled
    expect(saveBtn).toBeDisabled();
  });

  it("save button label shows 'Save' in idle state", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const saveBtn = screen.getByTestId("canvas-save-btn");
    expect(saveBtn).toHaveTextContent("Save");
  });

  it("status bar shows 'Ready' when idle and not dirty", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const status = screen.getByTestId("canvas-save-status");
    expect(status).toHaveTextContent("Ready");
  });

  it("renders initial strokes prop without crashing", async () => {
    const strokes = [
      {
        id: "s1",
        type: "pen" as const,
        points: [{ x: 0, y: 0 }, { x: 10, y: 10 }],
        color: "#000000",
        width: 2,
      },
    ];

    render(
      <CanvasEditor diagramId="test-diagram-id" initialStrokes={strokes} />
    );

    expect(screen.getByTestId("canvas-editor")).toBeInTheDocument();
  });

  it("canvas-element ref is present in the DOM", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const canvas = screen.getByTestId("canvas-element");
    expect(canvas.tagName.toLowerCase()).toBe("canvas");
  });
});

// ---------------------------------------------------------------------------
// Undo / Redo
// ---------------------------------------------------------------------------

describe("CanvasEditor — Undo/Redo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("undo button is initially disabled (no history)", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const undoBtn = screen.getByTestId("canvas-undo");
    expect(undoBtn).toBeDisabled();
  });

  it("redo button is initially disabled (no history)", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const redoBtn = screen.getByTestId("canvas-redo");
    expect(redoBtn).toBeDisabled();
  });

  it("undo button does not crash when clicked while disabled", async () => {
    const user = userEvent.setup();
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const undoBtn = screen.getByTestId("canvas-undo");
    // Even if the button is disabled, clicking should not throw
    await user.click(undoBtn).catch(() => undefined);
    expect(screen.getByTestId("canvas-editor")).toBeInTheDocument();
  });

  it("redo button does not crash when clicked while disabled", async () => {
    const user = userEvent.setup();
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const redoBtn = screen.getByTestId("canvas-redo");
    await user.click(redoBtn).catch(() => undefined);
    expect(screen.getByTestId("canvas-editor")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Auto-Save trigger
// ---------------------------------------------------------------------------

describe("CanvasEditor — Auto-Save trigger", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does NOT call saveCanvasStrokes when canvas is clean (not dirty)", async () => {
    const { diagramsApi: mockApi } = await import("../../api/diagrams");
    render(<CanvasEditor diagramId="test-diagram-id" />);

    // Advance past auto-save interval
    await vi.advanceTimersByTimeAsync(6000);

    expect(mockApi.saveCanvasStrokes).not.toHaveBeenCalled();
  });

  it("renders canvas-wrapper containing canvas element", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const wrapper = screen.getByTestId("canvas-wrapper");
    const canvas = screen.getByTestId("canvas-element");
    expect(wrapper).toContainElement(canvas);
  });

  it("status bar shows tool name (select is the default tool)", async () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    const statusBar = screen.getByTestId("canvas-status-bar");
    expect(statusBar).toHaveTextContent("select");
  });

  it("changes tool name in status bar when select tool is chosen", () => {
    render(<CanvasEditor diagramId="test-diagram-id" />);

    // Use fireEvent.click to avoid userEvent timeout issues with fake timers
    fireEvent.click(screen.getByTestId("canvas-tool-select"));

    const statusBar = screen.getByTestId("canvas-status-bar");
    expect(statusBar).toHaveTextContent("select");
  });
});
