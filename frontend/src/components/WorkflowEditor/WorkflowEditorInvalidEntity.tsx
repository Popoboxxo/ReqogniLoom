/**
 * REQ-176 — Workflow Editor invalid-entity notice.
 *
 * P2.4: both scope containers resolve their own entity type, and both must
 * report an unresolvable one the same way instead of falling back to
 * Requirement. Keeping the notice in one component means the two containers
 * differ only in the ``backTo`` target (workspace list vs. System Settings →
 * Workflow Defaults), not in copy, ARIA or test hooks.
 */

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import styles from "./WorkflowEditor.module.css";

interface WorkflowEditorInvalidEntityProps {
  /** The raw route slug / query parameter that failed resolution. */
  slug: string | null;
  /** Scope-specific "back" target. */
  backTo: string;
}

export function WorkflowEditorInvalidEntity({
  slug,
  backTo,
}: WorkflowEditorInvalidEntityProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={styles.page} data-testid="workflow-editor-page">
      <div
        className={styles.scopeError}
        role="alert"
        data-testid="workflow-invalid-entity"
      >
        <AlertCircle
          size={32}
          className={styles.overlayIcon}
          aria-hidden="true"
        />
        <div>
          <h1 className={styles.overlayTitle}>
            {t("workflow.invalidEntity.title")}
          </h1>
          <p className={styles.overlayText}>
            {t("workflow.invalidEntity.message", { slug: slug ?? "" })}
          </p>
          <Link
            to={backTo}
            className={`btn-ghost ${styles.scopeErrorLink}`}
            data-testid="workflow-invalid-entity-back"
          >
            {t("workflow.invalidEntity.back")}
          </Link>
        </div>
      </div>
    </div>
  );
}
