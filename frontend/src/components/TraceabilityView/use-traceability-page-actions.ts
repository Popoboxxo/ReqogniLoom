/**
 * ARCH-L1-001 ReactFrontend — traceability page actions (#598 S2).
 *
 * Extracted from `TraceabilityView.tsx`: the create-link dialog lifecycle, the
 * reload counter it bumps, and the PDF export are page-level actions,
 * independent of the data load, the filters and the impact hand-off.
 *
 * Contract kept verbatim: creating a link closes the dialog and increments the
 * reload key (the data hook keys off it); the export downloads
 * `traceability_matrix` for the active workspace and a failure only logs (the
 * page has no error banner for it).
 */

import { useCallback, useState } from "react";

import { workspacesApi } from "../../api/workspaces";

export interface UseTraceabilityPageActionsOptions {
  workspaceId: string | undefined;
}

export interface UseTraceabilityPageActionsResult {
  showCreateDialog: boolean;
  reloadKey: number;
  isExportingPdf: boolean;
  openCreateDialog: () => void;
  closeCreateDialog: () => void;
  handleCreated: () => void;
  exportPdf: () => Promise<void>;
}

export function useTraceabilityPageActions({
  workspaceId,
}: UseTraceabilityPageActionsOptions): UseTraceabilityPageActionsResult {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

  const openCreateDialog = useCallback((): void => {
    setShowCreateDialog(true);
  }, []);

  const closeCreateDialog = useCallback((): void => {
    setShowCreateDialog(false);
  }, []);

  const handleCreated = useCallback((): void => {
    setShowCreateDialog(false);
    setReloadKey((key) => key + 1);
  }, []);

  const exportPdf = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setIsExportingPdf(true);
    try {
      const blob = await workspacesApi.downloadPdfReport(
        workspaceId,
        "traceability_matrix"
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `traceability_matrix_${workspaceId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF export failed:", err);
    } finally {
      setIsExportingPdf(false);
    }
  }, [workspaceId]);

  return {
    showCreateDialog,
    reloadKey,
    isExportingPdf,
    openCreateDialog,
    closeCreateDialog,
    handleCreated,
    exportPdf,
  };
}
