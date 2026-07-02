/**
 * Minimal Fabric.js v6 type stub for TypeScript resolution.
 *
 * fabric is dynamically imported in CanvasEditor (REQ-L2-DS-006).
 * The full type package ships with fabric@6 — this stub is only needed
 * until `npm install` is run inside the Docker container.
 */

declare module "fabric" {
  export class Canvas {
    width: number | undefined;
    height: number | undefined;
    isDrawingMode: boolean;
    selection: boolean;
    freeDrawingBrush: PencilBrush | null;
    backgroundColor: string;

    constructor(element: HTMLCanvasElement | string, options?: object);

    on(event: string, handler: () => void): this;
    off(event: string, handler?: () => void): this;
    getObjects(): object[];
    toJSON(): object;
    loadFromJSON(json: object): Promise<this>;
    renderAll(): this;
    setDimensions(dims: { width: number; height: number }): this;
    dispose(): void;
    add(...objects: object[]): this;
  }

  export class PencilBrush {
    color: string;
    width: number;
    globalCompositeOperation: string;

    constructor(canvas: Canvas);
  }

  export class Path {
    constructor(path: string, options?: object);
  }
}
