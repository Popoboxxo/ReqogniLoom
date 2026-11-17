/**
 * Minimal Fabric.js type stub for TypeScript resolution.
 *
 * fabric is dynamically imported in CanvasEditor (REQ-L2-DS-006).
 *
 * TODO(FE-006, tracked follow-up): the installed fabric@7.4.0 DOES ship its own
 * typings, but they cannot replace this stub yet — removing it makes
 * `tsc -p tsconfig.build.json --noEmit` fail with 18 errors in CanvasEditor.tsx
 * (`getPointer`/`findTarget` no longer exist in v7, `TMat2D`/`TPointerEvent`
 * and object option types are stricter). Migrate CanvasEditor to the fabric 7
 * API first, then delete this file and verify tsc. Keeping the stub preserves
 * a green build; it is not a missing-dependency workaround.
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
