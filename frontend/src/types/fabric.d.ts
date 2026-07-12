/**
 * Minimal Fabric.js v6 type stub for TypeScript resolution.
 *
 * fabric is dynamically imported in CanvasEditor (REQ-L2-DS-006).
 * The full type package ships with fabric@6 — this stub is only needed
 * until `npm install` is run inside the Docker container.
 */

declare module "fabric" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type AnyProps = Record<string, any>;

  export class Canvas {
    width: number | undefined;
    height: number | undefined;
    isDrawingMode: boolean;
    selection: boolean;
    freeDrawingBrush: PencilBrush | null;
    backgroundColor: string;
    defaultCursor: string;
    viewportTransform: number[] | undefined;

    constructor(element: HTMLCanvasElement | string, options?: object);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    on(event: string, handler: (opt: any) => void): this;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    off(event: string, handler?: (opt: any) => void): this;
    getObjects(): AnyProps[];
    toJSON(propertiesToInclude?: string[]): object;
    loadFromJSON(json: object, callback?: () => void): Promise<this>;
    renderAll(): this;
    requestRenderAll(): this;
    setDimensions(dims: { width: number; height: number }): this;
    setViewportTransform(vt: number[]): this;
    dispose(): void;
    add(...objects: object[]): this;
    remove(...objects: object[]): this;
    getPointer(e: Event, ignoreVpt?: boolean): { x: number; y: number };
    findTarget(e: Event): AnyProps | undefined;
    setActiveObject(obj: object): this;
    getActiveObject(): AnyProps | null;
    getActiveObjects(): AnyProps[];
    discardActiveObject(): this;
  }

  export class PencilBrush {
    color: string;
    width: number;
    globalCompositeOperation: string;

    constructor(canvas: Canvas);
  }

  class FabricObject {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    [key: string]: any;
    constructor(options?: object);
    set(props: object): this;
    setCoords(): void;
    getBoundingRect(absolute?: boolean): {
      left: number;
      top: number;
      width: number;
      height: number;
    };
  }

  export class Path extends FabricObject {
    constructor(path: string, options?: object);
  }

  export class Rect extends FabricObject {}
  export class Ellipse extends FabricObject {}
  export class Triangle extends FabricObject {}

  export class Line extends FabricObject {
    constructor(points: number[], options?: object);
  }

  export class Textbox extends FabricObject {
    constructor(text: string, options?: object);
    enterEditing(): void;
    selectAll(): void;
  }

  export class Shadow {
    constructor(options?: object);
  }
}
