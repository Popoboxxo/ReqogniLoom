/**
 * ARCH-L1-001 ReactFrontend — stakeholder-need AI derivation (#598 S2).
 *
 * Extracted from `NeedsEditors.tsx`: the draft/accept flow behind
 * REQ-L2-AI-001/002. The manual derive and the create form stay in the page.
 *
 * Contract kept verbatim:
 *   - starting a run clears the previous drafts and reports "starting",
 *   - an empty draft list is its own message, not a success,
 *   - an error marks the status region as an alert and shows the server text,
 *   - discarding clears the drafts without a server round-trip.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { stakeholderNeedApi } from "../../api/stakeholder-need";
import type { DerivedRequirementDraft } from "../../api/stakeholder-need";
import type { StakeholderNeed } from "../../types";

interface ApiErrorShape {
  error?: { message?: string };
}

export interface UseNeedDeriveOptions {
  need: StakeholderNeed | null | undefined;
  t: TFunction;
}

export interface UseNeedDeriveResult {
  isDeriving: boolean;
  derivationStatus: string | null;
  derivationIsError: boolean;
  derivedDrafts: DerivedRequirementDraft[] | null;
  handleDerive: () => Promise<void>;
  discardDrafts: () => void;
  /** Clear the drafts and report the accepted count. */
  markAccepted: (count: number) => void;
}

export function useNeedDerive({
  need,
  t,
}: UseNeedDeriveOptions): UseNeedDeriveResult {
  const [isDeriving, setIsDeriving] = useState(false);
  const [derivationStatus, setDerivationStatus] = useState<string | null>(null);
  const [derivationIsError, setDerivationIsError] = useState(false);
  const [derivedDrafts, setDerivedDrafts] = useState<DerivedRequirementDraft[] | null>(
    null
  );

  // Issue #1092: stable identity — the route's <AiActionSection> action list
  // depends on it, and an unstable callback would invalidate the memo on every
  // render.
  const handleDerive = useCallback(async (): Promise<void> => {
    if (!need) return;
    setIsDeriving(true);
    setDerivationIsError(false);
    setDerivationStatus(t("needs.deriveStarting"));
    setDerivedDrafts(null);
    try {
      const res = await stakeholderNeedApi.deriveRequirements(need.id);
      const drafts = res.drafts ?? [];
      if (drafts.length === 0) {
        setDerivationStatus(t("needs.deriveEmpty"));
        return;
      }
      setDerivedDrafts(drafts);
      setDerivationStatus(null);
    } catch (err: unknown) {
      const apiErr = err as ApiErrorShape;
      setDerivationIsError(true);
      setDerivationStatus(apiErr?.error?.message ?? t("needs.deriveFailed"));
    } finally {
      setIsDeriving(false);
    }
  }, [need, t]);

  const discardDrafts = useCallback((): void => {
    setDerivedDrafts(null);
  }, []);

  const markAccepted = useCallback(
    (count: number): void => {
      setDerivedDrafts(null);
      setDerivationIsError(false);
      // #1089: name WHERE the new artefacts are reviewable — "created and
      // linked" left the user with nothing to do next.
      setDerivationStatus(t("needs.deriveCreated", { count }));
    },
    [t]
  );

  return {
    isDeriving,
    derivationStatus,
    derivationIsError,
    derivedDrafts,
    handleDerive,
    discardDrafts,
    markAccepted,
  };
}
