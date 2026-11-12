/**
 * ARCH-L1-001 ReactFrontend — glossary synonym linking (#598 S2, C10/REQ-006).
 *
 * Extracted from `GlossaryView.tsx`: the open picker, its query and the link
 * write. The list, the term form and the AI derivation stay in the view.
 *
 * Backend constraint kept verbatim: `GlossaryTerm.synonyms` is a plain string[]
 * and the term is not an Artifact subtype, so "linking" normalises the synonym
 * text to the target term's exact string through PATCH /glossary/{id}/.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { glossaryApi } from "../../api/glossary";
import type { GlossaryTerm } from "../../types";
import { extractErrorMessage } from "../../api/client";

export interface SynonymLinkTarget {
  termId: string;
  index: number;
}

export interface UseGlossarySynonymLinkOptions {
  t: TFunction;
  reloadTerms: () => void;
  /** Row-level banner is shared with delete, so the view owns its setter. */
  onError: (message: string) => void;
}

export interface UseGlossarySynonymLinkResult {
  linkingSynonym: SynonymLinkTarget | null;
  synonymLinkQuery: string;
  setSynonymLinkQuery: (value: string) => void;
  toggleSynonymLinking: (termId: string, index: number) => void;
  closeSynonymLinking: () => void;
  handleLinkSynonym: (
    term: GlossaryTerm,
    index: number,
    target: GlossaryTerm
  ) => Promise<void>;
}

export function useGlossarySynonymLink({
  t,
  reloadTerms,
  onError,
}: UseGlossarySynonymLinkOptions): UseGlossarySynonymLinkResult {
  const [linkingSynonym, setLinkingSynonym] = useState<SynonymLinkTarget | null>(null);
  const [synonymLinkQuery, setSynonymLinkQuery] = useState("");

  // C10: clicking the open picker's trigger again closes it and resets the
  // picker query.
  const toggleSynonymLinking = useCallback(
    (termId: string, index: number): void => {
      const isLinking =
        linkingSynonym?.termId === termId && linkingSynonym?.index === index;
      setLinkingSynonym(isLinking ? null : { termId, index });
      setSynonymLinkQuery("");
    },
    [linkingSynonym]
  );

  const closeSynonymLinking = useCallback((): void => {
    setLinkingSynonym(null);
  }, []);

  const handleLinkSynonym = useCallback(
    async (term: GlossaryTerm, index: number, target: GlossaryTerm): Promise<void> => {
      const newSynonyms = term.synonyms.map((synonym, position) =>
        position === index ? target.term : synonym
      );
      try {
        onError("");
        await glossaryApi.update(term.id, { synonyms: newSynonyms });
        setLinkingSynonym(null);
        setSynonymLinkQuery("");
        reloadTerms();
      } catch (err: unknown) {
        onError(extractErrorMessage(err) || t("glossary.linkSynonymFailed"));
      }
    },
    [t, reloadTerms, onError]
  );

  return {
    linkingSynonym,
    synonymLinkQuery,
    setSynonymLinkQuery,
    toggleSynonymLinking,
    closeSynonymLinking,
    handleLinkSynonym,
  };
}
