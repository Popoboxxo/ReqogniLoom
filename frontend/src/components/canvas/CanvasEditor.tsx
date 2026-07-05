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
import type { CanvasStroke, CanvasStrokeData, CanvasTool } from "../../types";
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
  // Auto-Save (IF-L1-058)
  // -----------------------------------------------------------------------

  const performAutoSave = useCallback(async (): Promise<void> => {
    const canvas = fabricRef.current;
    if (!canvas || !isDirty) return;

    setSaveStatus("saving");
    try {
      const strokeData = extractStrokeData(canvas);

      await diagramsApi.saveCanvasStrokes(diagramId, {
        strokes: strokeData.strokes,
        width: strokeData.width,
        height: strokeData.height,
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

      fabricRef.current = canvas;

      // Load initial strokes if provided
      if (initialStrokes && initialStrokes.length > 0) {
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
    }
  }, [activeTool, color, strokeWidth]);

  // -----------------------------------------------------------------------
  // Keyboard shortcuts
  // -----------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
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
  }, [handleUndo, handleRedo]);

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
