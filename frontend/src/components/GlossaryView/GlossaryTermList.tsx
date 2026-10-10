/**
 * GlossaryTermList — left-panel row list for glossary terms (no hierarchy —
 * a term has no parent/child relation).
 *
 * Extracted from GlossaryView.tsx (repowise code-health refactor): the row
 * markup, the selection aria wiring and the per-row edit/delete actions are
 * unchanged, the handlers stay owned by the container.
 */
import { Edit2, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { GlossaryTerm } from "../../types";
import styles from "./GlossaryView.module.css";

interface GlossaryTermListProps {
  terms: GlossaryTerm[];
  selectedId: string | null;
  onSelect: (term: GlossaryTerm) => void;
  onEdit: (term: GlossaryTerm) => void;
  onDelete: (id: string) => void;
}

export function GlossaryTermList({
  terms,
  selectedId,
  onSelect,
  onEdit,
  onDelete,
}: GlossaryTermListProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div data-testid="glossary-rows" className={styles.rowsList}>
      {terms.map((term) => {
        const isSelected = term.id === selectedId;
        return (
          <div
            key={term.id}
            data-testid={`glossary-row-${term.id}`}
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            onClick={() => onSelect(term)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(term);
              }
            }}
            className={`${styles.row} ${isSelected ? styles.rowSelected : styles.rowIdle}`}
          >
            <div className={styles.minWidth0}>
              <div className={styles.rowTitleLine}>
                <span className={styles.rowTerm}>{term.term}</span>
                {term.abbreviation && (
                  <span className={styles.abbreviationBadge}>
                    {term.abbreviation}
                  </span>
                )}
                {term.workspace_id === null && (
                  <span className={styles.globalBadge}>
                    {t("glossary.global")}
                  </span>
                )}
              </div>
              <p className={styles.rowDefinition}>
                {term.definition}
              </p>
            </div>
            <div className={styles.rowActions}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(term);
                }}
                className={`${styles.iconBtn} ${styles.iconBtnMuted}`}
                // #741: icon-only row action — was an untranslated,
                // aria-label-less `title`, i.e. no reliable accessible
                // name at all. Names the term so the per-row buttons are
                // distinguishable in a screen reader's element list.
                title={t("actions.edit")}
                aria-label={`${t("actions.edit")}: ${term.term}`}
                data-testid={`glossary-edit-${term.id}`}
              >
                <Edit2 size={16} />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(term.id);
                }}
                className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                title={t("actions.delete")}
                aria-label={`${t("actions.delete")}: ${term.term}`}
                data-testid={`glossary-delete-${term.id}`}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
