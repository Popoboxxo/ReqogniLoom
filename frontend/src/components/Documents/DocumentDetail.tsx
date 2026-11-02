/**
 * ARCH-L1-001 ReactFrontend — Document detail pane (Plan F F2-T8).
 *
 * Read-only view of one document: identity, lifecycle, freeze state and
 * content. Lifecycle actions go through the shared `<WorkflowStatusEditor>`
 * (artifactType="document"), which owns the allowed-transition menu, the
 * mandatory change-reason prompt and the signature gate. The document's own
 * optimistic-lock version is forwarded so a concurrent edit answers 412
 * instead of silently overwriting the winner.
 */

import { useTranslation } from "react-i18next";

import { DocumentLifecycle } from "./DocumentLifecycle";
import { WorkItemsPanel } from "../WorkItems/WorkItemsPanel";
import { InlineReferenceHints } from "../WorkItems/InlineReferenceHints";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import { isOutdatedState } from "../../utils/outdatedStates";
import type { Document, DocumentKind } from "../../types";
import styles from "./Documents.module.css";

const KIND_LABEL_KEY: Record<DocumentKind, string> = {
  Spec: "documents.kinds.spec",
  Plan: "documents.kinds.plan",
  AuditReport: "documents.kinds.auditReport",
  Review: "documents.kinds.review",
  Conclusion: "documents.kinds.conclusion",
  Concept: "documents.kinds.concept",
  Guide: "documents.kinds.guide",
};

export interface DocumentDetailProps {
  document: Document;
  canWrite: boolean;
  workspaceId?: string;
  onEdit: () => void;
  onDelete: () => void;
  onReactivate: () => void;
  onTransitionComplete: () => void;
  actionError: string | null;
}

export function DocumentDetail({
  document,
  canWrite,
  workspaceId,
  onEdit,
  onDelete,
  onReactivate,
  onTransitionComplete,
  actionError,
}: DocumentDetailProps): JSX.Element {
  const { t } = useTranslation();
  const outdated = isOutdatedState(document.status);
  const frozenFields = document.frozen_fields ?? [];
  const isFrozen = frozenFields.length > 0 || Boolean(document.frozen_at);
  const frozenDate = document.frozen_at
    ? document.frozen_at.slice(0, 10)
    : null;

  return (
    <article className={styles.detail} data-testid="document-detail">
      <header className={styles.detailHeader}>
        <div>
          <h2 className={styles.detailTitle}>
            {document.title || t("documents.untitled")}
          </h2>
          <p className={styles.meta}>
            <span data-testid="document-detail-uid">
              {document.uid ?? document.id.slice(0, 8)}
            </span>
            <span aria-hidden="true">·</span>
            <span data-testid="document-detail-kind">
              {t(KIND_LABEL_KEY[document.kind])}
            </span>
            <span aria-hidden="true">·</span>
            <span data-testid="document-detail-status">
              {getWorkflowStatusLabel(document.status)}
            </span>
            <span aria-hidden="true">·</span>
            <span data-testid="document-detail-version">
              {t("documents.versionLabel", { version: document.version })}
            </span>
            {document.doc_date && (
              <>
                <span aria-hidden="true">·</span>
                <span data-testid="document-detail-date">
                  {document.doc_date}
                </span>
              </>
            )}
          </p>
        </div>

        {canWrite && !outdated && (
          <div className={styles.actions}>
            <button
              type="button"
              className="btn-primary"
              data-testid="document-edit"
              onClick={onEdit}
            >
              {t("documents.edit")}
            </button>
            <button
              type="button"
              className="btn-danger"
              data-testid="document-delete"
              onClick={onDelete}
            >
              {t("documents.delete")}
            </button>
          </div>
        )}
        {canWrite && outdated && (
          <div className={styles.actions}>
            <button
              type="button"
              className="btn-secondary"
              data-testid="document-reactivate"
              onClick={onReactivate}
            >
              {t("documents.reactivate")}
            </button>
          </div>
        )}
      </header>

      <section className={styles.lifecycle} aria-label={t("documents.lifecycle")}>
        <span className={styles.sectionLabel}>{t("documents.lifecycle")}</span>
        <DocumentLifecycle
          document={document}
          canWrite={canWrite}
          workspaceId={workspaceId}
          onTransitionComplete={onTransitionComplete}
        />
      </section>

      {isFrozen && (
        <div
          role="note"
          className={styles.freezeBanner}
          data-testid="document-frozen-banner"
        >
          <strong>{t("documents.frozenTitle")}</strong>
          <p>
            {frozenDate
              ? t("documents.frozenSince", { date: frozenDate })
              : t("documents.frozenHint")}
          </p>
          {frozenFields.length > 0 && (
            <p data-testid="document-frozen-fields">
              {t("documents.frozenFields", {
                fields: frozenFields.join(", "),
              })}
            </p>
          )}
        </div>
      )}

      {actionError && (
        <p role="alert" className={styles.error} data-testid="document-action-error">
          {actionError}
        </p>
      )}

      {document.description && (
        <section>
          <h3 className={styles.sectionLabel}>{t("documents.description")}</h3>
          <p className={styles.description}>{document.description}</p>
        </section>
      )}

      <section>
        <h3 className={styles.sectionLabel}>{t("documents.body")}</h3>
        <div className={styles.bodyText} data-testid="document-detail-body">
          {document.body || t("documents.bodyEmpty")}
        </div>
        <InlineReferenceHints
          text={document.body}
          workspaceId={workspaceId}
          testId="document-inline-reference-hints"
        />
      </section>

      <WorkItemsPanel
        documentId={document.id}
        workspaceId={workspaceId}
        canWrite={canWrite}
      />
    </article>
  );
}

DocumentDetail.displayName = "DocumentDetail";
