/**
 * ARCH-L1-001 ReactFrontend — glossary term sidebar (Plan F F3-T9).
 *
 * The drag source for inline references: every term renders the *canonical*
 * stored token `[[glossary:<uuid>@<rev>]]` (ENT-F3 = a — the author never sees
 * a UUID in the text, the sidebar owns the translation). Clicking inserts at
 * the caret; dragging hands the token to the editor's drop zone. A term
 * without a `global_uuid` cannot be referenced and is not offered.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { glossaryApi } from "../../api/glossary";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { GlossaryTerm } from "../../types";
import styles from "./WorkItems.module.css";

export interface TermSidebarProps {
  workspaceId?: string;
  disabled?: boolean;
  onInsert: (token: string) => void;
  testId?: string;
}

/** Build the token the backend stores, never the `[[Begriff]]` display form. */
export function referenceToken(
  term: GlossaryTerm,
  mode: "pinned" | "always_head" = "pinned"
): string {
  const globalUuid = term.global_uuid;
  if (!globalUuid) return "";
  if (mode === "always_head" || term.version === undefined) {
    return `[[glossary:${globalUuid}]]`;
  }
  return `[[glossary:${globalUuid}@${term.version}]]`;
}

export function TermSidebar({
  workspaceId,
  disabled = false,
  onInsert,
  testId = "term-sidebar",
}: TermSidebarProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const mode = activeWorkspace?.glossary_reference_mode ?? "pinned";
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      setTerms([]);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    glossaryApi
      .list(workspaceId)
      .then((loaded) => {
        if (!cancelled) {
          setTerms(loaded.filter((term) => Boolean(term.global_uuid)));
        }
      })
      .catch(() => {
        if (!cancelled) setError(t("work_items.termSidebar.loadFailed"));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, t]);

  return (
    <aside className={styles.termSidebar} data-testid={testId}>
      <div>
        <h4 className={styles.sectionTitle}>
          {t("work_items.termSidebar.title")}
        </h4>
        <p className={styles.hint}>{t("work_items.termSidebar.hint")}</p>
      </div>

      {isLoading && (
        <p role="status" className={styles.hint} data-testid={`${testId}-loading`}>
          {t("work_items.termSidebar.loading")}
        </p>
      )}

      {error && (
        <p role="alert" className={styles.error} data-testid={`${testId}-error`}>
          {error}
        </p>
      )}

      {!isLoading && !error && terms.length === 0 && (
        <p className={styles.hint} data-testid={`${testId}-empty`}>
          {t("work_items.termSidebar.empty")}
        </p>
      )}

      {terms.length > 0 && (
        <ul className={styles.termList}>
          {terms.map((term) => {
            const token = referenceToken(term, mode);
            return (
              <li key={term.global_uuid}>
                <button
                  type="button"
                  className={`${styles.termItem} btn-ghost`}
                  data-testid={`${testId}-item-${term.global_uuid}`}
                  title={t("work_items.termSidebar.dragHint")}
                  draggable={!disabled}
                  disabled={disabled}
                  onDragStart={(event) => {
                    event.dataTransfer.setData("text/plain", token);
                    event.dataTransfer.effectAllowed = "copy";
                  }}
                  onClick={() => onInsert(token)}
                >
                  {term.term}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
