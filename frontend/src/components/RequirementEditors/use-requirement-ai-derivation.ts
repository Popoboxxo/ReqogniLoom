/**
 * ARCH-L1-001 ReactFrontend — requirement AI derivation (#598 S2, #1358/#1360).
 *
 * Extracted from `RequirementEditors.tsx`: the next-level decomposition preview
 * and the shared review dialog are independent of the list/create/export state
 * the route also carries.
 *
 * Contract kept verbatim:
 *   - the preview is `ephemeral: true` — it writes nothing; Discard writes
 *     nothing either,
 *   - an empty draft list is its own state, not a success (issue #311),
 *   - a preview failure is reported twice on purpose: in the dialog (where the
 *     user is) and in the route's status region (which survives closing it),
 *   - only Confirm / "Review later" reach the accept seam, and the difference
 *     between them is the message, not the write path (#1360),
 *   - a server answer that is not a proposal is surfaced with its own reason
 *     instead of claiming a queue entry that does not exist.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { requirementsApi } from "../../api/requirements";
import type { Requirement } from "../../types";
import type { AiDerivationDraft } from "../shared/AiDerivationDialog";

interface ApiErrorShape {
  error?: { message?: string };
}

export interface UseRequirementAiDerivationResult {
  showAiDeriveDialog: boolean;
  aiDrafts: AiDerivationDraft[] | null;
  aiDraftLoadError: string | null;
  aiDraftSubmitError: string | null;
  isAiDeriving: boolean;
  isAiSaving: boolean;
  aiDeriveStatus: string | null;
  aiDeriveIsError: boolean;
  handleAiDerive: () => Promise<void>;
  handleAiDraftDecision: (
    drafts: AiDerivationDraft[],
    parked: boolean
  ) => Promise<void>;
  closeAiDeriveDialog: () => void;
}

export function useRequirementAiDerivation(
  requirement: Requirement | null | undefined,
  t: TFunction,
  refresh: () => void
): UseRequirementAiDerivationResult {
  const [isAiDeriving, setIsAiDeriving] = useState(false);
  const [aiDeriveStatus, setAiDeriveStatus] = useState<string | null>(null);
  const [aiDeriveIsError, setAiDeriveIsError] = useState(false);
  const [showAiDeriveDialog, setShowAiDeriveDialog] = useState(false);
  const [aiDrafts, setAiDrafts] = useState<AiDerivationDraft[] | null>(null);
  const [aiDraftLoadError, setAiDraftLoadError] = useState<string | null>(null);
  const [isAiSaving, setIsAiSaving] = useState(false);
  const [aiDraftSubmitError, setAiDraftSubmitError] = useState<string | null>(null);

  const handleAiDerive = useCallback(async (): Promise<void> => {
    if (!requirement) return;
    setIsAiDeriving(true);
    setAiDeriveIsError(false);
    setAiDeriveStatus(t("needs.deriveStarting"));
    setAiDraftLoadError(null);
    setAiDraftSubmitError(null);
    setAiDrafts(null);
    setShowAiDeriveDialog(true);
    try {
      const result = await requirementsApi.aiDecomposeNextLevel(requirement.id);
      const drafts = result.drafts ?? [];
      // Issue #311: an empty answer is a state of its own, not a success — the
      // dialog renders its explicit empty state and the status region stays
      // silent (it never claims a save that did not happen).
      setAiDrafts(
        drafts.map((draft) => ({
          title: draft.title,
          description: draft.description,
          rationale: draft.rationale,
        }))
      );
      setAiDeriveStatus(null);
    } catch (err: unknown) {
      const apiErr = err as ApiErrorShape;
      const message = apiErr?.error?.message ?? t("needs.deriveFailed");
      setAiDraftLoadError(message);
      setAiDeriveIsError(true);
      setAiDeriveStatus(message);
    } finally {
      setIsAiDeriving(false);
    }
  }, [requirement, t]);

  const handleAiDraftDecision = useCallback(
    async (drafts: AiDerivationDraft[], parked: boolean): Promise<void> => {
      if (!requirement || drafts.length === 0) return;
      setIsAiSaving(true);
      setAiDraftSubmitError(null);
      try {
        const result = await requirementsApi.acceptAiDecomposition(
          requirement.id,
          drafts.map((draft) => ({
            title: draft.title,
            description: draft.description,
            rationale: draft.rationale,
          }))
        );
        if (!result.proposal?.is_proposal) {
          // The server read the created state back and it is not a proposal.
          setAiDraftSubmitError(
            t("deriveRequirements.reviewRequired", {
              reason: result.proposal?.reason || t("needs.deriveFailed"),
            })
          );
          return;
        }
        setAiDeriveIsError(false);
        setAiDeriveStatus(
          t(parked ? "aiDerivation.statusParked" : "aiDerivation.statusCreated", {
            count: result.count,
          })
        );
        setShowAiDeriveDialog(false);
        setAiDrafts(null);
        refresh();
      } catch (err: unknown) {
        const apiErr = err as ApiErrorShape;
        setAiDraftSubmitError(apiErr?.error?.message ?? t("needs.deriveFailed"));
      } finally {
        setIsAiSaving(false);
      }
    },
    [requirement, t, refresh]
  );

  const closeAiDeriveDialog = useCallback((): void => {
    setShowAiDeriveDialog(false);
    setAiDrafts(null);
    setAiDraftLoadError(null);
    setAiDraftSubmitError(null);
  }, []);

  return {
    showAiDeriveDialog,
    aiDrafts,
    aiDraftLoadError,
    aiDraftSubmitError,
    isAiDeriving,
    isAiSaving,
    aiDeriveStatus,
    aiDeriveIsError,
    handleAiDerive,
    handleAiDraftDecision,
    closeAiDeriveDialog,
  };
}
