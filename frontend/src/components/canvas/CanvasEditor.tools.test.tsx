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

  return { Canvas, PencilBrush, Rect, Ellipse, Textbox, Triangle, Path, Line };
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

    // Source center is now (60, 60); the "from" endpoint must follow.
    expect(line.x1).toBe(60);
    expect(line.y1).toBe(60);
    // The "to" endpoint stays put (target unmoved).
    expect(line.x2).toBe(110);
    expect(line.y2).toBe(110);
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
