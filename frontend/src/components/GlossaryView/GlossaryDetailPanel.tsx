/**
 * GlossaryDetailPanel — read-only detail of the selected glossary term:
 * abbreviation/global badges, definition, the synonym block and the usages
 * section (C9 trace links, REQ-142 version history/diff).
 *
 * Extracted from GlossaryView.tsx (repowise code-health refactor) —
 * identical markup and data-testid attributes; the synonym block is composed
 * by the container so the synonym-link picker state stays in one place.
 */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { GlossaryTerm } from "../../types";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
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
            className={`${styles.btn} ${styles.btnOutline}`}
          >
            {t("actions.edit", "Bearbeiten")}
          </button>
          <button
            type="button"
            data-testid="glossary-detail-delete-btn"
            onClick={() => onDelete(term.id)}
            className={`${styles.btn} ${styles.btnOutlineDanger}`}
          >
            {t("actions.delete", "Löschen")}
          </button>
        </div>
      </div>

      <p className={styles.detailDefinition}>{term.definition}</p>

      {synonyms}

      {/* Usages + Versions/Diff (REQ-142, UI-59): trace links referencing this
          glossary entry (C9), plus the version history + field-level diff
          that the shared VersionPanel/DiffPanel already support for
          kind="glossary" — only wiring `currentVersion` was missing, which
          previously forced this panel into its undefined/degraded state. */}
      <div className={styles.usagesSection}>
        <h3 className={styles.usagesHeading}>
          {t("glossary.usages", "Verwendungen")}
        </h3>
        <RightSidebar
          kind="glossary"
          artifactId={term.id}
          currentVersion={
            typeof term.version === "number"
              ? ({
                  version: term.version,
                  label: `v${term.version}`,
                  createdAt: term.updated_at ?? null,
                  baselineIds: [],
                } satisfies VersionRef)
              : undefined
          }
        />
      </div>
    </div>
  );
}
