/**
 * ARCH-L1-001 ReactFrontend — attribute editor view mode (#598 S2).
 *
 * Extracted from `AttributeEditorPage.tsx`: the list/table switch and its
 * per-viewer persistence. Never load-bearing — private browsing or a disabled
 * store falls back to "list" (the defensive wrapper absorbs lockouts).
 */

import { useCallback, useState } from "react";

import { safeLocalStorage } from "../../utils/safeStorage";

export type AttributeViewMode = "list" | "table";

const VIEW_MODE_STORAGE_KEY = "attributeEditor.viewMode";

function loadViewMode(): AttributeViewMode {
  return safeLocalStorage.getItem(VIEW_MODE_STORAGE_KEY) === "table"
    ? "table"
    : "list";
}

export interface UseAttributeViewModeResult {
  viewMode: AttributeViewMode;
  setViewMode: (mode: AttributeViewMode) => void;
}

export function useAttributeViewMode(): UseAttributeViewModeResult {
  const [viewMode, setViewModeState] = useState<AttributeViewMode>(loadViewMode);

  const setViewMode = useCallback((mode: AttributeViewMode): void => {
    setViewModeState(mode);
    // Same non-load-bearing contract as `loadViewMode`.
    safeLocalStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
  }, []);

  return { viewMode, setViewMode };
}
