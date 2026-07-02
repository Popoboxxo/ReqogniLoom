/**
 * Manual Vitest stub for fabric@6 — used in unit tests only.
 *
 * Provides the minimal surface used by CanvasEditor (COMP-RF-005):
 * Canvas, PencilBrush, Path.
 *
 * Tests that need more fine-grained control override this via vi.mock().
 */

export class Canvas {
  width = 800;
  height = 600;
  isDrawingMode = true;
  selection = false;
  backgroundColor = "#ffffff";
  freeDrawingBrush: PencilBrush | null = null;

  constructor(_element: HTMLCanvasElement | string, _options?: object) {}

  on(_event: string, _handler: () => void): this { return this; }
  off(_event: string, _handler?: () => void): this { return this; }
  getObjects(): object[] { return []; }
  toJSON(): object { return { objects: [] }; }
  async loadFromJSON(_json: object): Promise<this> { return this; }
  renderAll(): this { return this; }
  setDimensions(_dims: { width: number; height: number }): this { return this; }
  dispose(): void {}
  add(..._objects: object[]): this { return this; }
}

export class PencilBrush {
  color = "#000000";
  width = 2;
  globalCompositeOperation = "source-over";

  constructor(_canvas: Canvas) {}
}

export class Path {
  constructor(_path: string, _options?: object) {}
}
