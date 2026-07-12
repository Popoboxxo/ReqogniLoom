/**
 * ARCH-L1-001 ReactFrontend — CanvasEditor (COMP-RF-005 Canvas).
 *
 * leaf_id: COMP-RF-005 (CanvasEditor)
 * req_id: REQ-L1-056 (Free-Hand Canvas), REQ-L2-DS-006 (CanvasEditor)
 *
 * Free-hand canvas editor using Fabric.js v6.
 * Features:
 * - Pen tool (free-hand drawing)
 * - Select/move tool
 * - Eraser tool
 * - Color picker (CSS custom properties)
 * - Stroke width slider
 * - Undo/Redo (Ctrl+Z / Ctrl+Y)
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

const TOOLBAR_COLORS = [
  "#000000", // black
  "#e53e3e", // red
  "#38a169", // green
  "#4f6ef7", // blue (primary)
  "#d69e2e", // yellow
  "#805ad5", // purple
];

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
  const fabricRef = useRef<FabricCanvas>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const undoStackRef = useRef<string[]>([]);
  const redoStackRef = useRef<string[]>([]);

  const [activeTool, setActiveTool] = useState<CanvasTool>("pen");
  const [color, setColor] = useState("#000000");
  const [strokeWidth, setStrokeWidth] = useState(2);
  const [isDirty, setIsDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [isInitialized, setIsInitialized] = useState(false);

  // Live-value refs so canvas event handlers (bound once at init) always read
  // the current tool/color/width without being re-bound on every change.
  const activeToolRef = useRef<CanvasTool>(activeTool);
  const colorRef = useRef(color);
  const widthRef = useRef(strokeWidth);
  // Transient interaction state (shape drag origin, pending connector source).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const drawingRef = useRef<{ obj: any; originX: number; originY: number } | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const connectorSourceRef = useRef<any>(null);
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
    widthRef.current = strokeWidth;
  }, [strokeWidth]);

  // -----------------------------------------------------------------------
  // Undo / Redo
  // -----------------------------------------------------------------------

  const pushUndoState = useCallback(
    (canvas: FabricCanvas): void => {
      const json = JSON.stringify(canvas.toJSON());
      undoStackRef.current.push(json);
      if (undoStackRef.current.length > MAX_UNDO_HISTORY) {
        undoStackRef.current.shift();
      }
      redoStackRef.current = [];
    },
    []
  );

  const handleUndo = useCallback((): void => {
    const canvas = fabricRef.current;
    if (!canvas || undoStackRef.current.length === 0) return;

    const currentState = JSON.stringify(canvas.toJSON());
    redoStackRef.current.push(currentState);

    const prevState = undoStackRef.current.pop();
    if (prevState) {
       
      canvas.loadFromJSON(JSON.parse(prevState)).then(() => {
         
        canvas.renderAll();
      });
    }
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
         
        canvas.renderAll();
      });
    }
    setIsDirty(true);
  }, []);

  // -----------------------------------------------------------------------
  // Deletion (REQ-L2-CV-001..004)
  // -----------------------------------------------------------------------

  /**
   * Remove the current selection and any connectors/arrowheads anchored to it.
   *
   * Deleting a shape must not leave dangling connectors: every fabric.Line whose
   * `data.fromId`/`data.toId` references a removed shape is removed too, along
   * with the arrowhead Triangle carrying the matching `data.connectorId`.
   */
  const deleteActiveObjects = useCallback(
    (canvas: FabricCanvas): void => {
      const active = canvas.getActiveObjects?.() ?? [];
      if (active.length === 0) return;

      const toRemove = new Set<unknown>(active);
      const removedShapeIds = new Set<string>(
        active
          .map((o: Record<string, unknown>) => (o.data as { id?: string } | undefined)?.id)
          .filter((id: string | undefined): id is string => Boolean(id))
      );

      // Cascade: connectors referencing a removed shape (or selected directly).
      for (const obj of canvas.getObjects() as Record<string, unknown>[]) {
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
          .map((o) => (o as Record<string, unknown>).data as { type?: string; id?: string } | undefined)
          .filter((d): d is { type?: string; id?: string } => d?.type === "connector")
          .map((d) => d.id)
          .filter((id): id is string => Boolean(id))
      );
      for (const obj of canvas.getObjects() as Record<string, unknown>[]) {
        const data = obj.data as { type?: string; connectorId?: string } | undefined;
        if (data?.type === "arrowHead" && data.connectorId && removedConnectorIds.has(data.connectorId)) {
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
        backgroundColor: "#ffffff",
        isDrawingMode: true,
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      function createConnector(cv: FabricCanvas, fab: any, src: Record<string, unknown>, tgt: Record<string, unknown>): void {
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

        const line = new fab.Line([s.x, s.y, tp.x, tp.y], {
          stroke: colorRef.current,
          strokeWidth: widthRef.current,
          selectable: true,
          evented: true,
          data: { type: "connector", id: lineId, fromId: srcData?.id, toId: tgtData?.id },
        });

        const angle = (Math.atan2(tp.y - s.y, tp.x - s.x) * 180) / Math.PI + 90;
        const head = new fab.Triangle({
          left: tp.x,
          top: tp.y,
          width: 12,
          height: 12,
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
       * rect/ellipse: begin a drag-draw. text: drop an editable Textbox.
       * connector: pick source on 1st click, draw connector on 2nd click.
       */
      canvas.on("mouse:down", (opt: { e: Event; target?: unknown }) => {
        const tool = activeToolRef.current;
        if (tool !== "rect" && tool !== "ellipse" && tool !== "text" && tool !== "connector") {
          return;
        }
        const pointer = canvas.getPointer(opt.e);

        if (tool === "rect" || tool === "ellipse") {
          const common = {
            left: pointer.x,
            top: pointer.y,
            fill: "transparent",
            stroke: colorRef.current,
            strokeWidth: widthRef.current,
            selectable: false,
            evented: false,
            data: { id: makeObjectId(), type: tool },
          };
          const obj =
            tool === "rect"
              ? new fabric.Rect({ ...common, width: 0, height: 0 })
              : new fabric.Ellipse({ ...common, rx: 0, ry: 0 });
          canvas.add(obj);
          drawingRef.current = { obj, originX: pointer.x, originY: pointer.y };
          return;
        }

        if (tool === "text") {
          const textbox = new fabric.Textbox("Text", {
            left: pointer.x,
            top: pointer.y,
            fontSize: 16,
            fill: colorRef.current,
            editable: true,
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

        // connector
        const target = canvas.findTarget?.(opt.e) ?? null;
        if (!connectorSourceRef.current) {
          if (target) connectorSourceRef.current = target;
          return;
        }
        const src = connectorSourceRef.current;
        connectorSourceRef.current = null;
        if (!target || target === src) return;
        createConnector(canvas, fabric, src, target);
      });

      /** mouse:move — live-resize the shape currently being drawn. */
      canvas.on("mouse:move", (opt: { e: Event }) => {
        const drawing = drawingRef.current;
        if (!drawing) return;
        const tool = activeToolRef.current;
        if (tool !== "rect" && tool !== "ellipse") return;

        const pointer = canvas.getPointer(opt.e);
        const left = Math.min(pointer.x, drawing.originX);
        const top = Math.min(pointer.y, drawing.originY);
        const width = Math.abs(pointer.x - drawing.originX);
        const height = Math.abs(pointer.y - drawing.originY);

        if (tool === "rect") {
          drawing.obj.set({ left, top, width, height });
        } else {
          drawing.obj.set({ left, top, rx: width / 2, ry: height / 2 });
        }
        drawing.obj.setCoords();
        canvas.renderAll();
      });

      /** mouse:up — finalize the drawn shape and snapshot for undo. */
      canvas.on("mouse:up", () => {
        const drawing = drawingRef.current;
        if (!drawing) return;
        drawingRef.current = null;
        drawing.obj.set({ selectable: true, evented: true });
        drawing.obj.setCoords();
        pushUndoState(canvas);
        setIsDirty(true);
        canvas.renderAll();
      });

      /** mouse:dblclick — re-enter editing on an existing text box. */
      canvas.on("mouse:dblclick", (opt: { target?: Record<string, unknown> }) => {
        const target = opt.target;
        const data = target?.data as { type?: string } | undefined;
        if (target && data?.type === "text" && typeof target.enterEditing === "function") {
          (target.enterEditing as () => void)();
          canvas.renderAll();
        }
      });

      canvas.on("text:changed", () => setIsDirty(true));
      canvas.on("editing:exited", () => {
        pushUndoState(canvas);
        setIsDirty(true);
      });

      /**
       * object:moving — keep connectors glued to their anchor shapes
       * (REQ-L2-CV-004). Recomputes both line endpoints (clipped to each shape's
       * bounding-box edge via getEdgePoint) and the arrowhead pose from the
       * live positions of the anchored shapes.
       */
      canvas.on("object:moving", (opt: { target?: Record<string, unknown> }) => {
        const moved = opt.target;
        const movedData = moved?.data as { id?: string } | undefined;
        if (!moved || !movedData?.id) return;
        const movedId = movedData.id;
        const allObjects = canvas.getObjects() as Record<string, unknown>[];

        for (const obj of allObjects) {
          const data = obj.data as
            | { type?: string; id?: string; fromId?: string; toId?: string }
            | undefined;
          if (data?.type !== "connector") continue;
          const isFrom = data.fromId === movedId;
          const isTo = data.toId === movedId;
          if (!isFrom && !isTo) continue;

          // Resolve both anchored shapes; use the live-moved instance so its
          // current position is reflected before setCoords() commits.
          const findById = (id?: string): Record<string, unknown> | undefined => {
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
        canvas.renderAll();
      });

      fabricRef.current = canvas;

      // Restore prior canvas state (REQ-L2-CV-005). Full Fabric serialization
      // takes precedence over the legacy stroke-replay path.
      if (initialCanvasJson && Array.isArray(initialCanvasJson.objects)) {
        isLoadingRef.current = true;
        const result = canvas.loadFromJSON(initialCanvasJson, () => {
          canvas.renderAll();
        });
        Promise.resolve(result).then(() => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagramId]);

  // -----------------------------------------------------------------------
  // Tool switching
  // -----------------------------------------------------------------------

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    switch (activeTool) {
      case "pen": {
        canvas.isDrawingMode = true;
        canvas.selection = false;
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
        break;
      }
      case "eraser": {
        canvas.isDrawingMode = true;
        canvas.selection = false;
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
        drawingRef.current = null;
        connectorSourceRef.current = null;
        break;
      }
    }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isInitialized, performAutoSave]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className={styles.container} data-testid="canvas-editor">
      {/* Toolbar */}
      <div className={styles.toolbar} data-testid="canvas-toolbar">
        {/* Tool buttons */}
        <button
          type="button"
          data-testid="canvas-tool-pen"
          className={`${styles.toolButton} ${activeTool === "pen" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("pen")}
          title={t("canvas.toolbar.pen", "Pen")}
          aria-label={t("canvas.toolbar.pen", "Pen")}
        >
          ✏️
        </button>
        <button
          type="button"
          data-testid="canvas-tool-select"
          className={`${styles.toolButton} ${activeTool === "select" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("select")}
          title={t("canvas.toolbar.select", "Select")}
          aria-label={t("canvas.toolbar.select", "Select")}
        >
          ↖
        </button>
        <button
          type="button"
          data-testid="canvas-tool-eraser"
          className={`${styles.toolButton} ${activeTool === "eraser" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("eraser")}
          title={t("canvas.toolbar.eraser", "Eraser")}
          aria-label={t("canvas.toolbar.eraser", "Eraser")}
        >
          🧹
        </button>

        <div className={styles.toolbarSeparator} />

        {/* Shape / text / connector tools (REQ-L2-CV-001..004) */}
        <button
          type="button"
          data-testid="canvas-tool-rect"
          className={`${styles.toolButton} ${styles.shapeTool} ${activeTool === "rect" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("rect")}
          title={t("canvas.toolbar.rect", "Rectangle")}
          aria-label={t("canvas.toolbar.rect", "Rectangle")}
        >
          ▭
        </button>
        <button
          type="button"
          data-testid="canvas-tool-ellipse"
          className={`${styles.toolButton} ${styles.shapeTool} ${activeTool === "ellipse" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("ellipse")}
          title={t("canvas.toolbar.ellipse", "Ellipse")}
          aria-label={t("canvas.toolbar.ellipse", "Ellipse")}
        >
          ◯
        </button>
        <button
          type="button"
          data-testid="canvas-tool-text"
          className={`${styles.toolButton} ${styles.shapeTool} ${activeTool === "text" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("text")}
          title={t("canvas.toolbar.text", "Text")}
          aria-label={t("canvas.toolbar.text", "Text")}
        >
          T
        </button>
        <button
          type="button"
          data-testid="canvas-tool-connector"
          className={`${styles.toolButton} ${styles.shapeTool} ${activeTool === "connector" ? styles.toolButtonActive : ""}`}
          onClick={() => setActiveTool("connector")}
          title={t("canvas.toolbar.connector", "Connector")}
          aria-label={t("canvas.toolbar.connector", "Connector")}
        >
          →
        </button>

        <div className={styles.toolbarSeparator} />

        {/* Color picker */}
        <input
          type="color"
          data-testid="canvas-color-picker"
          className={styles.colorPicker}
          value={color}
          onChange={(e) => setColor(e.target.value)}
          title={t("canvas.toolbar.color", "Color")}
          aria-label={t("canvas.toolbar.color", "Color")}
        />

        {/* Quick-color swatches */}
        {TOOLBAR_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            data-testid={`canvas-color-${c.replace("#", "")}`}
            className={styles.toolButton}
            style={{
              background: c,
              border: color === c ? "2px solid var(--color-primary)" : "2px solid var(--color-border)",
              minWidth: 20,
              height: 20,
              padding: 0,
            }}
            onClick={() => setColor(c)}
            aria-label={`Color ${c}`}
          />
        ))}

        <div className={styles.toolbarSeparator} />

        {/* Stroke width */}
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

        <div className={styles.toolbarSeparator} />

        {/* Undo / Redo */}
        <button
          type="button"
          data-testid="canvas-undo"
          className={styles.toolButton}
          onClick={handleUndo}
          disabled={undoStackRef.current.length === 0}
          title={t("canvas.toolbar.undo", "Undo (Ctrl+Z)")}
          aria-label={t("canvas.toolbar.undo", "Undo")}
        >
          ↩
        </button>
        <button
          type="button"
          data-testid="canvas-redo"
          className={styles.toolButton}
          onClick={handleRedo}
          disabled={redoStackRef.current.length === 0}
          title={t("canvas.toolbar.redo", "Redo (Ctrl+Y)")}
          aria-label={t("canvas.toolbar.redo", "Redo")}
        >
          ↪
        </button>

        <div className={styles.toolbarSeparator} />

        {/* Manual save */}
        <button
          type="button"
          data-testid="canvas-save-btn"
          className={styles.toolButton}
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
      <div className={styles.canvasWrapper} data-testid="canvas-wrapper">
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

/**
 * Bounding-box center of a Fabric object. Prefers getBoundingRect() and falls
 * back to left/top + width/height for lightweight/mocked objects.
 */
function boundingCenter(obj: Record<string, unknown>): { x: number; y: number } {
  if (typeof obj.getBoundingRect === "function") {
    const r = (obj.getBoundingRect as () => { left: number; top: number; width: number; height: number })();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  const left = (obj.left as number) ?? 0;
  const top = (obj.top as number) ?? 0;
  const width = (obj.width as number) ?? 0;
  const height = (obj.height as number) ?? 0;
  return { x: left + width / 2, y: top + height / 2 };
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
