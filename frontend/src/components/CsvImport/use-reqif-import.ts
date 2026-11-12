/**
 * ARCH-L1-001 ReactFrontend — ReqIF 1.2 import (#598 S2, REQ-147, ADR-014 §3).
 *
 * Extracted from `CsvImport.tsx`: the ReqIF section is independent of the CSV
 * import, the CSV/ReqIF exports and the preview.
 *
 * Contract kept verbatim:
 *   - one Idempotency-Key per selected file/attempt, so a retry after a partial
 *     failure replays without a second write effect,
 *   - a new file selection starts a new key scope,
 *   - reset clears the file input, the result, the error and the key,
 *   - the dry-run switch is sent verbatim.
 */

import { useCallback, useRef, useState } from "react";
import type { TFunction } from "i18next";

import { importApi, type ReqifImportResult } from "../../api/import";
import { generateIdempotencyUuid } from "./idempotency";

export interface UseReqifImportOptions {
  workspaceId: string | undefined;
  t: TFunction;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
}

export interface UseReqifImportResult {
  selectedReqifFile: File | null;
  reqifDryRun: boolean;
  isImportingReqif: boolean;
  reqifImportResult: ReqifImportResult | null;
  reqifImportError: string | null;
  setReqifDryRun: (value: boolean) => void;
  handleReqifFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleReqifImport: () => Promise<void>;
  handleReqifReset: () => void;
}

export function useReqifImport({
  workspaceId,
  t,
  fileInputRef,
}: UseReqifImportOptions): UseReqifImportResult {
  const [selectedReqifFile, setSelectedReqifFile] = useState<File | null>(null);
  const [reqifDryRun, setReqifDryRun] = useState(false);
  const [isImportingReqif, setIsImportingReqif] = useState(false);
  const [reqifImportResult, setReqifImportResult] = useState<ReqifImportResult | null>(null);
  const [reqifImportError, setReqifImportError] = useState<string | null>(null);
  // ADR-014 §3: one key per selected file/attempt.
  const reqifIdempotencyKeyRef = useRef<string | null>(null);

  const handleReqifFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const file = event.target.files?.[0] ?? null;
      setSelectedReqifFile(file);
      setReqifImportResult(null);
      setReqifImportError(null);
      // A new file selection starts a new idempotency scope.
      reqifIdempotencyKeyRef.current = file
        ? `reqif-${generateIdempotencyUuid()}`
        : null;
    },
    []
  );

  const handleReqifImport = useCallback(async (): Promise<void> => {
    if (!selectedReqifFile || !workspaceId) return;
    setIsImportingReqif(true);
    setReqifImportError(null);
    setReqifImportResult(null);
    try {
      const importResult = await importApi.importReqif(
        workspaceId,
        selectedReqifFile,
        reqifDryRun,
        reqifIdempotencyKeyRef.current ?? undefined
      );
      setReqifImportResult(importResult);
    } catch (err) {
      setReqifImportError(
        err instanceof Error ? err.message : t("import.errorGeneric", "Import failed")
      );
    } finally {
      setIsImportingReqif(false);
    }
  }, [selectedReqifFile, workspaceId, reqifDryRun, t]);

  const handleReqifReset = useCallback((): void => {
    setSelectedReqifFile(null);
    setReqifImportResult(null);
    setReqifImportError(null);
    reqifIdempotencyKeyRef.current = null;
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [fileInputRef]);

  return {
    selectedReqifFile,
    reqifDryRun,
    isImportingReqif,
    reqifImportResult,
    reqifImportError,
    setReqifDryRun,
    handleReqifFileSelect,
    handleReqifImport,
    handleReqifReset,
  };
}
