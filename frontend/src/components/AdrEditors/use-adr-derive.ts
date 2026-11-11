/**
 * ARCH-L1-001 ReactFrontend — ADR AI derivation (#598 S2, #1358/#1360).
 *
 * Extracted from `AdrEditors.tsx`: the decision-text preview and the shared
 * review dialog are independent of the ADR list, the create dialog and the
 * artifact form.
 *
 * Contract kept verbatim:
 *   - the dialog opens with an empty decision field; `mode="write"` is only
 *     reachable after a preview (`ephemeral: true`),
 *   - the preview folds context and consequences into the dialog's description
 *     so the reviewer sees every part the write will persist,
 *   - Confirm and "Review later" share the write seam (count is always 1, an
 *     ADR is a single draft); only the success message differs,
 *   - a successful write refreshes the list.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { adrsApi } from "../../api/adrs";
import type { AiDerivationDraft } from "../shared/AiDerivationDialog";

interface ApiErrorShape {
  error?: { message?: string };
}

export interface UseAdrDeriveOptions {
  workspaceId: string | undefined;
  t: TFunction;
  refresh: () => void;
}

export interface UseAdrDeriveResult {
  deriveOpen: boolean;
  deriveDecision: string;
  setDeriveDecision: (value: string) => void;
  deriveDrafts: AiDerivationDraft[] | null;
  deriveLoading: boolean;
  deriveLoadError: string | null;
  deriveSaving: boolean;
  deriveSubmitError: string | null;
  deriveStatus: string | null;
  openDeriveDialog: () => void;
  closeDeriveDialog: () => void;
  handleDerivePreview: () => Promise<void>;
  handleDeriveDecision: (parked: boolean) => Promise<void>;
}

export function useAdrDerive({
  workspaceId,
  t,
  refresh,
}: UseAdrDeriveOptions): UseAdrDeriveResult {
  const [deriveOpen, setDeriveOpen] = useState(false);
  const [deriveDecision, setDeriveDecision] = useState("");
  const [deriveDrafts, setDeriveDrafts] = useState<AiDerivationDraft[] | null>(null);
  const [deriveLoading, setDeriveLoading] = useState(false);
  const [deriveLoadError, setDeriveLoadError] = useState<string | null>(null);
  const [deriveSaving, setDeriveSaving] = useState(false);
  const [deriveSubmitError, setDeriveSubmitError] = useState<string | null>(null);
  const [deriveStatus, setDeriveStatus] = useState<string | null>(null);

  const openDeriveDialog = useCallback((): void => {
    setDeriveDecision("");
    setDeriveDrafts(null);
    setDeriveLoadError(null);
    setDeriveSubmitError(null);
    setDeriveOpen(true);
  }, []);

  const closeDeriveDialog = useCallback((): void => {
    setDeriveOpen(false);
    setDeriveDrafts(null);
    setDeriveLoadError(null);
    setDeriveSubmitError(null);
  }, []);

  const handleDerivePreview = useCallback(async (): Promise<void> => {
    if (!workspaceId || !deriveDecision.trim()) return;
    setDeriveLoading(true);
    setDeriveLoadError(null);
    try {
      const preview = await adrsApi.derivePreview(workspaceId, deriveDecision.trim());
      const draft = preview.draft;
      setDeriveDrafts([
        {
          title: draft.title,
          // The reviewer sees every part the write will persist; the shared
          // dialog row is title/description/rationale, so context and
          // consequences are folded into the body.
          description: [
            draft.description,
            draft.context ? `${t("aiDerivation.adrContext")}: ${draft.context}` : null,
            draft.consequences
              ? `${t("aiDerivation.adrConsequences")}: ${draft.consequences}`
              : null,
          ]
            .filter(Boolean)
            .join("\n\n"),
        },
      ]);
    } catch (err: unknown) {
      const apiErr = err as ApiErrorShape;
      setDeriveLoadError(apiErr?.error?.message ?? t("needs.deriveFailed"));
    } finally {
      setDeriveLoading(false);
    }
  }, [workspaceId, deriveDecision, t]);

  const handleDeriveDecision = useCallback(
    async (parked: boolean): Promise<void> => {
      if (!workspaceId || !deriveDecision.trim()) return;
      setDeriveSaving(true);
      setDeriveSubmitError(null);
      try {
        await adrsApi.deriveWrite(workspaceId, deriveDecision.trim());
        setDeriveStatus(
          t(parked ? "aiDerivation.statusParked" : "aiDerivation.statusCreated", {
            count: 1,
          })
        );
        closeDeriveDialog();
        refresh();
      } catch (err: unknown) {
        const apiErr = err as ApiErrorShape;
        setDeriveSubmitError(apiErr?.error?.message ?? t("needs.deriveFailed"));
      } finally {
        setDeriveSaving(false);
      }
    },
    [workspaceId, deriveDecision, t, closeDeriveDialog, refresh]
  );

  return {
    deriveOpen,
    deriveDecision,
    setDeriveDecision,
    deriveDrafts,
    deriveLoading,
    deriveLoadError,
    deriveSaving,
    deriveSubmitError,
    deriveStatus,
    openDeriveDialog,
    closeDeriveDialog,
    handleDerivePreview,
    handleDeriveDecision,
  };
}
