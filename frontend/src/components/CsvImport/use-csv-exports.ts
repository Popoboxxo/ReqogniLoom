/**
 * ARCH-L1-001 ReactFrontend — CSV and ReqIF export (#598 S2).
 *
 * Extracted from `CsvImport.tsx`: the two download actions share one shape
 * (entity type for CSV, a fixed bundle for ReqIF) and are independent of the
 * import, preview and drag-and-drop state the page also carries.
 *
 * Contract kept verbatim: the chosen CSV entity type is sent as-is, both
 * buttons disable only their own request, and a failure keeps its own message
 * next to the button instead of a shared page-level banner.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { exportApi } from "../../api/export";
import type { ExportEntityType } from "../../api/export";

export interface UseCsvExportsOptions {
  workspaceId: string | undefined;
  t: TFunction;
}

export interface UseCsvExportsResult {
  exportEntityType: ExportEntityType;
  setExportEntityType: (type: ExportEntityType) => void;
  isExporting: boolean;
  exportError: string | null;
  handleExport: () => Promise<void>;
  isExportingReqif: boolean;
  reqifExportError: string | null;
  handleExportReqif: () => Promise<void>;
}

export function useCsvExports({
  workspaceId,
  t,
}: UseCsvExportsOptions): UseCsvExportsResult {
  const [exportEntityType, setExportEntityType] =
    useState<ExportEntityType>("Requirement");
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isExportingReqif, setIsExportingReqif] = useState(false);
  const [reqifExportError, setReqifExportError] = useState<string | null>(null);

  const handleExport = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setIsExporting(true);
    setExportError(null);
    try {
      await exportApi.downloadCsv(workspaceId, exportEntityType);
    } catch (err) {
      setExportError(
        err instanceof Error ? err.message : t("export.errorGeneric", "Export failed")
      );
    } finally {
      setIsExporting(false);
    }
  }, [workspaceId, exportEntityType, t]);

  // REQ-146: ReqIF 1.2 export (StakeholderNeeds, Requirements, TraceLinks).
  const handleExportReqif = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setIsExportingReqif(true);
    setReqifExportError(null);
    try {
      await exportApi.downloadReqif(workspaceId);
    } catch (err) {
      setReqifExportError(
        err instanceof Error ? err.message : t("export.errorGeneric", "Export failed")
      );
    } finally {
      setIsExportingReqif(false);
    }
  }, [workspaceId, t]);

  return {
    exportEntityType,
    setExportEntityType,
    isExporting,
    exportError,
    handleExport,
    isExportingReqif,
    reqifExportError,
    handleExportReqif,
  };
}
