/**
 * ARCH-L1-001 ReactFrontend — canvas tool settings (#598 S2).
 *
 * Extracted from `CanvasEditor.tsx`: the six palette/tool settings are pure UI
 * state with no canvas dependency. The editor keeps the fabric canvas, history,
 * zoom and save lifecycle; this module owns what the toolbar edits.
 *
 * The editor mirrors these values into refs so canvas handlers bound once at
 * init read the current tool without being re-bound — that sync stays in the
 * component because it is canvas lifecycle, not setting ownership.
 */

import { useState } from "react";

import type { CanvasTool } from "../../types";

export type LineStyle = "solid" | "dashed";

export interface UseCanvasToolSettingsResult {
  activeTool: CanvasTool;
  setActiveTool: React.Dispatch<React.SetStateAction<CanvasTool>>;
  color: string;
  setColor: React.Dispatch<React.SetStateAction<string>>;
  fillColor: string;
  setFillColor: React.Dispatch<React.SetStateAction<string>>;
  lineStyle: LineStyle;
  setLineStyle: React.Dispatch<React.SetStateAction<LineStyle>>;
  strokeWidth: number;
  setStrokeWidth: React.Dispatch<React.SetStateAction<number>>;
  snapEnabled: boolean;
  setSnapEnabled: React.Dispatch<React.SetStateAction<boolean>>;
}

export function useCanvasToolSettings(): UseCanvasToolSettingsResult {
  const [activeTool, setActiveTool] = useState<CanvasTool>("select");
  const [color, setColor] = useState("#1f2937");
  const [fillColor, setFillColor] = useState("#ffffff");
  const [lineStyle, setLineStyle] = useState<LineStyle>("solid");
  const [strokeWidth, setStrokeWidth] = useState(2);
  const [snapEnabled, setSnapEnabled] = useState(true);

  return {
    activeTool,
    setActiveTool,
    color,
    setColor,
    fillColor,
    setFillColor,
    lineStyle,
    setLineStyle,
    strokeWidth,
    setStrokeWidth,
    snapEnabled,
    setSnapEnabled,
  };
}
