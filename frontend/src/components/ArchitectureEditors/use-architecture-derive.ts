/**
 * ARCH-L1-001 ReactFrontend — derive a requirement from an architecture element
 * (#598 S2).
 *
 * Extracted from `ArchitectureEditors.tsx`: the "Ableiten" form creates a
 * Requirement and allocates it to the selected element
 * (SE: Req --allocated-to--> ArchitectureElement). It is independent of the
 * element create, the decompose panel and the AI dialogs.
 *
 * Contract kept verbatim: the title is required locally, the link is written
 * after the requirement, and a failed link leaves the message in the form
 * (the component's own error slot) without navigating away.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import type { ArchitectureElement } from "../../types";

interface ApiErrorShape {
  error?: { message?: string };
}

export interface UseArchitectureDeriveOptions {
  element: ArchitectureElement | null;
  workspaceId: string | undefined;
  t: TFunction;
  navigate: (path: string) => void;
}

export interface UseArchitectureDeriveResult {
  showDeriveForm: boolean;
  deriveTitle: string;
  isDeriving: boolean;
  deriveError: string | null;
  openDeriveForm: () => void;
  closeDeriveForm: () => void;
  setDeriveTitle: (value: string) => void;
  handleDeriveRequirement: () => Promise<void>;
}

export function useArchitectureDerive({
  element,
  workspaceId,
  t,
  navigate,
}: UseArchitectureDeriveOptions): UseArchitectureDeriveResult {
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState("");
  const [isDeriving, setIsDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);

  const openDeriveForm = useCallback((): void => {
    setShowDeriveForm(true);
  }, []);

  const closeDeriveForm = useCallback((): void => {
    setShowDeriveForm(false);
    setDeriveError(null);
  }, []);

  const handleDeriveRequirement = useCallback(async (): Promise<void> => {
    if (!element || !workspaceId) return;
    if (!deriveTitle.trim()) {
      setDeriveError(t("traceability.deriveTitleRequired"));
      return;
    }
    setIsDeriving(true);
    setDeriveError(null);
    try {
      const created = await requirementsApi.create({
        workspace_id: workspaceId,
        title: deriveTitle.trim(),
      });
      await tracelinksApi.create({
        source_id: created.id,
        target_id: element.id,
        link_type: "allocated-to",
      });
      setShowDeriveForm(false);
      setDeriveTitle("");
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      const apiErr = err as ApiErrorShape;
      setDeriveError(apiErr?.error?.message ?? t("needs.deriveFailed"));
    } finally {
      setIsDeriving(false);
    }
  }, [element, workspaceId, deriveTitle, t, navigate]);

  return {
    showDeriveForm,
    deriveTitle,
    isDeriving,
    deriveError,
    openDeriveForm,
    closeDeriveForm,
    setDeriveTitle,
    handleDeriveRequirement,
  };
}
