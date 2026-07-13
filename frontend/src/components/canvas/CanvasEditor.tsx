/**
 * ARCH-L1-001 ReactFrontend — CanvasEditor (COMP-RF-005 Canvas).
 *
 * leaf_id: COMP-RF-005 (CanvasEditor)
 * req_id: REQ-L1-056 (Free-Hand Canvas), REQ-L2-DS-006 (CanvasEditor)
 *
 * Architecture-modelling canvas editor built on Fabric.js v6.
 * Features:
 * - Select/move tool (default), pen, eraser
 * - Shape tools: rounded rectangle, ellipse, text (styled nodes with shadow)
 * - Drag-to-connect trace tool: press on a source node, drag a live preview,
 *   release on the target node (REQ-L2-CV-004); edge-clipped arrow connectors
 * - Node labels: double-click a shape to add/edit a centered label
 * - Dot-grid background with snap-to-grid (toggleable)
 * - Zoom (Ctrl+Scroll, toolbar buttons, fit-to-content) and pan (Alt/middle drag)
 * - Stroke + fill color, stroke width, solid/dashed connector style
 * - Undo/Redo (Ctrl+Z / Ctrl+Y), Delete with connector/label cascade
 * - Auto-Save 5s via PUT /canvas-strokes/ when dirty
 *
 * Interfaces:
 *   IF-L1-058 (input): Push stroke data backend
 *   IF-L1-060 (output): Receive stroke data + SVG backend
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { diagramsApi } from "../../api/diagrams";
import type {
  CanvasStroke,
  CanvasStrokeData,
  CanvasTool,
  FabricCanvasJson,
} from "../../types";
import styles from "../../styles/components/CanvasEditor.module.css";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AUTO_SAVE_INTERVAL_MS = 5000;
const MAX_UNDO_HISTORY = 50;
/** Logical snap resolution in scene units. */
const SNAP_GRID = 10;
/** Visual dot-grid spacing at zoom 1 (kept in sync with the CSS default). */
const VISUAL_GRID = 20;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;
const HIGHLIGHT_COLOR = "#4f6ef7";

const TOOLBAR_COLORS = [
  "#1f2937", // slate (default stroke)
  "#e53e3e", // red
  "#38a169", // green
  "#4f6ef7", // blue (primary)
  "#d69e2e", // yellow
  "#805ad5", // purple
];

const FILL_COLORS = [
  "transparent",
  "#ffffff",
  "#eef2ff", // indigo tint
  "#ecfdf5", // green tint
  "#fff7ed", // orange tint
  "#fef2f2", // red tint
];

/** Selection handle styling applied to every user-created object. */
const CONTROL_STYLE = {
  cornerColor: "#ffffff",
  cornerStrokeColor: HIGHLIGHT_COLOR,
  borderColor: HIGHLIGHT_COLOR,
  cornerSize: 8,
  transparentCorners: false,
  borderScaleFactor: 1.5,
};

const NODE_FONT = "'Inter', 'Segoe UI', system-ui, sans-serif";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CanvasEditorProps {
  diagramId: string;
  initialStrokes?: CanvasStroke[];
  /**
   * Pre-loaded Fabric.js serialization (REQ-L2-CV-005). When present and it
   * contains an `objects` array it takes precedence over `initialStrokes` and
   * is restored via canvas.loadFromJSON(). Falls back to stroke replay for the
   * legacy stroke-array format.
   */
  initialCanvasJson?: FabricCanvasJson;
  onAutoSave?: (strokes: CanvasStroke[]) => void;
}

// ---------------------------------------------------------------------------
// Internal types for Fabric.js (dynamically imported)
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FabricCanvas = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObj = Record<string, any>;

type LineStyle = "solid" | "dashed";

// ---------------------------------------------------------------------------
// Toolbar icons (16px, stroke = currentColor)
// ---------------------------------------------------------------------------

interface IconProps {
  children: React.ReactNode;
}

