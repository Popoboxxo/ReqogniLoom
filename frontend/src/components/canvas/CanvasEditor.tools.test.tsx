/**
 * Co-located tests for the CanvasEditor shape / text / connector tools.
 *
 * Covers REQ-L2-CV-001 (rect), REQ-L2-CV-004 (connector follow) and
 * REQ-L2-CV-005 (Fabric serialization round-trip / restore).
 *
 * Uses a richer Fabric.js mock than CanvasEditor.test.tsx: it implements a
 * minimal event bus and object store so custom mouse handlers can be exercised.
 * The pre-existing suite keeps its own lightweight mock — this file is additive.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CanvasEditor } from "./CanvasEditor";

// Shared registry of created canvas instances, hoisted so the vi.mock factory
// and the test bodies reference the same array.
const hoisted = vi.hoisted(() => {
  return { instances: [] as MockCanvasType[] };
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyProps = Record<string, any>;

interface MockCanvasType {
  _objects: AnyProps[];
  _handlers: Record<string, Array<(e: unknown) => void>>;
  _pointer: { x: number; y: number };
  _target: AnyProps | null;
  _active: AnyProps[];
  _loaded: unknown;
  on(evt: string, cb: (e: unknown) => void): void;
  add(o: AnyProps): void;
  getObjects(): AnyProps[];
  trigger(evt: string, e: unknown): void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

vi.mock("../../api/diagrams", () => ({
  diagramsApi: {
    fetchCanvasStrokes: vi.fn().mockResolvedValue({ strokes: [] }),
    saveCanvasStrokes: vi.fn().mockResolvedValue({ version_number: 2 }),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
    i18n: { language: "en" },
  }),
}));

vi.mock("../../styles/components/CanvasEditor.module.css", () => ({
  default: new Proxy({}, { get: (_t, prop) => String(prop) }),
}));

vi.mock("fabric", () => {
  class FabricObject {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    constructor(props: AnyProps = {}) {
      Object.assign(this, props);
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    set(p: AnyProps): this {
      Object.assign(this, p);
      return this;
    }
    setCoords(): void {}
    enterEditing(): void {}
    selectAll(): void {}
    getBoundingRect(): { left: number; top: number; width: number; height: number } {
      const self = this as unknown as AnyProps;
      return {
        left: self.left ?? 0,
        top: self.top ?? 0,
        width: self.width ?? 0,
        height: self.height ?? 0,
      };
    }
  }
  class Rect extends FabricObject {}
  class Ellipse extends FabricObject {}
  class Textbox extends FabricObject {
    constructor(text: string, props: AnyProps = {}) {
      super(props);
      (this as unknown as AnyProps).text = text;
    }
  }
  class Triangle extends FabricObject {}
  class Path extends FabricObject {}
  class Line extends FabricObject {
    constructor(points: number[], props: AnyProps = {}) {
      super(props);
      const self = this as unknown as AnyProps;
      self.x1 = points[0];
      self.y1 = points[1];
      self.x2 = points[2];
      self.y2 = points[3];
    }
  }
  class Shadow {
    constructor(props: AnyProps = {}) {
      Object.assign(this, props);
    }
  }
  class PencilBrush {
    color = "#000000";
    width = 2;
    globalCompositeOperation = "source-over";
  }

  class Canvas implements MockCanvasType {
    width = 800;
    height = 600;
    isDrawingMode = true;
    selection = false;
    freeDrawingBrush = new PencilBrush();
    _objects: AnyProps[] = [];
    _handlers: Record<string, Array<(e: unknown) => void>> = {};
    _pointer = { x: 0, y: 0 };
    _target: AnyProps | null = null;
    _active: AnyProps[] = [];
    _loaded: unknown = null;

    constructor() {
      hoisted.instances.push(this);
    }
    on(evt: string, cb: (e: unknown) => void): void {
      (this._handlers[evt] ||= []).push(cb);
    }
    off(): void {}
    add(o: AnyProps): void {
      this._objects.push(o);
      (this._handlers["object:added"] || []).forEach((h) => h({ target: o }));
    }
    remove(o: AnyProps): void {
      this._objects = this._objects.filter((x) => x !== o);
    }
    getObjects(): AnyProps[] {
      return this._objects;
    }
    getPointer(): { x: number; y: number } {
      return this._pointer;
    }
    findTarget(): AnyProps | null {
      return this._target;
    }
    setActiveObject(o: AnyProps): void {
      this._active = [o];
    }
    getActiveObject(): AnyProps | null {
      return this._active[0] ?? null;
    }
    getActiveObjects(): AnyProps[] {
      return this._active;
    }
    discardActiveObject(): void {
      this._active = [];
    }
    toJSON(): { objects: AnyProps[] } {
      return { objects: this._objects };
    }
    loadFromJSON(json: unknown, cb?: () => void): Promise<void> {
      this._loaded = json;
      cb?.();
      return Promise.resolve();
    }
    renderAll(): void {}
    setDimensions(): void {}
    dispose(): void {}
    trigger(evt: string, e: unknown): void {
      (this._handlers[evt] || []).forEach((h) => h(e));
    }
  }

  return { Canvas, PencilBrush, Rect, Ellipse, Textbox, Triangle, Path, Line, Shadow };
});

// Grab the latest canvas instance once the async init has run.
async function latestCanvas(): Promise<MockCanvasType> {
  await waitFor(() => expect(hoisted.instances.length).toBeGreaterThan(0));
  const canvas = hoisted.instances[hoisted.instances.length - 1];
  await waitFor(() => expect(canvas._handlers["mouse:down"]).toBeDefined());
  return canvas;
}

describe("CanvasEditor — shape tools (REQ-L2-CV-001)", () => {
  beforeEach(() => {
    hoisted.instances.length = 0;
    vi.clearAllMocks();
  });

  it("adds a fabric.Rect when the rect tool is active and mouse events fire", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    fireEvent.click(screen.getByTestId("canvas-tool-rect"));

    canvas._pointer = { x: 10, y: 10 };
    canvas.trigger("mouse:down", { e: {} });
    canvas._pointer = { x: 60, y: 40 };
    canvas.trigger("mouse:move", { e: {} });
    canvas.trigger("mouse:up", { e: {} });

    const rects = canvas.getObjects().filter((o) => o instanceof fabric.Rect);
    expect(rects).toHaveLength(1);
    expect(rects[0].width).toBe(50);
    expect(rects[0].height).toBe(30);
    expect(rects[0].selectable).toBe(true);
  });

  it("adds a fabric.Ellipse when the ellipse tool is active and mouse events fire", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    fireEvent.click(screen.getByTestId("canvas-tool-ellipse"));

    canvas._pointer = { x: 20, y: 20 };
    canvas.trigger("mouse:down", { e: {} });
    canvas._pointer = { x: 80, y: 60 };
    canvas.trigger("mouse:move", { e: {} });
    canvas.trigger("mouse:up", { e: {} });

    const ellipses = canvas.getObjects().filter((o) => o instanceof fabric.Ellipse);
    expect(ellipses).toHaveLength(1);
    expect(ellipses[0].rx).toBe(30); // (80 - 20) / 2
    expect(ellipses[0].ry).toBe(20); // (60 - 20) / 2
    expect(ellipses[0].selectable).toBe(true);
  });

  it("adds a fabric.Textbox when the text tool is active and mouse down fires", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    fireEvent.click(screen.getByTestId("canvas-tool-text"));

    canvas._pointer = { x: 100, y: 100 };
    canvas.trigger("mouse:down", { e: {} });

    const textboxes = canvas.getObjects().filter((o) => o instanceof fabric.Textbox);
    expect(textboxes).toHaveLength(1);
    expect(textboxes[0].left).toBe(100);
    expect(textboxes[0].top).toBe(100);
    expect(textboxes[0].editable).toBe(true);
  });
});

describe("CanvasEditor — connector follow (REQ-L2-CV-004)", () => {
  beforeEach(() => {
    hoisted.instances.length = 0;
    vi.clearAllMocks();
  });

  it("updates connector endpoints when an anchored shape moves", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    const source = new fabric.Rect({ left: 0, top: 0, width: 20, height: 20, data: { id: "A" } });
    const target = new fabric.Rect({ left: 100, top: 100, width: 20, height: 20, data: { id: "B" } });
    const line = new fabric.Line([10, 10, 110, 110], {
      data: { type: "connector", id: "L1", fromId: "A", toId: "B" },
    });
    canvas._objects.push(source, target, line);

    // Move the source shape and fire the moving event.
    source.set({ left: 50, top: 50 });
    canvas.trigger("object:moving", { target: source });

    // Source center is now (60, 60); the "from" endpoint must follow, clipped to edge (70, 70).
    expect(line.x1).toBe(70);
    expect(line.y1).toBe(70);
    // The "to" endpoint is re-clipped onto the target edge facing the new
    // source position: target center (110, 110) minus half-extent 10.
    expect(line.x2).toBe(100);
    expect(line.y2).toBe(100);
  });
});

describe("CanvasEditor — drag-to-connect traces (REQ-L2-CV-004)", () => {
  beforeEach(() => {
    hoisted.instances.length = 0;
    vi.clearAllMocks();
  });

  it("creates a connector with arrowhead by dragging from source to target", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    const source = new fabric.Rect({
      left: 0, top: 0, width: 20, height: 20, selectable: true,
      data: { id: "A", type: "rect" },
    }) as unknown as AnyProps;
    const target = new fabric.Rect({
      left: 100, top: 100, width: 20, height: 20, selectable: true,
      data: { id: "B", type: "rect" },
    }) as unknown as AnyProps;
    canvas._objects.push(source, target);

    fireEvent.click(screen.getByTestId("canvas-tool-connector"));

    // Press on the source node, drag to the target node, release.
    canvas._target = source;
    canvas._pointer = { x: 10, y: 10 };
    canvas.trigger("mouse:down", { e: {} });

    canvas._pointer = { x: 110, y: 110 };
    canvas._target = target;
    canvas.trigger("mouse:move", { e: {} });
    canvas.trigger("mouse:up", { e: {} });

    const connectors = canvas.getObjects().filter((o) => o.data?.type === "connector");
    expect(connectors).toHaveLength(1);
    expect(connectors[0].data.fromId).toBe("A");
    expect(connectors[0].data.toId).toBe("B");
    // Endpoints are clipped to the bounding-box edges of both nodes.
    expect(connectors[0].x1).toBe(20);
    expect(connectors[0].y1).toBe(20);
    expect(connectors[0].x2).toBe(100);
    expect(connectors[0].y2).toBe(100);

    const heads = canvas.getObjects().filter((o) => o.data?.type === "arrowHead");
    expect(heads).toHaveLength(1);
    expect(heads[0].data.connectorId).toBe(connectors[0].data.id);

    // The live preview line must be gone after the gesture completes.
    const previews = canvas.getObjects().filter((o) => o.data?.type === "connectorPreview");
    expect(previews).toHaveLength(0);
  });

  it("does not create a connector when released over empty canvas", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    const source = new fabric.Rect({
      left: 0, top: 0, width: 20, height: 20, selectable: true,
      data: { id: "A", type: "rect" },
    }) as unknown as AnyProps;
    canvas._objects.push(source);

    fireEvent.click(screen.getByTestId("canvas-tool-connector"));

    canvas._target = source;
    canvas._pointer = { x: 10, y: 10 };
    canvas.trigger("mouse:down", { e: {} });

    canvas._target = null;
    canvas._pointer = { x: 200, y: 200 };
    canvas.trigger("mouse:move", { e: {} });
    canvas.trigger("mouse:up", { e: {} });

    expect(canvas.getObjects().filter((o) => o.data?.type === "connector")).toHaveLength(0);
    expect(canvas.getObjects().filter((o) => o.data?.type === "connectorPreview")).toHaveLength(0);
  });
});

describe("CanvasEditor — node labels", () => {
  beforeEach(() => {
    hoisted.instances.length = 0;
    vi.clearAllMocks();
  });

  it("adds a centered editable label on double-click of a shape", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    const shape = new fabric.Rect({
      left: 0, top: 0, width: 100, height: 60,
      data: { id: "S1", type: "rect" },
    }) as unknown as AnyProps;
    canvas._objects.push(shape);

    canvas.trigger("mouse:dblclick", { target: shape });

    const labels = canvas.getObjects().filter((o) => o.data?.type === "label");
    expect(labels).toHaveLength(1);
    expect(labels[0].data.labelFor).toBe("S1");
    expect(labels[0].left).toBe(50);
    expect(labels[0].top).toBe(30);
  });

  it("re-centers the label when its shape moves", async () => {
    const fabric = await import("fabric");
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    const shape = new fabric.Rect({
      left: 0, top: 0, width: 100, height: 60,
      data: { id: "S1", type: "rect" },
    }) as unknown as AnyProps;
    canvas._objects.push(shape);
    canvas.trigger("mouse:dblclick", { target: shape });

    shape.set({ left: 200, top: 100 });
    canvas.trigger("object:moving", { target: shape });

    const label = canvas.getObjects().find((o) => o.data?.type === "label") as AnyProps;
    expect(label.left).toBe(250);
    expect(label.top).toBe(130);
  });
});

describe("CanvasEditor — Fabric serialization (REQ-L2-CV-005)", () => {
  beforeEach(() => {
    hoisted.instances.length = 0;
    vi.clearAllMocks();
  });

  it("restores initialCanvasJson via loadFromJSON on init", async () => {
    const initialCanvasJson = { objects: [{ type: "rect", left: 1, top: 2 }], version: "6.0.0" };
    render(<CanvasEditor diagramId="d1" initialCanvasJson={initialCanvasJson} />);
    const canvas = await latestCanvas();

    await waitFor(() => expect(canvas._loaded).toBe(initialCanvasJson));
  });

  it("round-trips: toJSON() output can be loaded back via loadFromJSON", async () => {
    render(<CanvasEditor diagramId="d1" />);
    const canvas = await latestCanvas();

    const snapshot = canvas.toJSON();
    let done = false;
    await canvas.loadFromJSON(snapshot, () => {
      done = true;
    });

    expect(done).toBe(true);
    expect(canvas._loaded).toBe(snapshot);
  });
});
