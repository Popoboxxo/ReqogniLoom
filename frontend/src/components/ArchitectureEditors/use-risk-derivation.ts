/**
 * ARCH-L1-001 ReactFrontend — AI risk derivation dialog (#598 S2, #1360).
 *
 * Extracted from `ArchitectureEditors.tsx`: the preview/confirm lifecycle of
 * the shared AI review dialog is independent of the editor's list, create and
 * decompose state, so it owns its own module now.
 *
 * Flow: `openRiskDialog()` loads the `derive-risks` preview (`ephemeral: true`)
 * into drafts; Confirm / "Review later" call the `mode="write"` seam through
 * `decide(parked)`, which closes the dialog and reports a status line.
 * Load and submit failures are kept apart — a failed preview must not look like
 * a failed commit.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { architectureApi } from "../../api/architecture";
import type { AiDerivationDraft } from "../shared/AiDerivationDialog";
import type { ArchitectureElement } from "../../types";

interface ApiErrorShape {
  error?: { message?: string };
}

export interface UseRiskDerivationResult {
  riskOpen: boolean;
  riskDrafts: AiDerivationDraft[] | null;
  riskLoading: boolean;
  riskLoadError: string | null;
  riskSaving: boolean;
  riskSubmitError: string | null;
  riskStatus: string | null;
  openRiskDialog: () => Promise<void>;
  closeRiskDialog: () => void;
  decide: (parked: boolean) => Promise<void>;
}

export function useRiskDerivation(
  element: ArchitectureElement | null,
  t: TFunction
): UseRiskDerivationResult {
  const [riskOpen, setRiskOpen] = useState(false);
  const [riskDrafts, setRiskDrafts] = useState<AiDerivationDraft[] | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskLoadError, setRiskLoadError] = useState<string | null>(null);
  const [riskSaving, setRiskSaving] = useState(false);
  const [riskSubmitError, setRiskSubmitError] = useState<string | null>(null);
  const [riskStatus, setRiskStatus] = useState<string | null>(null);

  const closeRiskDialog = useCallback((): void => {
    setRiskOpen(false);
    setRiskDrafts(null);
    setRiskLoadError(null);
    setRiskSubmitError(null);
  }, []);

  const openRiskDialog = useCallback(async (): Promise<void> => {
    if (!element) return;
    setRiskOpen(true);
    setRiskDrafts(null);
    setRiskLoadError(null);
    setRiskSubmitError(null);
    setRiskLoading(true);
    try {
      const preview = await architectureApi.deriveRisksPreview(element.id);
      setRiskDrafts(
        preview.drafts.map((draft) => ({
          title: draft.title,
          description: draft.description,
        }))
      );
    } catch (err: unknown) {
      const apiErr = err as ApiErrorShape;
      setRiskLoadError(apiErr?.error?.message ?? t("needs.deriveFailed"));
    } finally {
      setRiskLoading(false);
    }
  }, [element, t]);

  const decide = useCallback(
    async (parked: boolean): Promise<void> => {
      if (!element) return;
      setRiskSaving(true);
      setRiskSubmitError(null);
      try {
        const receipt = await architectureApi.deriveRisksWrite(element.id);
        setRiskStatus(
          t(parked ? "aiDerivation.statusParked" : "aiDerivation.statusCreated", {
            count: receipt.written.length,
          })
        );
        closeRiskDialog();
      } catch (err: unknown) {
        const apiErr = err as ApiErrorShape;
        setRiskSubmitError(apiErr?.error?.message ?? t("needs.deriveFailed"));
      } finally {
        setRiskSaving(false);
      }
    },
    [element, t, closeRiskDialog]
  );

  return {
    riskOpen,
    riskDrafts,
    riskLoading,
    riskLoadError,
    riskSaving,
    riskSubmitError,
    riskStatus,
    openRiskDialog,
    closeRiskDialog,
    decide,
  };
}
