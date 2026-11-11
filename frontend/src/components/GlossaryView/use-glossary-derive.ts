/**
 * ARCH-L1-001 ReactFrontend — glossary AI derivation (#598 S2, #1358/#1360).
 *
 * Extracted from `GlossaryView.tsx`: the preview/confirm lifecycle of the
 * shared AI review dialog is independent of the term list, the form and the
 * synonym linking state.
 *
 * Contract kept verbatim:
 *   - the preview is `ephemeral: true` — Discard writes nothing,
 *   - Confirm and "Review later" both persist through the same `mode="write"`
 *     seam (#1089); only the success message differs (created now vs. parked
 *     for the review queue),
 *   - a successful write reloads the term list,
 *   - preview and submit failures stay separate.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { glossaryApi } from "../../api/glossary";
import { extractErrorMessage } from "../../api/client";
import type { AiDerivationDraft } from "../shared/AiDerivationDialog";

export interface UseGlossaryDeriveOptions {
  workspaceId: string | undefined;
  t: TFunction;
  /** Re-read the term list after a successful write. */
  reloadTerms: () => void;
}

export interface UseGlossaryDeriveResult {
  deriveOpen: boolean;
  deriveDrafts: AiDerivationDraft[] | null;
  deriveLoading: boolean;
  deriveLoadError: string | null;
  deriveSaving: boolean;
  deriveSubmitError: string | null;
  deriveStatus: string | null;
  openDeriveDialog: () => Promise<void>;
  closeDeriveDialog: () => void;
  handleDeriveDecision: (parked: boolean) => Promise<void>;
}

export function useGlossaryDerive({
  workspaceId,
  t,
  reloadTerms,
}: UseGlossaryDeriveOptions): UseGlossaryDeriveResult {
  const [deriveOpen, setDeriveOpen] = useState(false);
  const [deriveDrafts, setDeriveDrafts] = useState<AiDerivationDraft[] | null>(null);
  const [deriveLoading, setDeriveLoading] = useState(false);
  const [deriveLoadError, setDeriveLoadError] = useState<string | null>(null);
  const [deriveSaving, setDeriveSaving] = useState(false);
  const [deriveSubmitError, setDeriveSubmitError] = useState<string | null>(null);
  const [deriveStatus, setDeriveStatus] = useState<string | null>(null);

  const closeDeriveDialog = useCallback((): void => {
    setDeriveOpen(false);
    setDeriveDrafts(null);
    setDeriveLoadError(null);
    setDeriveSubmitError(null);
  }, []);

  const openDeriveDialog = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    setDeriveOpen(true);
    setDeriveDrafts(null);
    setDeriveLoadError(null);
    setDeriveSubmitError(null);
    setDeriveLoading(true);
    try {
      const preview = await glossaryApi.derivePreview(workspaceId);
      setDeriveDrafts(
        preview.drafts.map((draft) => ({
          title: draft.term,
          description: draft.definition,
        }))
      );
    } catch (err) {
      setDeriveLoadError(extractErrorMessage(err) || t("glossary.deriveFailed"));
    } finally {
      setDeriveLoading(false);
    }
  }, [workspaceId, t]);

  const handleDeriveDecision = useCallback(
    async (parked: boolean): Promise<void> => {
      if (!workspaceId) return;
      setDeriveSaving(true);
      setDeriveSubmitError(null);
      try {
        const receipt = await glossaryApi.deriveWrite(workspaceId);
        setDeriveStatus(
          t(parked ? "aiDerivation.statusParked" : "aiDerivation.statusCreated", {
            count: receipt.written.length,
          })
        );
        closeDeriveDialog();
        reloadTerms();
      } catch (err) {
        setDeriveSubmitError(extractErrorMessage(err) || t("glossary.deriveFailed"));
      } finally {
        setDeriveSaving(false);
      }
    },
    [workspaceId, t, closeDeriveDialog, reloadTerms]
  );

  return {
    deriveOpen,
    deriveDrafts,
    deriveLoading,
    deriveLoadError,
    deriveSaving,
    deriveSubmitError,
    deriveStatus,
    openDeriveDialog,
    closeDeriveDialog,
    handleDeriveDecision,
  };
}
