/**
 * ARCH-L1-001 ReactFrontend — CanvasEditor geometry & persistence helpers.
 *
 * leaf_id: COMP-RF-005 (CanvasEditor)
 * req_id:  REQ-L2-CV-004 (connector anchoring), REQ-L2-DS-006 (CanvasEditor),
 *          IF-L1-058 / IF-L1-060 (stroke persistence),
 *          REQ-050 (Container/Presenter decomposition — pure-helper extraction)
 *
 * Pure Fabric.js geometry and stroke-serialization helpers extracted verbatim
 * from the former monolithic CanvasEditor. No React / component state — just
 * math and canvas-object mapping, so they are trivially unit-testable.
 */

import type { CanvasStroke, CanvasStrokeData } from "../../types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FabricCanvas = any;

/** Generate a stable per-object id for connector anchoring (REQ-L2-CV-004). */
export function makeObjectId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Set the viewport zoom while keeping the given screen point stationary. */
export function zoomViewportAt(canvas: FabricCanvas, zoom: number, x: number, y: number): void {
  const current = canvas.viewportTransform as number[] | undefined;
  if (!current) return;
  const vt = current.slice();
  const prev = vt[0] || 1;
  vt[0] = zoom;
  vt[3] = zoom;
  vt[4] = x - ((x - vt[4]) * zoom) / prev;
  vt[5] = y - ((y - vt[5]) * zoom) / prev;
  if (typeof canvas.setViewportTransform === "function") {
    canvas.setViewportTransform(vt);
  } else {
    canvas.viewportTransform = vt;
  }
}

/**
 * Bounding-box rect of a Fabric object. Prefers getBoundingRect(true) and falls
 * back to left/top + width/height for lightweight/mocked objects.
 */
export function boundingRect(
  obj: Record<string, unknown>
): { left: number; top: number; width: number; height: number } {
  if (typeof obj.getBoundingRect === "function") {
    return (obj.getBoundingRect as (absolute?: boolean) => {
      left: number;
      top: number;
      width: number;
      height: number;
    })(true);
  }
  return {
    left: (obj.left as number) ?? 0,
    top: (obj.top as number) ?? 0,
    width: (obj.width as number) ?? 0,
    height: (obj.height as number) ?? 0,
  };
}

/** Returns the point on the axis-aligned bounding box edge in direction of (tx, ty) from center (cx, cy). */
export function getEdgePoint(
  cx: number, cy: number,
  halfW: number, halfH: number,
  tx: number, ty: number
): { x: number; y: number } {
  const dx = tx - cx;
  const dy = ty - cy;
  if (Math.abs(dx) < 0.001 && Math.abs(dy) < 0.001) return { x: cx, y: cy };
  const tX = Math.abs(dx) > 0.001 ? halfW / Math.abs(dx) : Infinity;
  const tY = Math.abs(dy) > 0.001 ? halfH / Math.abs(dy) : Infinity;
  const t = Math.min(tX, tY);
  return { x: cx + dx * t, y: cy + dy * t };
}

/**
 * Extract stroke data from a Fabric.js canvas for persistence (IF-L1-058).
 *
 * Iterates over all canvas objects and maps them to CanvasStroke records.
 * Only "path" (free-hand pen) objects are converted; other object types
 * are included with an empty points array until richer extraction is needed.
 */
export function extractStrokeData(canvas: FabricCanvas): CanvasStrokeData {
  const objects: unknown[] = canvas.getObjects() as unknown[];
  const strokes: CanvasStroke[] = [];

  for (const obj of objects) {
    const o = obj as Record<string, unknown>;
    const stroke: CanvasStroke = {
      id: typeof o.id === "string" ? o.id : crypto.randomUUID(),
      type: "pen",
      color: typeof o.stroke === "string" ? o.stroke : "#000000",
      width: typeof o.strokeWidth === "number" ? o.strokeWidth : 2,
      opacity: typeof o.opacity === "number" ? o.opacity : 1.0,
      points: [],
    };

    // Extract path points for free-hand strokes (Fabric.js type === "path")
    if (o.type === "path") {
      const pathObj = o as { path?: Array<Array<string | number>> };
      stroke.points = (pathObj.path ?? [])
        .map((segment) => ({
          x: segment[segment.length - 2] as number,
          y: segment[segment.length - 1] as number,
        }));
    }

    strokes.push(stroke);
  }

  return {
    strokes,
    width: (canvas.width as number | undefined) ?? 800,
    height: (canvas.height as number | undefined) ?? 600,
  };
}

/**
 * Load stroke data onto a Fabric.js canvas (IF-L1-060).
 *
 * For pen strokes, converts point arrays to SVG path strings. Full Fabric
 * object reconstruction from all stroke types is deferred to a future
 * iteration — this simplified version handles pen strokes.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function loadStrokesToCanvas(canvas: FabricCanvas, fabric: any, strokes: CanvasStroke[]): void {
  for (const stroke of strokes) {
    if (stroke.type === "pen" && stroke.points && stroke.points.length > 0) {
      const pathData = stroke.points
        .map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x} ${pt.y}`)
        .join(" ");
      const path = new fabric.Path(pathData, {
        stroke: stroke.color,
        strokeWidth: stroke.width,
        fill: "transparent",
        opacity: stroke.opacity,
        strokeLineCap: "round",
        strokeLineJoin: "round"
      });
      canvas.add(path);
    }
  }
  canvas.renderAll();
}
