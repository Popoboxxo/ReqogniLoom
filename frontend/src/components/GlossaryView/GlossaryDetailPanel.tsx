/**
 * GlossaryDetailPanel — read-only detail of the selected glossary term:
 * abbreviation/global badges, definition and the synonym block.
 *
 * Extracted from GlossaryView.tsx (repowise code-health refactor) —
 * identical markup and data-testid attributes; the synonym block is composed
 * by the container so the synonym-link picker state stays in one place.
 *
 * #1762/M5 (spec §11 D8): the term's trace links ("Verwendungen") are no
 * longer an inline block under the definition. They live in the Links tab of
 * the shared `InspectorShell`, which the route mounts next to this panel —
 * so the detail pane holds one definition block and nothing else.
 */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { GlossaryTerm } from "../../types";
import styles from "./GlossaryView.module.css";

interface GlossaryDetailPanelProps {
  term: GlossaryTerm;
  onEdit: (term: GlossaryTerm) => void;
  onDelete: (id: string) => void;
  synonyms?: ReactNode;
}

export function GlossaryDetailPanel({
  term,
  onEdit,
  onDelete,
  synonyms,
}: GlossaryDetailPanelProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div data-testid="glossary-detail" className={styles.detail}>
      <div className={styles.detailHeader}>
        <div>
          <div className={styles.detailTitleRow}>
            <h2 className={styles.detailTitle}>{term.term}</h2>
            {term.abbreviation && (
              <span className={styles.abbreviationBadge}>
                {term.abbreviation}
              </span>
            )}
            {term.workspace_id === null && (
              <span className={styles.globalBadgeDetail}>
                {t("glossary.global")}
              </span>
            )}
          </div>
        </div>
        <div className={styles.detailActions}>
          <button
            type="button"
            data-testid="glossary-detail-edit-btn"
            onClick={() => onEdit(term)}
            className="btn-secondary"
          >
            {t("actions.edit", "Bearbeiten")}
          </button>
          <button
            type="button"
            data-testid="glossary-detail-delete-btn"
            onClick={() => onDelete(term.id)}
            className="btn-danger"
          >
            {t("actions.delete", "Löschen")}
          </button>
        </div>
      </div>

      <p className={styles.detailDefinition}>{term.definition}</p>

      {synonyms}
    </div>
  );
}
