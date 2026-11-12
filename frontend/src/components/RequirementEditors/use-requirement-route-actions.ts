/**
 * ARCH-L1-001 ReactFrontend — requirement route actions (#598 S2).
 *
 * Extracted from `RequirementEditors.tsx`: the PDF export and the AI
 * TestCase-draft panel toggle. Both are route-level actions, independent of the
 * create form, the AI decomposition and the list.
 *
 * Contract kept verbatim: a failed export reports through the page's action
 * banner (#340) instead of dying in the console, and the panel opens/closes as
 * a plain toggle.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { workspacesApi } from "../../api/workspaces";
import { extractApiErrorMessage } from "../../api/client";

export interface UseRequirementRouteActionsOptions {
  workspaceId: string | undefined;
  t: TFunction;
  /** The page-level action banner is shared with delete, so it owns the setter. */
  onError: (message: string | null) => void;
}

export interface UseRequirementRouteActionsResult {
  isExportingPdf: boolean;
  showDeriveTestcasePanel: boolean;
  exportPdf: () => Promise<void>;
  openDeriveTestcasePanel: () => void;
  closeDeriveTestcasePanel: () => void;
}

export function useRequirementRouteActions({
  workspaceId,
  t,
  onError,
}: UseRequirementRouteActionsOptions): UseRequirementRouteActionsResult {
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [showDeriveTestcasePanel, setShowDeriveTestcasePanel] = useState(false);

  const exportPdf = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setIsExportingPdf(true);
    onError(null);
    try {
      const blob = await workspacesApi.downloadPdfReport(workspaceId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `requirement_document_${workspaceId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      // #340: a failed export produced no download and no message at all.
      onError(extractApiErrorMessage(err) ?? t("req.pdfExportFailed"));
    } finally {
      setIsExportingPdf(false);
    }
  }, [workspaceId, t, onError]);

  const openDeriveTestcasePanel = useCallback((): void => {
    setShowDeriveTestcasePanel(true);
  }, []);

  const closeDeriveTestcasePanel = useCallback((): void => {
    setShowDeriveTestcasePanel(false);
  }, []);

  return {
    isExportingPdf,
    showDeriveTestcasePanel,
    exportPdf,
    openDeriveTestcasePanel,
    closeDeriveTestcasePanel,
  };
}
