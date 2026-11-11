/**
 * ARCH-L1-001 ReactFrontend — manual need→requirement derivation (#598 S2, UI-33).
 *
 * Extracted from `NeedsEditors.tsx`: the manual derive form (title + optional
 * architecture allocation) is independent of the created/deleted list, the
 * create form and the AI draft flow.
 *
 * UI-33 contract kept verbatim: the flow is three independent REST calls
 * (create Requirement, `derives-from`, optional `allocated-to`), not one
 * transaction. If a link call fails after the requirement was created, the
 * orphan is soft-deleted on a best-effort basis and the message says whether
 * that cleanup worked — never a bare "derive failed" once something persisted.
 */

import { useCallback, useEffect, useState } from "react";
import type { TFunction } from "i18next";

import { architectureApi } from "../../api/architecture";
import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import type { ArchitectureElement, Requirement, StakeholderNeed } from "../../types";

interface ApiErrorShape {
  error?: { message?: string };
}

export interface UseManualDeriveOptions {
  need: StakeholderNeed | null | undefined;
  t: TFunction;
  refresh: () => void;
  navigate: (path: string) => void;
}

export interface UseManualDeriveResult {
  showDeriveForm: boolean;
  deriveTitle: string;
  deriveArchId: string;
  isManualDeriving: boolean;
  deriveError: string | null;
  archElements: ArchitectureElement[];
  openDeriveForm: () => void;
  closeDeriveForm: () => void;
  setDeriveTitle: (value: string) => void;
  setDeriveArchId: (value: string) => void;
  handleManualDerive: () => Promise<void>;
}

export function useManualDerive({
  need,
  t,
  refresh,
  navigate,
}: UseManualDeriveOptions): UseManualDeriveResult {
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState("");
  const [deriveArchId, setDeriveArchId] = useState("");
  const [isManualDeriving, setIsManualDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);
  const [archElements, setArchElements] = useState<ArchitectureElement[]>([]);

  // The allocation picker is loaded lazily, only while the form is open.
  useEffect(() => {
    if (!showDeriveForm || !need) return;
    let cancelled = false;
    architectureApi
      .listAll(need.workspace_id)
      .then((els) => {
        if (!cancelled) setArchElements(els);
      })
      .catch(() => {
        if (!cancelled) setArchElements([]);
      });
    return () => {
      cancelled = true;
    };
  }, [showDeriveForm, need]);

  const openDeriveForm = useCallback((): void => {
    setShowDeriveForm(true);
  }, []);

  const closeDeriveForm = useCallback((): void => {
    setShowDeriveForm(false);
    setDeriveError(null);
  }, []);

  const handleManualDerive = useCallback(async (): Promise<void> => {
    if (!need) return;
    if (!deriveTitle.trim()) {
      setDeriveError(t("traceability.deriveTitleRequired"));
      return;
    }
    setIsManualDeriving(true);
    setDeriveError(null);
    let created: Requirement | null = null;
    try {
      created = await requirementsApi.create({
        workspace_id: need.workspace_id,
        title: deriveTitle.trim(),
      });
      await tracelinksApi.create({
        source_id: created.id,
        target_id: need.artifact_id,
        link_type: "derives-from",
      });
      if (deriveArchId) {
        await tracelinksApi.create({
          source_id: created.id,
          target_id: deriveArchId,
          link_type: "allocated-to",
        });
      }
      setShowDeriveForm(false);
      setDeriveTitle("");
      setDeriveArchId("");
      refresh();
      navigate(`/requirements/${created.id}`);
    } catch (err) {
      const apiErr = err as ApiErrorShape;
      const baseMessage = apiErr?.error?.message ?? t("needs.deriveFailed");
      if (created) {
        // Best-effort compensating action: never leave the orphan silently.
        const orphanId = created.id;
        try {
          await requirementsApi.delete(orphanId);
          setDeriveError(
            t("needs.deriveRolledBack", {
              message: baseMessage,
              defaultValue: `${baseMessage} The already-created requirement was rolled back (archived).`,
            })
          );
        } catch {
          setDeriveError(
            t("needs.derivePartialFailure", {
              message: baseMessage,
              id: orphanId,
              defaultValue: `${baseMessage} Warning: a requirement was already created, but linking it to the need failed and the automatic rollback failed too. Please check manually (requirement id: ${orphanId}).`,
            })
          );
        }
      } else {
        setDeriveError(baseMessage);
      }
    } finally {
      setIsManualDeriving(false);
    }
  }, [need, t, deriveTitle, deriveArchId, refresh, navigate]);

  return {
    showDeriveForm,
    deriveTitle,
    deriveArchId,
    isManualDeriving,
    deriveError,
    archElements,
    openDeriveForm,
    closeDeriveForm,
    setDeriveTitle,
    setDeriveArchId,
    handleManualDerive,
  };
}
