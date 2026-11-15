/**
 * ARCH-L1-001 ReactFrontend — batch save bar for the document reading view
 * (R6, plan 2026-11-15-document-view-on-document.md).
 *
 * Purely presentational: the batch request and the draft store live in
 * `useDocumentDrafts`. The bar only answers "how much is unsaved, is anything
 * in conflict, and what happens on save / discard".
 *
 * `role="status"` on the counter announces the number of unsaved fields
 * without interrupting the user's typing; a batch failure is a `role="alert"`,
 * because the drafts are still there and the user has to react (reload or
 * discard) instead of walking away believing the write landed.
 */

import { useTranslation } from "react-i18next";

import styles from "./Documents.module.css";

export interface DocumentSaveBarProps {
  /** Number of changed fields still waiting for the batch. */
  dirtyCount: number;
  /** Fields the server reported as changed underneath (marked, stay editable). */
  conflicts: string[];
  /** A batch (or a single-field save) is in flight. */
  saving?: boolean;
  /** Batch-level message: a server detail, or the `MISSING_ARTIFACT` code. */
  error?: string | null;
  onSaveAll: () => void;
  onDiscard: () => void;
}

/** Code the hook reports when the reading object carries no artifact id. */
const MISSING_ARTIFACT = "MISSING_ARTIFACT";

export function DocumentSaveBar({
  dirtyCount,
  conflicts,
  saving = false,
  error = null,
  onSaveAll,
  onDiscard,
}: DocumentSaveBarProps): JSX.Element {
  const { t } = useTranslation();
  const hasChanges = dirtyCount > 0;
  const conflictCount = conflicts.length;
  const errorText =
    error === MISSING_ARTIFACT ? t("documents.saveAllMissingArtifact") : error;

  return (
    <div
      className={styles.saveBar}
      data-testid="document-save-bar"
      role="group"
      aria-label={t("documents.saveBarLabel")}
    >
      <p className={styles.saveBarCount} role="status">
        {t("documents.dirtyFields", { value: dirtyCount })}
      </p>

      {conflictCount > 0 && (
        <p
          className={styles.fieldConflictNote}
          data-testid="document-save-bar-conflicts"
        >
          {t("documents.saveBarConflicts", { value: conflictCount })}
        </p>
      )}

      <div className={styles.saveBarActions}>
        <button
          type="button"
          className="btn-primary"
          data-testid="document-save-all"
          onClick={onSaveAll}
          disabled={!hasChanges || saving}
        >
          {saving ? t("documents.saving") : t("documents.saveAll")}
        </button>
        <button
          type="button"
          className="btn-ghost"
          data-testid="document-discard"
          onClick={onDiscard}
          disabled={!hasChanges || saving}
        >
          {t("documents.discard")}
        </button>
      </div>

      {errorText && (
        <p className={styles.error} role="alert" data-testid="document-save-bar-error">
          {errorText}
        </p>
      )}
    </div>
  );
}

DocumentSaveBar.displayName = "DocumentSaveBar";
