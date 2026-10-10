/**
 * GlossarySynonyms — C10 synonym rendering for the glossary detail pane
 * (REQ-006).
 *
 * A synonym whose text matches an existing entry's term renders as a
 * clickable chip (the backend has no ID-based synonym-link field, so linking
 * is the normalized-text match); an unmatched synonym renders a "link"
 * button that opens the picker whose selection normalizes the synonym text
 * via PATCH (GlossaryTerm.synonyms is a plain string[] with no /tracelinks/
 * support — GlossaryTerm is not an Artifact subtype).
 *
 * Extracted from GlossaryView.tsx (repowise code-health refactor) —
 * identical markup and data-testid attributes.
 */
import { useTranslation } from "react-i18next";
import { Link2 } from "lucide-react";
import type { GlossaryTerm } from "../../types";
import { resolveSynonymLink } from "./glossary-view-shared";
import styles from "./GlossaryView.module.css";

export interface SynonymLinkingTarget {
  termId: string;
  index: number;
}

interface GlossarySynonymsProps {
  term: GlossaryTerm;
  terms: GlossaryTerm[];
  synonymLinkIndex: Map<string, GlossaryTerm>;
  linkingSynonym: SynonymLinkingTarget | null;
  synonymLinkQuery: string;
  onToggleLinking: (termId: string, index: number) => void;
  onSynonymLinkQueryChange: (value: string) => void;
  onCancelLinking: () => void;
  onLinkSynonym: (term: GlossaryTerm, index: number, target: GlossaryTerm) => void;
  onEditLinked: (term: GlossaryTerm) => void;
}

export function GlossarySynonyms({
  term,
  terms,
  synonymLinkIndex,
  linkingSynonym,
  synonymLinkQuery,
  onToggleLinking,
  onSynonymLinkQueryChange,
  onCancelLinking,
  onLinkSynonym,
  onEditLinked,
}: GlossarySynonymsProps): JSX.Element | null {
  const { t } = useTranslation();

  if (!term.synonyms || term.synonyms.length === 0) return null;

  return (
    <div className={styles.synonyms}>
      <strong>{t("glossary.synonymsLabel", "Synonyms")}:</strong>
      {term.synonyms.map((syn, idx) => {
        const linked = resolveSynonymLink(synonymLinkIndex, syn, term.id);
        const isLinking = linkingSynonym?.termId === term.id && linkingSynonym?.index === idx;
        const pickerQuery = synonymLinkQuery.trim().toLowerCase();
        const pickerCandidates = isLinking
          ? terms.filter(
              (candidate) =>
                candidate.id !== term.id && candidate.term.toLowerCase().includes(pickerQuery),
            )
          : [];
        return (
          <span key={`${term.id}-syn-${idx}`} className={styles.synonymWrap}>
            {linked ? (
              <button
                type="button"
                data-testid={`glossary-synonym-link-${term.id}-${idx}`}
                onClick={() => onEditLinked(linked)}
                title={t("glossary.synonymLinkedTooltip", "Zu verlinktem Eintrag springen")}
                className={styles.synonymLinkedBtn}
              >
                <Link2 size={12} />
                {syn}
              </button>
            ) : (
              <>
                <span>{syn}</span>
                <button
                  type="button"
                  data-testid={`glossary-synonym-linkbtn-${term.id}-${idx}`}
                  onClick={() => onToggleLinking(term.id, idx)}
                  title={t("glossary.linkSynonym", "Mit bestehendem Eintrag verlinken")}
                  aria-label={`${t("glossary.linkSynonym", "Mit bestehendem Eintrag verlinken")}: ${syn}`}
                  className={styles.synonymLinkBtn}
                >
                  <Link2 size={12} />
                </button>
              </>
            )}
            {isLinking && (
              <div className={styles.synonymPicker}>
                <input
                  autoFocus
                  data-testid={`glossary-synonym-search-${term.id}-${idx}`}
                  className={`${styles.input} ${styles.inputMarginBottom}`}
                  placeholder={t("glossary.searchPlaceholder")}
                  value={synonymLinkQuery}
                  onChange={(e) => onSynonymLinkQueryChange(e.target.value)}
                />
                <div className={styles.synonymPickerList}>
                  {pickerCandidates.slice(0, 20).map((candidate) => (
                    <button
                      key={candidate.id}
                      type="button"
                      data-testid={`glossary-synonym-option-${term.id}-${idx}-${candidate.id}`}
                      onClick={() => onLinkSynonym(term, idx, candidate)}
                      className={styles.synonymPickerOption}
                    >
                      {candidate.term}
                    </button>
                  ))}
                  {pickerCandidates.length === 0 && (
                    <p className={styles.synonymPickerEmpty}>
                      {t("glossary.noTerms")}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  data-testid={`glossary-synonym-cancel-${term.id}-${idx}`}
                  onClick={onCancelLinking}
                  className={styles.synonymPickerCancel}
                >
                  {t("actions.cancel", "Cancel")}
                </button>
              </div>
            )}
          </span>
        );
      })}
    </div>
  );
}
