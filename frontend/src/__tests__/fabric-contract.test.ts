/**
 * Contract test for the fabric mock alias (REQ-097 — DEEP_SYSTEM_ANALYSIS.md FE-20).
 *
 * Problem this guards against:
 *   The fabric stub in `src/__mocks__/fabric.ts` is only wired in via the Vitest
 *   `resolve.alias` (see vite.config.ts). Production type-checking and the app
 *   bundle use the REAL `fabric` package, while unit tests use this stub. That
 *   divergence is invisible — if the mock drifts from the real API (a renamed
 *   export, a dropped method, a changed constructor arg), tests keep passing
 *   against a fiction while production breaks.
 *
 * What this test locks down:
 *   1. Runtime structure — the stub actually exposes the constructors,
 *      methods and properties that CanvasEditor (COMP-RF-005) calls at runtime.
 *      Fails loudly (in `vitest run`) if the mock loses a member.
 *   2. Type-level contract — the stub's classes AND the real `fabric` package
 *      both satisfy the used API subset, and the real package still exports the
 *      names the stub mirrors. `import type` is erased at runtime, so this never
 *      loads real fabric (which needs a browser canvas), yet `tsc` / `npm run
 *      build` fails if the real package drifts away from the used surface.
 *
 * This is a structural/contract check, not a rendering test.
 */

import { describe, it, expect } from "vitest";

// The stub under test. Imported via a relative path so it is used directly,
// independent of the Vitest `fabric` alias.
import {
  Canvas as MockCanvas,
  PencilBrush as MockPencilBrush,
  Path as MockPath,
} from "../__mocks__/fabric";

// Types from the REAL fabric package. `import type` is compile-time only and is
// erased from the emitted JS, so real fabric is never loaded at runtime.
import type {
  Canvas as RealCanvas,
  PencilBrush as RealPencilBrush,
  Path as RealPath,
} from "fabric";

// ---------------------------------------------------------------------------
// Used API subset — the exact fabric surface CanvasEditor.tsx relies on.
//
// Kept intentionally loose (`unknown` returns, `...args: any[]`) so the real,
// heavily-overloaded fabric signatures remain assignable to it. The contract is
// about *presence and callability* of the used members, not their exact
// generic shapes.
// ---------------------------------------------------------------------------

interface UsedCanvasApi {
  isDrawingMode: boolean;
  freeDrawingBrush?: unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  on(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  off(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getObjects(...args: any[]): unknown[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toJSON(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  loadFromJSON(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  renderAll(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setDimensions(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dispose(...args: any[]): unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  add(...args: any[]): unknown;
}

interface UsedPencilBrushApi {
  color: string;
  width: number;
  globalCompositeOperation: string;
}

/**
 * Compile-time assertion helper: the call only type-checks when `value` is
 * assignable to `Expected`. A no-op at runtime.
 */
function expectAssignable<Expected>(_value: Expected): void {
  /* type-level only */
}

describe("fabric mock contract (REQ-097)", () => {
  // -------------------------------------------------------------------------
  // Type-level: the real fabric package still satisfies the used subset.
  // These fail `tsc` (not `vitest run`) if the real API drifts.
  // -------------------------------------------------------------------------
  it("real fabric exposes the used Canvas / PencilBrush / Path surface (type-level)", () => {
    expectAssignable<UsedCanvasApi>(null as unknown as RealCanvas);
    expectAssignable<UsedPencilBrushApi>(null as unknown as RealPencilBrush);
    // Real Path must still be constructible from an SVG path string + options,
    // exactly how loadStrokesToCanvas() builds pen strokes.
    expectAssignable<(path: string, options?: object) => RealPath>(
      (path, options) => new (null as unknown as typeof RealPath)(path, options)
    );
    expect(true).toBe(true);
  });

  // -------------------------------------------------------------------------
  // Type-level: the mock satisfies the same used subset the real package does.
  // -------------------------------------------------------------------------
  it("mock satisfies the used Canvas / PencilBrush surface (type-level)", () => {
    const el = document.createElement("canvas");
    expectAssignable<UsedCanvasApi>(new MockCanvas(el));
    expectAssignable<UsedPencilBrushApi>(new MockPencilBrush(new MockCanvas(el)));
    expect(true).toBe(true);
  });

  // -------------------------------------------------------------------------
  // Runtime: the mock exports the constructors the codebase imports.
  // -------------------------------------------------------------------------
  it("exports Canvas, PencilBrush and Path as constructors", () => {
    expect(typeof MockCanvas).toBe("function");
    expect(typeof MockPencilBrush).toBe("function");
    expect(typeof MockPath).toBe("function");
  });

  // -------------------------------------------------------------------------
  // Runtime: Canvas mock accepts the app's construction and exposes every
  // method CanvasEditor.tsx invokes.
  // -------------------------------------------------------------------------
  it("Canvas mock exposes the methods used by CanvasEditor", () => {
    const el = document.createElement("canvas");
    const canvas = new MockCanvas(el, { width: 800, height: 600 });

    // Methods called in CanvasEditor.tsx (undo/redo, autosave, connectors, init).
    const usedMethods = [
      "on",
      "off",
      "getObjects",
      "toJSON",
      "loadFromJSON",
      "renderAll",
      "setDimensions",
      "dispose",
      "add",
    ] as const;
    for (const method of usedMethods) {
      expect(typeof (canvas as unknown as Record<string, unknown>)[method]).toBe("function");
    }

    // Properties read/written by CanvasEditor.tsx.
    expect(canvas).toHaveProperty("isDrawingMode");
    expect(canvas).toHaveProperty("freeDrawingBrush");

    // loadFromJSON is awaited in the component, so it must be thenable.
    expect(canvas.loadFromJSON({ objects: [] })).toBeInstanceOf(Promise);
    // toJSON accepts the property allowlist the component passes (["data"]).
    expect(canvas.toJSON()).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Runtime: PencilBrush mock is built from a Canvas and carries the three
  // brush properties the pen/eraser tools mutate.
  // -------------------------------------------------------------------------
  it("PencilBrush mock exposes color, width and globalCompositeOperation", () => {
    const canvas = new MockCanvas(document.createElement("canvas"));
    const brush = new MockPencilBrush(canvas);

    expect(brush).toHaveProperty("color");
    expect(brush).toHaveProperty("width");
    expect(brush).toHaveProperty("globalCompositeOperation");

    // The eraser tool flips this to "destination-out" — must be writable.
    brush.globalCompositeOperation = "destination-out";
    expect(brush.globalCompositeOperation).toBe("destination-out");
  });

  // -------------------------------------------------------------------------
  // Runtime: Path mock is constructed from an SVG path string + options,
  // matching loadStrokesToCanvas().
  // -------------------------------------------------------------------------
  it("Path mock is constructible from an SVG path string and options", () => {
    const path = new MockPath("M 0 0 L 10 10", {
      stroke: "#000000",
      strokeWidth: 2,
      fill: "transparent",
    });
    expect(path).toBeInstanceOf(MockPath);
  });
});