function Icon({ children }: IconProps): JSX.Element {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const ICONS = {
  select: (
    <Icon>
      <path d="M3 2l4.5 11 1.6-4.4L13.5 7 3 2z" fill="currentColor" stroke="none" />
    </Icon>
  ),
  pen: (
    <Icon>
      <path d="M2.5 13.5l.9-3.2 7.4-7.4a1.3 1.3 0 011.8 0l.5.5a1.3 1.3 0 010 1.8l-7.4 7.4-3.2.9z" />
    </Icon>
  ),
  eraser: (
    <Icon>
      <path d="M5.5 13h8" />
      <path d="M2.7 10.3l6-6a1.2 1.2 0 011.7 0l2.3 2.3a1.2 1.2 0 010 1.7L8.5 12.5H5.9l-3.2-2.2z" />
    </Icon>
  ),
  rect: (
    <Icon>
      <rect x="2.5" y="4" width="11" height="8" rx="1.5" />
    </Icon>
  ),
  ellipse: (
    <Icon>
      <ellipse cx="8" cy="8" rx="5.5" ry="4" />
    </Icon>
  ),
  text: (
    <Icon>
      <path d="M3.5 4.5V3h9v1.5M8 3v10M6 13h4" />
    </Icon>
  ),
  connector: (
    <Icon>
      <rect x="1.5" y="1.5" width="5" height="4" rx="1" />
      <rect x="9.5" y="10.5" width="5" height="4" rx="1" />
      <path d="M6.5 5.5L10 10m0 0v-2.6M10 10H7.4" />
    </Icon>
  ),
  dashed: (
    <Icon>
      <path d="M2 8h2.5M6.5 8H9M11 8h3" />
    </Icon>
  ),
  solid: (
    <Icon>
      <path d="M2 8h12" />
    </Icon>
  ),
  grid: (
    <Icon>
      <circle cx="4" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="4" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="4" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="0.8" fill="currentColor" stroke="none" />
    </Icon>
  ),
  zoomIn: (
    <Icon>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14M7 5v4M5 7h4" />
    </Icon>
  ),
  zoomOut: (
    <Icon>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14M5 7h4" />
    </Icon>
  ),
  fit: (
    <Icon>
      <path d="M2 5.5V2h3.5M14 5.5V2h-3.5M2 10.5V14h3.5M14 10.5V14h-3.5" />
    </Icon>
  ),
  undo: (
    <Icon>
      <path d="M6 3.5L2.5 7 6 10.5" />
      <path d="M2.5 7h7a4 4 0 010 8H8" />
    </Icon>
  ),
  redo: (
    <Icon>
      <path d="M10 3.5L13.5 7 10 10.5" />
      <path d="M13.5 7h-7a4 4 0 000 8H8" />
    </Icon>
  ),
};

// ---------------------------------------------------------------------------
// CanvasEditor component
// ---------------------------------------------------------------------------

export function CanvasEditor({
  diagramId,
  initialStrokes,
  initialCanvasJson,
  onAutoSave,
}: CanvasEditorProps): JSX.Element {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const fabricRef = useRef<FabricCanvas>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const undoStackRef = useRef<string[]>([]);
  const redoStackRef = useRef<string[]>([]);

  const [activeTool, setActiveTool] = useState<CanvasTool>("select");
  const [color, setColor] = useState("#1f2937");
  const [fillColor, setFillColor] = useState("#ffffff");
  const [lineStyle, setLineStyle] = useState<LineStyle>("solid");
  const [strokeWidth, setStrokeWidth] = useState(2);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [isDirty, setIsDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [isInitialized, setIsInitialized] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  // Live-value refs so canvas event handlers (bound once at init) always read
  // the current tool/color/width without being re-bound on every change.
  const activeToolRef = useRef<CanvasTool>(activeTool);
  const colorRef = useRef(color);
  const fillRef = useRef(fillColor);
  const lineStyleRef = useRef<LineStyle>(lineStyle);
  const widthRef = useRef(strokeWidth);
  const snapRef = useRef(snapEnabled);
  // Transient interaction state (shape drag origin, live connector drag, pan).
  const drawingRef = useRef<{ obj: AnyObj; originX: number; originY: number } | null>(null);
  const connectorDragRef = useRef<{ src: AnyObj; line: AnyObj } | null>(null);
  const highlightRef = useRef<{ obj: AnyObj; stroke: unknown } | null>(null);
  const panRef = useRef<{ x: number; y: number } | null>(null);
  // Set while canvas.loadFromJSON() replays objects programmatically so that
  // add-driven snapshots (REQ-L2-CV-005) are suppressed during restores.
  const isLoadingRef = useRef(false);

  useEffect(() => {
    activeToolRef.current = activeTool;
  }, [activeTool]);
  useEffect(() => {
    colorRef.current = color;
  }, [color]);
  useEffect(() => {
    fillRef.current = fillColor;
  }, [fillColor]);
  useEffect(() => {
    lineStyleRef.current = lineStyle;
  }, [lineStyle]);
  useEffect(() => {
    widthRef.current = strokeWidth;
  }, [strokeWidth]);
  useEffect(() => {
    snapRef.current = snapEnabled;
  }, [snapEnabled]);

  // -----------------------------------------------------------------------
  // Grid background sync (dot grid follows viewport pan/zoom)
  // -----------------------------------------------------------------------

  const updateGridBackground = useCallback((canvas: FabricCanvas): void => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const vt = (canvas.viewportTransform as number[] | undefined) ?? [1, 0, 0, 1, 0, 0];
    const size = VISUAL_GRID * (vt[0] || 1);
    wrapper.style.backgroundSize = `${size}px ${size}px`;
    wrapper.style.backgroundPosition = `${vt[4]}px ${vt[5]}px`;
  }, []);

  // -----------------------------------------------------------------------
  // Undo / Redo
  // -----------------------------------------------------------------------

  const pushUndoState = useCallback((canvas: FabricCanvas): void => {
    const json = JSON.stringify(canvas.toJSON());
    undoStackRef.current.push(json);
    if (undoStackRef.current.length > MAX_UNDO_HISTORY) {
      undoStackRef.current.shift();
    }
    redoStackRef.current = [];
    setCanUndo(true);
    setCanRedo(false);
  }, []);

  const handleUndo = useCallback((): void => {
    const canvas = fabricRef.current;
    if (!canvas || undoStackRef.current.length === 0) return;

    const currentState = JSON.stringify(canvas.toJSON());
    redoStackRef.current.push(currentState);

    const prevState = undoStackRef.current.pop();
    if (prevState) {
      canvas.loadFromJSON(JSON.parse(prevState)).then(() => {
        canvas.backgroundColor = "";
        canvas.renderAll();
      });
    }
    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(true);
    setIsDirty(true);
  }, []);

  const handleRedo = useCallback((): void => {
    const canvas = fabricRef.current;
    if (!canvas || redoStackRef.current.length === 0) return;

    const currentState = JSON.stringify(canvas.toJSON());
    undoStackRef.current.push(currentState);

    const nextState = redoStackRef.current.pop();
    if (nextState) {
      canvas.loadFromJSON(JSON.parse(nextState)).then(() => {
        canvas.backgroundColor = "";
        canvas.renderAll();
      });
    }
    setCanUndo(true);
    setCanRedo(redoStackRef.current.length > 0);
    setIsDirty(true);
  }, []);

  // -----------------------------------------------------------------------
  // Zoom controls
  // -----------------------------------------------------------------------

  const applyZoom = useCallback(
    (nextZoom: number, centerX?: number, centerY?: number): void => {
      const canvas = fabricRef.current;
      if (!canvas || !Array.isArray(canvas.viewportTransform)) return;
      const z = clampZoom(nextZoom);
      const cx = centerX ?? (canvas.width as number) / 2;
      const cy = centerY ?? (canvas.height as number) / 2;
      zoomViewportAt(canvas, z, cx, cy);
      setZoom(z);
      updateGridBackground(canvas);
      canvas.renderAll();
    },
    [updateGridBackground]
  );

  const handleZoomIn = useCallback((): void => applyZoom(zoom * 1.25), [applyZoom, zoom]);
  const handleZoomOut = useCallback((): void => applyZoom(zoom / 1.25), [applyZoom, zoom]);

  /** Fit all content into the viewport with padding; reset to 100% when empty. */
  const handleZoomFit = useCallback((): void => {
    const canvas = fabricRef.current;
    if (!canvas || !Array.isArray(canvas.viewportTransform)) return;
    const objects = (canvas.getObjects() as AnyObj[]).filter(
      (o) => (o.data as { type?: string } | undefined)?.type !== "connectorPreview"
    );
    const cw = (canvas.width as number) || 800;
    const ch = (canvas.height as number) || 600;

    if (objects.length === 0) {
      canvas.setViewportTransform?.([1, 0, 0, 1, 0, 0]);
      setZoom(1);
      updateGridBackground(canvas);
      canvas.renderAll();
      return;
    }

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const obj of objects) {
      const br = boundingRect(obj);
      minX = Math.min(minX, br.left);
      minY = Math.min(minY, br.top);
      maxX = Math.max(maxX, br.left + br.width);
      maxY = Math.max(maxY, br.top + br.height);
    }
    const pad = 48;
    const bw = Math.max(maxX - minX, 1);
    const bh = Math.max(maxY - minY, 1);
    const z = clampZoom(Math.min((cw - pad * 2) / bw, (ch - pad * 2) / bh, 1.5));
    const vt = [z, 0, 0, z, cw / 2 - (minX + bw / 2) * z, ch / 2 - (minY + bh / 2) * z];
    canvas.setViewportTransform?.(vt);
    setZoom(z);
    updateGridBackground(canvas);
    canvas.renderAll();
  }, [updateGridBackground]);

  // -----------------------------------------------------------------------
  // Deletion (REQ-L2-CV-001..004)
  // -----------------------------------------------------------------------

  /**
   * Remove the current selection and any connectors/arrowheads/labels anchored
   * to it. Deleting a shape must not leave dangling connectors: every
   * fabric.Line whose `data.fromId`/`data.toId` references a removed shape is
   * removed too, along with the arrowhead Triangle carrying the matching
   * `data.connectorId` and any label with a matching `data.labelFor`.
   */
  const deleteActiveObjects = useCallback(
    (canvas: FabricCanvas): void => {
      const active = canvas.getActiveObjects?.() ?? [];
      if (active.length === 0) return;

      const toRemove = new Set<unknown>(active);
      const removedShapeIds = new Set<string>(
        active
          .map((o: AnyObj) => (o.data as { id?: string } | undefined)?.id)
          .filter((id: string | undefined): id is string => Boolean(id))
      );

      // Cascade: connectors referencing a removed shape (or selected directly).
      for (const obj of canvas.getObjects() as AnyObj[]) {
        const data = obj.data as { type?: string; fromId?: string; toId?: string } | undefined;
        if (
          data?.type === "connector" &&
          ((data.fromId && removedShapeIds.has(data.fromId)) ||
            (data.toId && removedShapeIds.has(data.toId)))
        ) {
          toRemove.add(obj);
        }
      }

      // Cascade: arrowheads whose connector is being removed.
      const removedConnectorIds = new Set<string>(
        [...toRemove]
          .map((o) => (o as AnyObj).data as { type?: string; id?: string } | undefined)
          .filter((d): d is { type?: string; id?: string } => d?.type === "connector")
          .map((d) => d.id)
          .filter((id): id is string => Boolean(id))
      );
      for (const obj of canvas.getObjects() as AnyObj[]) {
        const data = obj.data as { type?: string; connectorId?: string; labelFor?: string } | undefined;
        if (data?.type === "arrowHead" && data.connectorId && removedConnectorIds.has(data.connectorId)) {
          toRemove.add(obj);
        }
        if (data?.type === "label" && data.labelFor && removedShapeIds.has(data.labelFor)) {
          toRemove.add(obj);
        }
      }

      toRemove.forEach((obj) => canvas.remove(obj));
      canvas.discardActiveObject();
      pushUndoState(canvas);
      setIsDirty(true);
      canvas.renderAll();
    },
    [pushUndoState]
  );

  // -----------------------------------------------------------------------
  // Auto-Save (IF-L1-058)
  // -----------------------------------------------------------------------

  const performAutoSave = useCallback(async (): Promise<void> => {
    const canvas = fabricRef.current;
    if (!canvas || !isDirty) return;

    setSaveStatus("saving");
    try {
      const strokeData = extractStrokeData(canvas);
      // REQ-L2-CV-005: primary persistence is the full Fabric serialization.
      // The ["data"] allowlist keeps custom connector anchor metadata. The
      // legacy `strokes` array is still sent for backward compatibility.
      const canvasJson = canvas.toJSON(["data"]) as FabricCanvasJson;

      await diagramsApi.saveCanvasStrokes(diagramId, {
        strokes: strokeData.strokes,
        width: strokeData.width,
        height: strokeData.height,
        canvas_json: canvasJson,
      } as CanvasStrokeData);

      setIsDirty(false);
      setSaveStatus("saved");
      onAutoSave?.(strokeData.strokes);

      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (err) {
      console.error("Canvas auto-save failed", err);
      setSaveStatus("error");
    }
  }, [diagramId, isDirty, onAutoSave]);

  // -----------------------------------------------------------------------
  // Fabric.js initialization
  // -----------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    async function initCanvas(): Promise<void> {
      if (!canvasRef.current || fabricRef.current) return;

      const fabric = await import("fabric");
      if (cancelled || !canvasRef.current) return;

      const parent = canvasRef.current.parentElement;
      const width = parent?.clientWidth ?? 800;
      const height = parent?.clientHeight ?? 600;

      const canvas = new fabric.Canvas(canvasRef.current, {
        width,
        height,
        // Transparent so the CSS dot grid on the wrapper shows through.
        backgroundColor: "",
        isDrawingMode: false,
        selection: true,
        preserveObjectStacking: true,
        selectionColor: "rgba(79, 110, 247, 0.08)",
        selectionBorderColor: HIGHLIGHT_COLOR,
        selectionLineWidth: 1,
      });

      // Configure drawing brush
      canvas.freeDrawingBrush = new fabric.PencilBrush(canvas);
      canvas.freeDrawingBrush.color = color;
      canvas.freeDrawingBrush.width = strokeWidth;

      // Track changes for undo
      canvas.on("path:created", () => {
        pushUndoState(canvas);
        setIsDirty(true);
      });

      canvas.on("object:modified", () => {
        pushUndoState(canvas);
        setIsDirty(true);
      });

      /** Snap a scene coordinate to the grid when snapping is enabled. */
      function snap(v: number): number {
        return snapRef.current ? Math.round(v / SNAP_GRID) * SNAP_GRID : v;
      }

      /** Node shadow — subtle elevation for shape nodes; optional for mocks. */
      function nodeShadow(): unknown {
        return typeof fabric.Shadow === "function"
          ? new fabric.Shadow({ color: "rgba(15, 23, 42, 0.12)", blur: 8, offsetX: 0, offsetY: 2 })
          : undefined;
      }

      /** Restore a temporarily highlighted connector target. */
      function clearHighlight(): void {
        const h = highlightRef.current;
        if (!h) return;
        h.obj.set({ stroke: h.stroke });
        highlightRef.current = null;
      }

      /** True when the object can serve as a connector anchor. */
      function isConnectable(obj: AnyObj | null | undefined): obj is AnyObj {
        if (!obj) return false;
        const data = obj.data as { id?: string; type?: string } | undefined;
        return Boolean(
          data?.id && data.type !== "connector" && data.type !== "label" && data.type !== "connectorPreview"
        );
      }

      // -------------------------------------------------------------------
      // Shape / text / connector interaction (REQ-L2-CV-001..004)
      //
      // Bound once here so `fabric` is in scope. Live tool/color/width are read
      // from refs, so these handlers never need re-binding on state changes.
      // -------------------------------------------------------------------

      /**
       * Create a connector (fabric.Line) with an arrowhead Triangle between two
       * anchor shapes (REQ-L2-CV-004). Endpoints are clipped to each shape's
       * bounding-box edge via getEdgePoint so the line starts/ends at the box
       * border instead of the center. Both carry linked `data` metadata so
       * object:moving and deletion can find them.
       */
      function createConnector(cv: FabricCanvas, src: AnyObj, tgt: AnyObj): void {
        const srcBR = boundingRect(src);
        const tgtBR = boundingRect(tgt);
        const srcCenter = { x: srcBR.left + srcBR.width / 2, y: srcBR.top + srcBR.height / 2 };
        const tgtCenter = { x: tgtBR.left + tgtBR.width / 2, y: tgtBR.top + tgtBR.height / 2 };
        // Clip endpoints to the bounding-box edges (REQ-L2-CV-004).
        const s = getEdgePoint(
          srcCenter.x, srcCenter.y, srcBR.width / 2, srcBR.height / 2, tgtCenter.x, tgtCenter.y
        );
        const tp = getEdgePoint(
          tgtCenter.x, tgtCenter.y, tgtBR.width / 2, tgtBR.height / 2, srcCenter.x, srcCenter.y
        );
        const lineId = makeObjectId();
        const srcData = src.data as { id?: string } | undefined;
        const tgtData = tgt.data as { id?: string } | undefined;

        const line = new fabric.Line([s.x, s.y, tp.x, tp.y], {
          stroke: colorRef.current,
          strokeWidth: Math.max(1.5, widthRef.current),
          strokeLineCap: "round",
          strokeDashArray: lineStyleRef.current === "dashed" ? [8, 5] : undefined,
          selectable: true,
          evented: true,
          perPixelTargetFind: true,
          ...CONTROL_STYLE,
          data: { type: "connector", id: lineId, fromId: srcData?.id, toId: tgtData?.id },
        });

        const angle = (Math.atan2(tp.y - s.y, tp.x - s.x) * 180) / Math.PI + 90;
        const head = new fabric.Triangle({
          left: tp.x,
          top: tp.y,
          width: 11,
          height: 13,
          fill: colorRef.current,
          angle,
          originX: "center",
          originY: "center",
          selectable: false,
          evented: false,
          data: { type: "arrowHead", connectorId: lineId },
        });

        cv.add(line);
        cv.add(head);
        pushUndoState(cv);
        setIsDirty(true);
        cv.renderAll();
      }

      /**
       * mouse:down — dispatch by active tool.
       * Alt/middle-button press starts panning regardless of tool.
       * rect/ellipse: begin a drag-draw (snapped). text: drop an editable
       * Textbox. connector: press on a source node to start a drag-to-connect
       * gesture with a live dashed preview line.
       */
      canvas.on("mouse:down", (opt: { e: Event; target?: unknown }) => {
        const evt = opt.e as MouseEvent | undefined;
        if (evt && (evt.altKey || (evt as MouseEvent).button === 1)) {
          panRef.current = { x: evt.clientX, y: evt.clientY };
          return;
        }

        const tool = activeToolRef.current;
        if (tool !== "rect" && tool !== "ellipse" && tool !== "text" && tool !== "connector") {
          return;
        }
        const raw = canvas.getPointer(opt.e);
        const pointer = { x: snap(raw.x), y: snap(raw.y) };

        if (tool === "rect" || tool === "ellipse") {
          const common = {
            left: pointer.x,
            top: pointer.y,
            fill: fillRef.current,
            stroke: colorRef.current,
            strokeWidth: widthRef.current,
            strokeUniform: true,
            shadow: nodeShadow(),
            selectable: false,
            evented: false,
            ...CONTROL_STYLE,
            data: { id: makeObjectId(), type: tool },
          };
          const obj =
            tool === "rect"
              ? new fabric.Rect({ ...common, width: 0, height: 0, rx: 8, ry: 8 })
              : new fabric.Ellipse({ ...common, rx: 0, ry: 0 });
          canvas.add(obj);
          drawingRef.current = { obj, originX: pointer.x, originY: pointer.y };
          return;
        }

        if (tool === "text") {
          const textbox = new fabric.Textbox(t("canvas.defaultText", "Text"), {
            left: pointer.x,
            top: pointer.y,
            width: 160,
            fontSize: 14,
            fontFamily: NODE_FONT,
            fill: colorRef.current,
            editable: true,
            ...CONTROL_STYLE,
            data: { id: makeObjectId(), type: "text" },
          });
          canvas.add(textbox);
          canvas.setActiveObject(textbox);
          textbox.enterEditing?.();
          textbox.selectAll?.();
          pushUndoState(canvas);
          setIsDirty(true);
          canvas.renderAll();
          return;
        }

        // connector — drag-to-connect: press on a source node starts the trace.
        const target = canvas.findTarget?.(opt.e) ?? null;
        if (!isConnectable(target)) return;
        const srcBR = boundingRect(target);
        const cx = srcBR.left + srcBR.width / 2;
        const cy = srcBR.top + srcBR.height / 2;
        const start = getEdgePoint(cx, cy, srcBR.width / 2, srcBR.height / 2, raw.x, raw.y);
        const preview = new fabric.Line([start.x, start.y, raw.x, raw.y], {
          stroke: HIGHLIGHT_COLOR,
          strokeWidth: 1.5,
          strokeDashArray: [6, 4],
          selectable: false,
          evented: false,
          data: { type: "connectorPreview" },
        });
        canvas.add(preview);
        connectorDragRef.current = { src: target, line: preview };
      });

      /**
       * mouse:move — pan, live connector preview (with target highlight) or
       * live-resize of the shape currently being drawn.
       */
      canvas.on("mouse:move", (opt: { e: Event }) => {
        const evt = opt.e as MouseEvent | undefined;

        if (panRef.current && evt) {
          const vt = canvas.viewportTransform as number[] | undefined;
          if (vt) {
            vt[4] += evt.clientX - panRef.current.x;
            vt[5] += evt.clientY - panRef.current.y;
            panRef.current = { x: evt.clientX, y: evt.clientY };
            canvas.setViewportTransform?.(vt);
            updateGridBackground(canvas);
            canvas.renderAll();
          }
          return;
        }

        const drag = connectorDragRef.current;
        if (drag) {
          const pointer = canvas.getPointer(opt.e);
          const srcBR = boundingRect(drag.src);
          const cx = srcBR.left + srcBR.width / 2;
          const cy = srcBR.top + srcBR.height / 2;
          const start = getEdgePoint(cx, cy, srcBR.width / 2, srcBR.height / 2, pointer.x, pointer.y);
          drag.line.set({ x1: start.x, y1: start.y, x2: pointer.x, y2: pointer.y });
          drag.line.setCoords?.();

          // Highlight the node currently under the cursor as a drop target.
          const over = canvas.findTarget?.(opt.e) ?? null;
          const validTarget = isConnectable(over) && over !== drag.src ? over : null;
          if (highlightRef.current && highlightRef.current.obj !== validTarget) {
            clearHighlight();
          }
          if (validTarget && !highlightRef.current) {
            highlightRef.current = { obj: validTarget, stroke: validTarget.stroke };
            validTarget.set({ stroke: HIGHLIGHT_COLOR });
          }
          canvas.renderAll();
          return;
        }

        const drawing = drawingRef.current;
        if (!drawing) return;
        const tool = activeToolRef.current;
        if (tool !== "rect" && tool !== "ellipse") return;

        const raw = canvas.getPointer(opt.e);
        const px = snap(raw.x);
        const py = snap(raw.y);
        const left = Math.min(px, drawing.originX);
        const top = Math.min(py, drawing.originY);
        const width = Math.abs(px - drawing.originX);
        const height = Math.abs(py - drawing.originY);

        if (tool === "rect") {
          drawing.obj.set({ left, top, width, height });
        } else {
          drawing.obj.set({ left, top, rx: width / 2, ry: height / 2 });
        }
        drawing.obj.setCoords();
        canvas.renderAll();
      });

      /**
       * mouse:up — end panning, finalize a drag-to-connect gesture, or
       * finalize the drawn shape (then hand back to the select tool).
       */
      canvas.on("mouse:up", (opt: { e?: Event }) => {
        if (panRef.current) {
          panRef.current = null;
          return;
        }

        const drag = connectorDragRef.current;
        if (drag) {
          connectorDragRef.current = null;
          clearHighlight();
          canvas.remove(drag.line);
          const target = opt.e ? canvas.findTarget?.(opt.e) ?? null : null;
          if (isConnectable(target) && target !== drag.src) {
            createConnector(canvas, drag.src, target);
          } else {
            canvas.renderAll();
          }
          return;
        }

        const drawing = drawingRef.current;
        if (!drawing) return;
        drawingRef.current = null;
        drawing.obj.set({ selectable: true, evented: true });
        drawing.obj.setCoords();
        canvas.setActiveObject?.(drawing.obj);
        pushUndoState(canvas);
        setIsDirty(true);
        canvas.renderAll();
        // Hand back to select so the fresh node can be positioned immediately.
        setActiveTool("select");
      });

      /**
       * mouse:dblclick — re-enter editing on a text box, or add/edit the
       * centered label of a shape node.
       */
      canvas.on("mouse:dblclick", (opt: { target?: AnyObj }) => {
        const target = opt.target;
        const data = target?.data as { id?: string; type?: string } | undefined;
        if (!target || !data) return;

        if (data.type === "text" && typeof target.enterEditing === "function") {
          (target.enterEditing as () => void)();
          canvas.renderAll();
          return;
        }

        if ((data.type === "rect" || data.type === "ellipse") && data.id) {
          const existing = (canvas.getObjects() as AnyObj[]).find((o) => {
            const od = o.data as { type?: string; labelFor?: string } | undefined;
            return od?.type === "label" && od.labelFor === data.id;
          });
          const br = boundingRect(target);
          let label = existing;
          if (!label) {
            label = new fabric.Textbox(t("canvas.defaultLabel", "Label"), {
              left: br.left + br.width / 2,
              top: br.top + br.height / 2,
              width: Math.max(60, br.width - 16),
              originX: "center",
              originY: "center",
              fontSize: 13,
              fontFamily: NODE_FONT,
              fontWeight: "600",
              textAlign: "center",
              fill: colorRef.current,
              editable: true,
              selectable: false,
              evented: true,
              data: { id: makeObjectId(), type: "label", labelFor: data.id },
            });
            canvas.add(label);
          }
          canvas.setActiveObject?.(label);
          label.enterEditing?.();
          label.selectAll?.();
          setIsDirty(true);
          canvas.renderAll();
        }
      });

      canvas.on("text:changed", () => setIsDirty(true));
      canvas.on("editing:exited", () => {
        pushUndoState(canvas);
        setIsDirty(true);
      });

      /**
       * Keep connectors, arrowheads and labels glued to their anchor shape
       * (REQ-L2-CV-004). Recomputes both line endpoints (clipped to each
       * shape's bounding-box edge via getEdgePoint), the arrowhead pose and
       * the label center from the live positions of the anchored shapes.
       */
      function syncAttachments(moved: AnyObj): void {
        const movedData = moved.data as { id?: string } | undefined;
        if (!movedData?.id) return;
        const movedId = movedData.id;
        const allObjects = canvas.getObjects() as AnyObj[];

        for (const obj of allObjects) {
          const data = obj.data as
            | { type?: string; id?: string; fromId?: string; toId?: string; labelFor?: string }
            | undefined;

          if (data?.type === "label" && data.labelFor === movedId) {
            const br = boundingRect(moved);
            obj.set({ left: br.left + br.width / 2, top: br.top + br.height / 2 });
            (obj.setCoords as () => void)();
            continue;
          }

          if (data?.type !== "connector") continue;
          const isFrom = data.fromId === movedId;
          const isTo = data.toId === movedId;
          if (!isFrom && !isTo) continue;

          // Resolve both anchored shapes; use the live-moved instance so its
          // current position is reflected before setCoords() commits.
          const findById = (id?: string): AnyObj | undefined => {
            if (!id) return undefined;
            if (movedId === id) return moved;
            return allObjects.find((o) => {
              const od = o.data as { id?: string } | undefined;
              return od?.id === id;
            });
          };
          const srcObj = findById(data.fromId);
          const tgtObj = findById(data.toId);
          if (!srcObj || !tgtObj) continue;

          const srcBR = boundingRect(srcObj);
          const tgtBR = boundingRect(tgtObj);
          const srcCenter = { x: srcBR.left + srcBR.width / 2, y: srcBR.top + srcBR.height / 2 };
          const tgtCenter = { x: tgtBR.left + tgtBR.width / 2, y: tgtBR.top + tgtBR.height / 2 };
          // Clip both endpoints to the bounding-box edges (REQ-L2-CV-004).
          const lineStart = getEdgePoint(
            srcCenter.x, srcCenter.y, srcBR.width / 2, srcBR.height / 2, tgtCenter.x, tgtCenter.y
          );
          const lineEnd = getEdgePoint(
            tgtCenter.x, tgtCenter.y, tgtBR.width / 2, tgtBR.height / 2, srcCenter.x, srcCenter.y
          );

          obj.set({ x1: lineStart.x, y1: lineStart.y, x2: lineEnd.x, y2: lineEnd.y });
          (obj.setCoords as () => void)();

          const head = allObjects.find((o) => {
            const hd = o.data as { type?: string; connectorId?: string } | undefined;
            return hd?.type === "arrowHead" && hd.connectorId === data.id;
          });
          if (head) {
            const angle =
              (Math.atan2(lineEnd.y - lineStart.y, lineEnd.x - lineStart.x) * 180) / Math.PI + 90;
            head.set({ left: lineEnd.x, top: lineEnd.y, angle });
            (head.setCoords as () => void)();
          }
        }
      }

      canvas.on("object:moving", (opt: { target?: AnyObj }) => {
        const moved = opt.target;
        if (!moved) return;
        // Snap node position to the grid while dragging.
        if (snapRef.current && typeof moved.left === "number" && typeof moved.top === "number") {
          const movedData = moved.data as { type?: string } | undefined;
          if (movedData?.type === "rect" || movedData?.type === "ellipse" || movedData?.type === "text") {
            moved.set({
              left: Math.round(moved.left / SNAP_GRID) * SNAP_GRID,
              top: Math.round(moved.top / SNAP_GRID) * SNAP_GRID,
            });
          }
        }
        syncAttachments(moved);
        canvas.renderAll();
      });

      canvas.on("object:scaling", (opt: { target?: AnyObj }) => {
        if (!opt.target) return;
        syncAttachments(opt.target);
        canvas.renderAll();
      });

      /** Ctrl/Cmd+Scroll zooms around the cursor; plain scroll pans. */
      canvas.on("mouse:wheel", (opt: { e: WheelEvent }) => {
        const evt = opt.e;
        if (!evt) return;
        evt.preventDefault?.();
        evt.stopPropagation?.();
        const vt = canvas.viewportTransform as number[] | undefined;
        if (!vt) return;

        if (evt.ctrlKey || evt.metaKey) {
          const factor = Math.pow(0.999, evt.deltaY);
          const z = clampZoom((vt[0] || 1) * factor);
          zoomViewportAt(canvas, z, evt.offsetX ?? (canvas.width as number) / 2, evt.offsetY ?? (canvas.height as number) / 2);
          setZoom(z);
        } else {
          vt[4] -= evt.deltaX;
          vt[5] -= evt.deltaY;
          canvas.setViewportTransform?.(vt);
        }
        updateGridBackground(canvas);
        canvas.renderAll();
      });

      fabricRef.current = canvas;
      updateGridBackground(canvas);

      // Restore prior canvas state (REQ-L2-CV-005). Full Fabric serialization
      // takes precedence over the legacy stroke-replay path.
      if (initialCanvasJson && Array.isArray(initialCanvasJson.objects)) {
        isLoadingRef.current = true;
        const result = canvas.loadFromJSON(initialCanvasJson, () => {
          canvas.renderAll();
        });
        Promise.resolve(result).then(() => {
          // Legacy saves carry an opaque white background — clear it so the
          // dot grid stays visible after a restore.
          canvas.backgroundColor = "";
          canvas.renderAll();
          isLoadingRef.current = false;
        });
      } else if (initialStrokes && initialStrokes.length > 0) {
        loadStrokesToCanvas(canvas, fabric, initialStrokes);
      }

      // Handle resize
      resizeObserverRef.current = new ResizeObserver(() => {
        if (!fabricRef.current || !parent) return;
        fabricRef.current.setDimensions({
          width: parent.clientWidth,
          height: parent.clientHeight,
        });
        fabricRef.current.renderAll();
      });
      if (parent) resizeObserverRef.current.observe(parent);

      setIsInitialized(true);
    }

    void initCanvas();

    return () => {
      cancelled = true;
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      fabricRef.current?.dispose();
      fabricRef.current = null;
    };
  }, [diagramId]);

  // -----------------------------------------------------------------------
  // Tool switching
  // -----------------------------------------------------------------------

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    // Leaving the connector tool: restore selectability captured on entry.
    if (activeTool !== "connector") {
      for (const obj of (canvas.getObjects?.() ?? []) as AnyObj[]) {
        if (obj.__wasSelectable !== undefined) {
          obj.selectable = obj.__wasSelectable;
          delete obj.__wasSelectable;
        }
      }
    }

    switch (activeTool) {
      case "pen": {
        canvas.isDrawingMode = true;
        canvas.selection = false;
        canvas.defaultCursor = "crosshair";
        if (canvas.freeDrawingBrush) {
          canvas.freeDrawingBrush.color = color;
          canvas.freeDrawingBrush.width = strokeWidth;
          canvas.freeDrawingBrush.globalCompositeOperation = "source-over";
        }
        break;
      }
      case "select": {
        canvas.isDrawingMode = false;
        canvas.selection = true;
        canvas.defaultCursor = "default";
        break;
      }
      case "eraser": {
        canvas.isDrawingMode = true;
        canvas.selection = false;
        canvas.defaultCursor = "crosshair";
        if (canvas.freeDrawingBrush) {
          canvas.freeDrawingBrush.color = color;
          canvas.freeDrawingBrush.width = strokeWidth * 3;
          canvas.freeDrawingBrush.globalCompositeOperation = "destination-out";
        }
        break;
      }
      // Shape / text / connector tools (REQ-L2-CV-001..004): disable free-draw
      // so mouse events reach the custom handlers. Reset any pending state.
      case "rect":
      case "ellipse":
      case "text":
      case "connector": {
        canvas.isDrawingMode = false;
        canvas.selection = false;
        canvas.defaultCursor = "crosshair";
        drawingRef.current = null;
        if (activeTool === "connector") {
          // Nodes must stay evented (hit-testable as anchors) but not
          // draggable, otherwise pressing on the source starts a move
          // instead of a trace gesture.
          for (const obj of (canvas.getObjects?.() ?? []) as AnyObj[]) {
            const data = obj.data as { type?: string } | undefined;
            if (data?.type === "arrowHead" || data?.type === "connectorPreview") continue;
            if (obj.__wasSelectable === undefined) obj.__wasSelectable = obj.selectable;
            obj.selectable = false;
          }
          canvas.discardActiveObject?.();
        } else if (connectorDragRef.current) {
          canvas.remove?.(connectorDragRef.current.line);
          connectorDragRef.current = null;
        }
        break;
      }
    }
    canvas.renderAll?.();
  }, [activeTool, color, strokeWidth]);

  // -----------------------------------------------------------------------
  // Keyboard shortcuts
  // -----------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      // Delete / Backspace removes the selection (REQ-L2-CV-001..004). Skipped
      // while a text box is in edit mode so keys reach the text input.
      if (e.key === "Delete" || e.key === "Backspace") {
        const canvas = fabricRef.current;
        if (!canvas) return;
        const active = canvas.getActiveObject?.();
        if (active?.isEditing) return;
        if ((canvas.getActiveObjects?.() ?? []).length > 0) {
          e.preventDefault();
          deleteActiveObjects(canvas);
        }
        return;
      }

      // Escape cancels an in-flight trace gesture or shape drag.
      if (e.key === "Escape") {
        const canvas = fabricRef.current;
        if (!canvas) return;
        if (connectorDragRef.current) {
          canvas.remove?.(connectorDragRef.current.line);
          connectorDragRef.current = null;
          canvas.renderAll?.();
        }
        if (drawingRef.current) {
          canvas.remove?.(drawingRef.current.obj);
          drawingRef.current = null;
          canvas.renderAll?.();
        }
        return;
      }

      if (!e.ctrlKey && !e.metaKey) return;
      if (e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if (e.key === "y" || (e.key === "z" && e.shiftKey)) {
        e.preventDefault();
        handleRedo();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleUndo, handleRedo, deleteActiveObjects]);

  // -----------------------------------------------------------------------
  // Auto-Save interval
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!isInitialized) return;
    const timerId = setInterval(() => {
      void performAutoSave();
    }, AUTO_SAVE_INTERVAL_MS);
    return () => clearInterval(timerId);
  }, [isInitialized, performAutoSave]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const toolButton = (
    tool: CanvasTool,
    icon: JSX.Element,
    label: string,
    extraClass = ""
  ): JSX.Element => (
    <button
      type="button"
      data-testid={`canvas-tool-${tool}`}
      className={`${styles.toolButton} ${extraClass} ${activeTool === tool ? styles.toolButtonActive : ""}`}
      onClick={() => setActiveTool(tool)}
      title={label}
      aria-label={label}
      aria-pressed={activeTool === tool}
    >
      {icon}
    </button>
  );

  return (
    <div className={styles.container} data-testid="canvas-editor">
      {/* Toolbar */}
      <div className={styles.toolbar} data-testid="canvas-toolbar">
        <div className={styles.toolGroup}>
          {toolButton("select", ICONS.select, t("canvas.toolbar.select", "Select / Move"))}
          {toolButton("pen", ICONS.pen, t("canvas.toolbar.pen", "Pen"))}
          {toolButton("eraser", ICONS.eraser, t("canvas.toolbar.eraser", "Eraser"))}
        </div>

        {/* Shape / text tools (REQ-L2-CV-001..003) */}
        <div className={styles.toolGroup}>
          {toolButton("rect", ICONS.rect, t("canvas.toolbar.rect", "Component (Rectangle)"), styles.shapeTool)}
          {toolButton("ellipse", ICONS.ellipse, t("canvas.toolbar.ellipse", "Node (Ellipse)"), styles.shapeTool)}
          {toolButton("text", ICONS.text, t("canvas.toolbar.text", "Text"), styles.shapeTool)}
        </div>

        {/* Trace / connector tool (REQ-L2-CV-004): drag from node to node */}
        <div className={styles.toolGroup}>
          {toolButton(
            "connector",
            ICONS.connector,
            t("canvas.toolbar.connector", "Trace — drag from one node to another"),
            styles.shapeTool
          )}
          <button
            type="button"
            data-testid="canvas-line-style"
            className={styles.toolButton}
            onClick={() => setLineStyle((s) => (s === "solid" ? "dashed" : "solid"))}
            title={t("canvas.toolbar.lineStyle", "Trace style (solid / dashed)")}
            aria-label={t("canvas.toolbar.lineStyle", "Trace style")}
            aria-pressed={lineStyle === "dashed"}
          >
            {lineStyle === "dashed" ? ICONS.dashed : ICONS.solid}
          </button>
        </div>

        {/* Stroke color + fill */}
        <div className={styles.toolGroup}>
          <input
            type="color"
            data-testid="canvas-color-picker"
            className={styles.colorPicker}
            value={color}
            onChange={(e) => setColor(e.target.value)}
            title={t("canvas.toolbar.color", "Stroke color")}
            aria-label={t("canvas.toolbar.color", "Stroke color")}
          />
          {TOOLBAR_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              data-testid={`canvas-color-${c.replace("#", "")}`}
              className={`${styles.swatch} ${color === c ? styles.swatchActive : ""}`}
              style={{ background: c }}
              onClick={() => setColor(c)}
              title={`Stroke ${c}`}
              aria-label={`Color ${c}`}
            />
          ))}
        </div>

        <div className={styles.toolGroup}>
          <span className={styles.groupLabel}>{t("canvas.toolbar.fill", "Fill")}</span>
          {FILL_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              data-testid={`canvas-fill-${c.replace("#", "")}`}
              className={`${styles.swatch} ${c === "transparent" ? styles.swatchTransparent : ""} ${
                fillColor === c ? styles.swatchActive : ""
              }`}
              style={c === "transparent" ? undefined : { background: c }}
              onClick={() => setFillColor(c)}
              title={c === "transparent" ? t("canvas.toolbar.noFill", "No fill") : `Fill ${c}`}
              aria-label={`Fill ${c}`}
            />
          ))}
        </div>

        {/* Stroke width */}
        <div className={styles.toolGroup}>
          <input
            type="range"
            data-testid="canvas-width-slider"
            className={styles.widthSlider}
            min={1}
            max={20}
            value={strokeWidth}
            onChange={(e) => setStrokeWidth(Number(e.target.value))}
            title={t("canvas.toolbar.width", "Stroke width")}
            aria-label={t("canvas.toolbar.width", "Stroke width")}
          />
          <span className={styles.widthLabel} data-testid="canvas-width-label">
            {strokeWidth}px
          </span>
        </div>

        {/* Grid snap + zoom */}
        <div className={styles.toolGroup}>
          <button
            type="button"
            data-testid="canvas-snap-toggle"
            className={`${styles.toolButton} ${snapEnabled ? styles.toolButtonActive : ""}`}
            onClick={() => setSnapEnabled((v) => !v)}
            title={t("canvas.toolbar.snap", "Snap to grid")}
            aria-label={t("canvas.toolbar.snap", "Snap to grid")}
            aria-pressed={snapEnabled}
          >
            {ICONS.grid}
          </button>
          <button
            type="button"
            data-testid="canvas-zoom-out"
            className={styles.toolButton}
            onClick={handleZoomOut}
            title={t("canvas.toolbar.zoomOut", "Zoom out")}
            aria-label={t("canvas.toolbar.zoomOut", "Zoom out")}
          >
            {ICONS.zoomOut}
          </button>
          <span className={styles.zoomLabel} data-testid="canvas-zoom-label">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            data-testid="canvas-zoom-in"
            className={styles.toolButton}
            onClick={handleZoomIn}
            title={t("canvas.toolbar.zoomIn", "Zoom in")}
            aria-label={t("canvas.toolbar.zoomIn", "Zoom in")}
          >
            {ICONS.zoomIn}
          </button>
          <button
            type="button"
            data-testid="canvas-zoom-fit"
            className={styles.toolButton}
            onClick={handleZoomFit}
            title={t("canvas.toolbar.zoomFit", "Fit content")}
            aria-label={t("canvas.toolbar.zoomFit", "Fit content")}
          >
            {ICONS.fit}
          </button>
        </div>

        {/* Undo / Redo */}
        <div className={styles.toolGroup}>
          <button
            type="button"
            data-testid="canvas-undo"
            className={styles.toolButton}
            onClick={handleUndo}
            disabled={!canUndo}
            title={t("canvas.toolbar.undo", "Undo (Ctrl+Z)")}
            aria-label={t("canvas.toolbar.undo", "Undo")}
          >
            {ICONS.undo}
          </button>
          <button
            type="button"
            data-testid="canvas-redo"
            className={styles.toolButton}
            onClick={handleRedo}
            disabled={!canRedo}
            title={t("canvas.toolbar.redo", "Redo (Ctrl+Y)")}
            aria-label={t("canvas.toolbar.redo", "Redo")}
          >
            {ICONS.redo}
          </button>
        </div>

        {/* Manual save */}
        <button
          type="button"
          data-testid="canvas-save-btn"
          className={styles.saveButton}
          onClick={() => void performAutoSave()}
          disabled={!isDirty || saveStatus === "saving"}
          title={t("canvas.toolbar.save", "Save")}
          aria-label={t("canvas.toolbar.save", "Save")}
        >
          {saveStatus === "saving"
            ? t("actions.saving", "Saving...")
            : t("actions.save", "Save")}
        </button>
      </div>

      {/* Canvas area */}
      <div className={styles.canvasWrapper} ref={wrapperRef} data-testid="canvas-wrapper">
        <canvas ref={canvasRef} data-testid="canvas-element" />
        {!isInitialized && (
          <div className={styles.emptyState}>
            {t("canvas.loading", "Loading canvas...")}
          </div>
        )}
      </div>

      {/* Status bar */}
      <div className={styles.statusBar} data-testid="canvas-status-bar">
        <span>
          {t("canvas.status.tool", "Tool")}: {activeTool}
        </span>
        <span className={styles.statusHint}>
          {t(
            "canvas.status.hint",
            "Drag traces node → node · Double-click a shape to label it · Alt+Drag pans · Ctrl+Scroll zooms"
          )}
        </span>
        <span
          className={
            saveStatus === "saved"
              ? styles.statusSaved
              : saveStatus === "error"
              ? styles.statusError
              : isDirty
              ? styles.statusUnsaved
              : ""
          }
          data-testid="canvas-save-status"
        >
          {saveStatus === "saving"
            ? t("canvas.status.saving", "Saving...")
            : saveStatus === "saved"
            ? t("canvas.status.saved", "Saved")
            : saveStatus === "error"
            ? t("canvas.status.error", "Save failed")
            : isDirty
            ? t("canvas.status.unsaved", "Unsaved changes")
            : t("canvas.status.idle", "Ready")}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate a stable per-object id for connector anchoring (REQ-L2-CV-004). */
function makeObjectId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function clampZoom(z: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}

/** Set the viewport zoom while keeping the given screen point stationary. */
function zoomViewportAt(canvas: FabricCanvas, zoom: number, x: number, y: number): void {
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
function boundingRect(
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
function getEdgePoint(
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
function extractStrokeData(canvas: FabricCanvas): CanvasStrokeData {
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
function loadStrokesToCanvas(canvas: FabricCanvas, fabric: any, strokes: CanvasStroke[]): void {
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
